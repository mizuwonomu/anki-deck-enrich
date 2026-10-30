"""Version-2 enriched-output validation and explicit build-stage boundary."""

from __future__ import annotations

import hashlib
import re
from dataclasses import replace
from pathlib import Path
from typing import Any, Mapping

from .aggregation import protected_evidence_paths, validate_aggregate
from .config import (
    AppConfig,
    ConfigPaths,
    DatasetConstraints,
    StageConfig,
    StagePaths,
)
from .input_validation import InputStageError, validate_input_dataset
from .source_apkg import SourceError
from .validation import ValidationError, _load_json, read_jsonl, validate_records


class OutputStageError(ValidationError):
    """Controlled output-stage failure with structured CLI context."""

    def __init__(
        self,
        message: str,
        *,
        record_id: str | None = None,
        file: str | None = None,
        path: str | None = None,
    ):
        super().__init__(message, record_id=record_id, file=file, path=path)


def _wrap_validation(exc: Exception, *, file: Path) -> OutputStageError:
    if isinstance(exc, OutputStageError):
        return exc
    record_id = getattr(exc, "record_id", None)
    path = getattr(exc, "path", None)
    message = str(exc)
    record_match = re.search(r"\brecord ['\"]?([^'\" /]+)", message)
    path_match = re.search(r"\bpath (/[^ :'\"]+)", message)
    if record_match:
        record_id = record_id or record_match.group(1)
    if path_match:
        path = path or path_match.group(1)
    return OutputStageError(
        str(exc),
        record_id=record_id,
        file=getattr(exc, "file", None) or str(file),
        path=path,
    )


def contextualize_build_error(exc: Exception, *, file: Path) -> OutputStageError:
    """Attach the effective dataset path to a structured builder/render failure.

    Renderer ValueErrors are expected only when they carry its record/path
    diagnostic form. Other ValueErrors are re-raised unchanged.
    """
    if isinstance(exc, ValidationError) or re.match(r"^record \S+ path /[^:]+: .+", str(exc)):
        return _wrap_validation(exc, file=file)
    raise exc


def _required_paths(config: StageConfig) -> tuple[Path, Path, Path, Path]:
    values = (config.paths.input, config.paths.source_input, config.paths.output_schema, config.paths.input_schema)
    if any(value is None for value in values):
        raise OutputStageError("paths.input, paths.source_input, paths.output_schema, and paths.input_schema are required")
    return values  # type: ignore[return-value]


