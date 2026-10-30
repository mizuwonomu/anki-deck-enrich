"""Standalone strict source-input and source-map validation for Phase 1."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from .config import StageConfig
from .pathrefs import relative_reference
from .source_apkg import file_sha256, read_source_snapshot
from .sources import get_source_adapter
from .validation import InputStageError, ValidationError, read_jsonl


def protected_stage_paths(config: StageConfig, *, publisher_stage: str) -> set[Path]:
    """Resolve the full protected boundary for a Phase 1 artifact publisher.

    `source_input` and normalization destinations are generated outputs only for
    normalize; validate-input treats them as protected inputs/sidecars. Excluding
    outputs by field role (not by their resolved path value) ensures an output
    alias cannot unprotect the source APKG, schema, or another declared input.
    """
    if publisher_stage not in {"normalize", "validate-input"}:
        raise ValueError(f"Unsupported Phase 1 publisher stage {publisher_stage!r}")
    protected: set[Path] = {config.config_path.resolve()}
    for candidate in (config.paths.input, config.paths.output_schema, config.paths.input_schema, config.paths.output_dir):
        if candidate is not None:
            protected.add(candidate.resolve())
    if config.source is not None:
        protected.update({config.source.apkg.resolve(), config.source.mapping_contract.resolve()})
    if publisher_stage == "validate-input":
        if config.paths.source_input is not None:
            protected.add(config.paths.source_input.resolve())
        if config.normalization is not None:
            protected.update({
                config.normalization.source_map.resolve(),
                config.normalization.raw_notes.resolve(),
                config.normalization.exceptions.resolve(),
                config.normalization.report.resolve(),
            })
    return protected


def _read_json(path: Path, what: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise InputStageError(f"Cannot read {what} at {path}: {exc}", file=str(path)) from exc
    except UnicodeDecodeError as exc:
        raise InputStageError(f"Invalid UTF-8 in {what} at {path}: {exc}", file=str(path)) from exc
    except json.JSONDecodeError as exc:
        raise InputStageError(
            f"Invalid JSON in {what} at {path}:{exc.lineno}:{exc.colno}: {exc.msg}", file=str(path)
        ) from exc


def _schema_validator(path: Path) -> Draft202012Validator:
    schema = _read_json(path, "input schema")
    try:
        Draft202012Validator.check_schema(schema)
    except Exception as exc:
        raise InputStageError(f"Invalid input schema {path}: {exc}") from exc
    return Draft202012Validator(schema, format_checker=FormatChecker())



def validate_input_objects(
    records: list[dict[str, Any]],
    validator: Draft202012Validator,
    *,
    expected_ids: tuple[str, ...] | None,
    file: Path | str | None = None,
    batch_id: str | None = None,
) -> None:
    file_name = str(file) if file is not None else None

    def failure(message: str, *, line_no: int | None = None, record_id: Any = None, path: str | None = None) -> InputStageError:
        if batch_id is not None:
            location = f"batch {batch_id}"
            if line_no is not None:
                location += f" line {line_no}"
            message = f"{location}: {message}"
        return InputStageError(
            message,
            record_id=None if record_id is None else str(record_id),
            file=file_name,
            path=path,
        )

    if not records:
        raise failure("input dataset path $: at least one input record is required", line_no=1, path="/")
    ids: list[str] = []
    for line_no, record in enumerate(records, start=1):
        record_id = record.get("id", f"line-{line_no}")
        errors = sorted(validator.iter_errors(record), key=lambda err: (list(map(str, err.absolute_path)), err.message))
        if errors:
            err = errors[0]
            path = "/" + "/".join(str(part) for part in err.absolute_path) if err.absolute_path else "/"
            raise failure(f"input {record_id!r} path {path}: {err.message}", line_no=line_no, record_id=record_id, path=path)
        ids.append(record["id"])
    if len(ids) != len(set(ids)):
        duplicate_index = next(index for index, item in enumerate(ids) if item in ids[:index])
        duplicate = ids[duplicate_index]
        raise failure(
            f"input dataset path /id: duplicate input ID {duplicate!r}",
            line_no=duplicate_index + 1,
            record_id=duplicate,
            path="/id",
        )
    if expected_ids is not None and tuple(ids) != expected_ids:
        limit = max(len(ids), len(expected_ids))
        difference = next(
            index for index in range(limit)
            if index >= len(ids) or index >= len(expected_ids) or ids[index] != expected_ids[index]
        )
        record_id = ids[difference] if difference < len(ids) else None
        raise failure(
            f"input dataset path /id: expected ordered IDs {list(expected_ids)!r}, got {ids!r}",
            line_no=difference + 1,
            record_id=record_id,
            path="/id",
        )



def validate_input_dataset(config: StageConfig) -> dict[str, Any]:
    """Validate strict JSONL and optional adapter-declared source-map/raw linkage."""
    if config.paths.source_input is None or config.paths.input_schema is None:
        raise InputStageError("paths.source_input and paths.input_schema are required for validate-input")
    schema_path = config.paths.input_schema
    validator = _schema_validator(schema_path)
    raw_bytes, records = read_jsonl(config.paths.source_input, "source input JSONL")
    validate_input_objects(records, validator, expected_ids=config.constraints.input_ids)
    digest = hashlib.sha256(raw_bytes).hexdigest()
    expected_digest = config.constraints.source_input_sha256
    if expected_digest is not None and digest != expected_digest:
        raise InputStageError(f"input dataset path $: source_input_sha256 mismatch; expected {expected_digest}, got {digest}")

    sidecar_hashes: dict[str, str] = {}
    source_details = None
    if config.source is not None:
        adapter = get_source_adapter(config.source.adapter)
        try:
            source = adapter.validate_profile_config(config)
        except adapter.MappingFailure as exc:
            raise InputStageError(f"source/config path $: {exc}", file=str(config.config_path)) from exc
        if file_sha256(source.apkg) != source.sha256:
            raise InputStageError(f"source APKG path $: source SHA-256 mismatch for {source.apkg}", file=str(source.apkg))
        if file_sha256(source.mapping_contract) != source.mapping_contract_sha256:
            raise InputStageError(f"mapping contract path $: mapping-contract SHA-256 mismatch for {source.mapping_contract}", file=str(source.mapping_contract))
        if config.normalization is None:
            raise InputStageError("normalization paths are required for source-map linkage")
        map_path = config.normalization.source_map
        raw_path = config.normalization.raw_notes
        source_map_bytes, source_map = read_jsonl(map_path, "source map JSONL")
        raw_notes_bytes, raw_notes = read_jsonl(raw_path, "raw source notes JSONL")
        snapshot = read_source_snapshot(
            source.apkg,
            expected_sha256=source.sha256,
            deck_ids=source.deck_ids,
            note_type_ids=source.note_type_ids,
            selection_count=source.selection_count,
            selection_native_ids=adapter.configured_native_ids(config),
        )
        adapter.validate_map_linkage(config, records, source_map, raw_notes, snapshot=snapshot)
        sidecar_hashes = {
            "source_map_sha256": hashlib.sha256(source_map_bytes).hexdigest(),
            "raw_notes_sha256": hashlib.sha256(raw_notes_bytes).hexdigest(),
        }
        source_details = {
            "source_sha256": source.sha256,
            "mapping_contract_sha256": source.mapping_contract_sha256,
            "database_member": adapter.DATABASE_MEMBER,
            "adapter": source.adapter,
            "mapping_contract_version": source.mapping_contract_version,
            "linked_records": len(source_map),
        }

    report_owner = validation_report_path(config)
    return {
        "stage": "validate-input",
        "status": "pass",
        "checked_counts": {
            "input_records": len(records),
            "unique_ids": len(records),
            "unique_expressions": len({record["expression"] for record in records}),
        },
        "input_sha256": digest,
        "input_schema": relative_reference(report_owner, schema_path),
        "input_path": relative_reference(report_owner, config.paths.source_input),
        "expected_ids": list(config.constraints.input_ids) if config.constraints.input_ids is not None else None,
        "source_linkage": source_details,
        "sidecar_hashes": sidecar_hashes,
    }


def validation_report_path(config: StageConfig) -> Path:
    if config.normalization is not None:
        return config.normalization.report.with_name("input-validation-report.json").resolve()
    assert config.paths.source_input is not None
    return config.paths.source_input.with_name("input-validation-report.json").resolve()


def publish_validation_report(path: Path, report: dict[str, Any], *, protected: set[Path]) -> None:
    resolved = path.resolve()
    if resolved in protected:
        raise InputStageError(f"input validation report path aliases a protected input: {resolved}")
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    temp_path: Path | None = None
    try:
        import tempfile

        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False) as temp:
            temp.write(payload)
            temp.flush()
            temp_path = Path(temp.name)
        temp_path.replace(path)
    except OSError as exc:
        raise OSError(f"Cannot publish input validation report {path}: {exc}") from exc
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()