def validate_output(config: StageConfig) -> dict[str, Any]:
    """Validate normalized inputs and enriched outputs without publishing files."""
    input_path, source_path, output_schema_path, input_schema_path = _required_paths(config)
    constraints = config.constraints
    if constraints.input_ids is None or not constraints.input_ids:
        raise OutputStageError("constraints.input_ids must contain a nonempty ordered ID selection", file=str(config.config_path))
    if (constraints.revision is None and constraints.revisions is None) or constraints.schema_version is None:
        raise OutputStageError("constraints.revision or constraints.revisions and schema_version are required", file=str(config.config_path))
    aggregate_report = validate_aggregate(config) if config.aggregation is not None else None

    # Source input order is not identity for a generic v2 stage. The accepted native
    # profile still independently checks its frozen row-to-source mapping.
    input_config = config if config.source is not None else replace(config, constraints=replace(constraints, input_ids=None))
    try:
        input_report = validate_input_dataset(input_config)
    except (InputStageError, SourceError, ValidationError, OSError, ValueError) as exc:
        message = str(exc)
        if isinstance(exc, UnicodeDecodeError) or str(input_schema_path) in message:
            error_file = input_schema_path
        elif config.normalization is not None and str(config.normalization.source_map) in message:
            error_file = config.normalization.source_map
        elif config.normalization is not None and str(config.normalization.raw_notes) in message:
            error_file = config.normalization.raw_notes
        elif config.normalization is not None and "source linkage" in message:
            raw_markers = ("raw note", "/raw_notes", "/native_note", "/fields_original", "/cards")
            error_file = config.normalization.raw_notes if any(marker in message for marker in raw_markers) else config.normalization.source_map
        else:
            error_file = source_path
        raise _wrap_validation(exc, file=error_file) from exc

    try:
        source_raw, source_records = read_jsonl(source_path, "source input JSONL")
        output_raw, records = read_jsonl(input_path, "enriched JSONL")
    except ValidationError as exc:
        file_path = source_path if "source input" in str(exc) else input_path
        raise _wrap_validation(exc, file=file_path) from exc

    source_digest = hashlib.sha256(source_raw).hexdigest()
    output_digest = hashlib.sha256(output_raw).hexdigest()
    if constraints.source_input_sha256 is not None and source_digest != constraints.source_input_sha256:
        raise OutputStageError(
            f"source_input_sha256 mismatch for effective source input; expected {constraints.source_input_sha256}, got {source_digest}",
            file=str(source_path),
            path="/",
        )
    if constraints.input_sha256 is not None and output_digest != constraints.input_sha256:
        raise OutputStageError(
            f"input_sha256 mismatch for effective enriched input; expected {constraints.input_sha256}, got {output_digest}",
            file=str(input_path),
            path="/",
        )

    source_ids = [record.get("id") for record in source_records]
    expected_count = len(constraints.input_ids)
    if len(records) != expected_count:
        raise OutputStageError(
            f"enriched output dataset must contain exactly {expected_count} records, got {len(records)}",
            file=str(input_path),
            path="/input_id",
        )
    if len(source_records) != expected_count:
        raise OutputStageError(
            f"source input dataset must contain exactly {expected_count} records, got {len(source_records)}",
            file=str(source_path),
            path="/",
        )
    if set(source_ids) != set(constraints.input_ids):
        raise OutputStageError(
            "constraints.input_ids set must equal the normalized source input ID set",
            file=str(source_path),
            path="/id",
        )
    try:
        output_schema = _load_json(output_schema_path, "output schema")
    except (ValidationError, UnicodeDecodeError, OSError) as exc:
        raise _wrap_validation(exc, file=output_schema_path) from exc
    try:
        input_schema = _load_json(input_schema_path, "input schema")
    except (ValidationError, UnicodeDecodeError, OSError) as exc:
        raise _wrap_validation(exc, file=input_schema_path) from exc
    try:
        validate_records(
            records,
            source_records,
            output_schema,
            input_schema,
            output_schema_path=output_schema_path,
            input_schema_path=input_schema_path,
            expected_ids=constraints.input_ids,
            expected_revision=constraints.revision,
            expected_schema_version=constraints.schema_version,
            expected_revisions=dict(constraints.revisions) if constraints.revisions is not None else None,
        )
    except ValidationError as exc:
        message = str(exc)
        if str(output_schema_path) in message:
            error_file = output_schema_path
        elif str(input_schema_path) in message:
            error_file = input_schema_path
        elif "source input" in message:
            error_file = source_path
        else:
            error_file = input_path
        raise _wrap_validation(exc, file=error_file) from exc

    return {
        "stage": "validate-output",
        "status": "pass",
        "checked_counts": {
            "input_records": len(source_records),
            "output_records": len(records),
            "unique_ids": len(source_records),
            "unique_expressions": input_report["checked_counts"]["unique_expressions"],
            "source_linked_records": (input_report.get("source_linkage") or {}).get("linked_records", 0),
        },
        "input_sha256": output_digest,
        "source_input_sha256": source_digest,
        "input_path": str(input_path),
        "source_input_path": str(source_path),
        "output_schema": str(output_schema_path),
        "input_schema": str(input_schema_path),
        "expected_ids": list(constraints.input_ids),
        "revision": constraints.revision,
        "schema_version": constraints.schema_version,
        **({"record_revisions": dict(constraints.revisions)} if constraints.revisions is not None else {}),
        **({"aggregate_provenance_path": aggregate_report["provenance_path"]} if aggregate_report is not None else {}),
    }


def apply_stage_path_overrides(config: StageConfig, overrides: Mapping[str, Path]) -> StageConfig:
    """Apply CLI path overrides using invocation-cwd resolution semantics."""
    allowed = {"input", "source_input", "output_schema", "input_schema", "output_dir"}
    unknown = set(overrides) - allowed
    if unknown:
        raise ValueError(f"Unknown CLI path override(s): {', '.join(sorted(unknown))}")
    if not overrides:
        return config
    resolved = {key: Path(value).resolve() for key, value in overrides.items()}
    if config.aggregation is not None:
        for key, value in resolved.items():
            configured = getattr(config.paths, key)
            if key != "output_dir" and (configured is None or value != configured.resolve()):
                raise OutputStageError(f"aggregation mode does not permit overriding verified {key} path", file=str(config.config_path), path=f"/paths/{key}")
    return replace(
        config,
        paths=replace(config.paths, **resolved),
        overrides=tuple((key, str(resolved[key])) for key in sorted(resolved)),
    )


def _resolved_protected_paths(config: StageConfig) -> set[Path]:
    protected = {config.config_path.resolve()}
    # CLI overrides change effective paths, not the immutable YAML-declared
    # inputs. Protect both boundaries so --force cannot clobber either one.
    for path_set in (config.declared_paths, config.paths):
        if path_set is None:
            continue
        for candidate in (
            path_set.input,
            path_set.source_input,
            path_set.output_schema,
            path_set.input_schema,
        ):
            if candidate is not None:
                protected.add(candidate.resolve())
    if config.source is not None:
        protected.update({config.source.apkg.resolve(), config.source.mapping_contract.resolve()})
    if config.normalization is not None:
        protected.update({
            config.normalization.source_map.resolve(),
            config.normalization.raw_notes.resolve(),
            config.normalization.exceptions.resolve(),
            config.normalization.report.resolve(),
        })
    return protected


def build_targets(config: StageConfig) -> dict[str, Path]:
    """Validate target identity/collisions before any build directory is created."""
    if config.package is None or config.paths.output_dir is None:
        raise OutputStageError("package and paths.output_dir are required for build", file=str(config.config_path))
    output_dir = config.paths.output_dir
    names = {
        "apkg": config.package.apkg_filename,
        "preview": "preview.html",
        "audit": "audit.json",
    }
    targets = {key: (output_dir / name).resolve() for key, name in names.items()}
    if len(set(targets.values())) != len(targets):
        raise OutputStageError("build artifact target paths collide", file=str(config.config_path))
    protected = _resolved_protected_paths(config)
    protected.update(protected_evidence_paths(config))
    for key, target in targets.items():
        if target in protected:
            raise OutputStageError(
                f"build {key} target aliases a protected declared input: {target}",
                file=str(target),
                path="/paths/output_dir",
            )
    return targets


def app_config_for_build(config: StageConfig, *, verified_input_sha256: str | None = None) -> AppConfig:
    """Adapt validated full v2 stage config to the stable typed builder API."""
    if (
        config.package is None
        or config.paths.input is None
        or config.paths.source_input is None
        or config.paths.output_schema is None
        or config.paths.input_schema is None
        or config.paths.output_dir is None
        or config.constraints.input_ids is None
        or config.constraints.schema_version is None
        or (config.constraints.revision is None and config.constraints.revisions is None)
    ):
        raise OutputStageError("build requires complete paths, package settings, and frozen constraints", file=str(config.config_path))
    input_sha256 = config.constraints.input_sha256
    if config.aggregation is not None:
        verified = verified_input_sha256 or validate_aggregate(config)["input_sha256"]
        if input_sha256 is not None and input_sha256 != verified:
            raise OutputStageError("configured enriched hash differs from verified aggregate provenance", file=str(config.paths.input), path="/")
        input_sha256 = verified
    if input_sha256 is None:
        raise OutputStageError("build requires a frozen enriched hash or verified aggregate provenance", file=str(config.config_path))
    return AppConfig(
        paths=ConfigPaths(
            input=config.paths.input,
            source_input=config.paths.source_input,
            output_schema=config.paths.output_schema,
            input_schema=config.paths.input_schema,
            output_dir=config.paths.output_dir,
        ),
        package=config.package,
        constraints=DatasetConstraints(
            input_sha256=input_sha256,
            input_ids=config.constraints.input_ids,
            revision=config.constraints.revision,
            schema_version=config.constraints.schema_version,
            revisions=dict(config.constraints.revisions) if config.constraints.revisions is not None else None,
        ),
        config_path=config.config_path,
        config_sha256=config.config_sha256,
        overrides=config.overrides,
        stage_config=config,
    )
