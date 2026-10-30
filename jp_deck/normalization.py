"""Deterministic source normalization and named-artifact publication."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from .config import StageConfig
from .pathrefs import relative_reference
from .input_validation import (
    InputStageError,
    _schema_validator,
    protected_stage_paths,
    validate_input_objects,
)
from .source_apkg import SourceError, file_sha256, read_source_snapshot
from .sources import get_source_adapter


def _compact_line(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n"


def _schema_validator_for_config(config: StageConfig) -> Draft202012Validator:
    assert config.paths.input_schema is not None
    return _schema_validator(config.paths.input_schema)


def _all_output_paths(config: StageConfig) -> dict[str, Path]:
    assert config.normalization is not None and config.paths.source_input is not None
    return {
        "input": config.paths.source_input.resolve(),
        "source_map": config.normalization.source_map.resolve(),
        "raw_notes": config.normalization.raw_notes.resolve(),
        "exceptions": config.normalization.exceptions.resolve(),
        "report": config.normalization.report.resolve(),
    }


def _check_output_safety(config: StageConfig, *, force: bool) -> dict[str, Path]:
    outputs = _all_output_paths(config)
    if len(set(outputs.values())) != len(outputs):
        duplicates: dict[Path, list[str]] = {}
        for name, path in outputs.items():
            duplicates.setdefault(path, []).append(name)
        collision = next(names for names in duplicates.values() if len(names) > 1)
        raise SourceError(f"Normalization output path collision: {', '.join(collision)}")
    assert config.source is not None and config.paths.input_schema is not None
    protected = protected_stage_paths(config, publisher_stage="normalize")
    for name, output in outputs.items():
        if output in protected:
            raise SourceError(f"Normalization output {name} aliases a protected input: {output}")
        if output.exists():
            if output.is_dir():
                raise SourceError(f"Normalization output {name} is a directory, not a replaceable named file: {output}")
            if not force:
                raise FileExistsError(f"Normalization output already exists; use --force to replace this named output: {output}")
    validation_report = config.normalization.report.with_name("input-validation-report.json").resolve()
    if validation_report in set(outputs.values()) | protected:
        raise SourceError(f"Input-validation report path collides with another artifact or protected input: {validation_report}")
    return outputs


def _serialize_jsonl(rows: list[dict[str, Any]]) -> bytes:
    return b"".join(_compact_line(row) for row in rows)


def _publish_named_files(outputs: dict[Path, bytes], *, force: bool) -> None:
    staged: list[tuple[Path, Path]] = []
    try:
        for destination, payload in outputs.items():
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists() and not force:
                raise FileExistsError(f"Normalization output already exists; use --force: {destination}")
            if destination.exists() and destination.is_dir():
                raise SourceError(f"Cannot replace a directory with a normalization artifact: {destination}")
            with tempfile.NamedTemporaryFile(
                dir=destination.parent,
                prefix=f".{destination.name}.",
                suffix=".stage",
                delete=False,
            ) as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
                temp_path = Path(stream.name)
            staged.append((temp_path, destination))
        for temp_path, destination in staged:
            if destination.exists() and not force:
                raise FileExistsError(f"Normalization output appeared during staging; use --force: {destination}")
        for temp_path, destination in staged:
            temp_path.replace(destination)
    except OSError:
        raise
    finally:
        for temp_path, _ in staged:
            if temp_path.exists():
                temp_path.unlink()


def normalize_source(config: StageConfig, *, force: bool = False) -> dict[str, Any]:
    """Đọc nguồn đã duyệt, giữ selection cấu hình, chuyển đổi và xuất bản artifacts."""
    if config.source is None:
        raise SourceError("A registered source adapter is required for normalization")
    adapter = get_source_adapter(config.source.adapter)
    try:
        source = adapter.validate_profile_config(config)
    except adapter.MappingFailure as exc:
        raise SourceError(f"Unsupported source/config profile: {exc}") from exc
    assert config.normalization is not None and config.paths.input_schema is not None
    destinations = _check_output_safety(config, force=force)

    if file_sha256(source.apkg) != source.sha256:
        raise SourceError(f"Source APKG SHA-256 mismatch for {source.apkg}; expected {source.sha256}")
    if file_sha256(source.mapping_contract) != source.mapping_contract_sha256:
        raise SourceError(
            f"Mapping-contract SHA-256 mismatch for {source.mapping_contract}; expected {source.mapping_contract_sha256}"
        )
    snapshot = read_source_snapshot(
        source.apkg,
        expected_sha256=source.sha256,
        deck_ids=source.deck_ids,
        note_type_ids=source.note_type_ids,
        selection_count=source.selection_count,
        selection_native_ids=adapter.configured_native_ids(config),
    )
    selected_native_ids = tuple(int(note["id"]) for note in snapshot.selected_notes)
    try:
        expected_ids = adapter.validate_snapshot(config, snapshot)
    except adapter.MappingFailure as exc:
        raise SourceError(f"Source snapshot is not applicable to the selected adapter: {exc}") from exc

    projections = []
    raw_rows: list[dict[str, Any]] = []
    source_map: list[dict[str, Any]] = []
    for position, note in enumerate(snapshot.selected_notes, start=1):
        native_id = int(note["id"])
        signature = snapshot.note_types.get(int(note["mid"]), ("", ()))[1]
        try:
            projection = adapter.project_note(note, signature)
        except adapter.MappingFailure as exc:
            raise SourceError(
                f"Selected native note {native_id} is blocked ({exc.reason_code}): {exc}; no replacement is permitted"
            ) from exc
        raw = adapter.raw_note(snapshot, note, position)
        projections.append(projection.values)
        raw_rows.append(raw)
        source_map.append(adapter.source_map(config, snapshot, note, raw, position))
    validator = _schema_validator_for_config(config)
    validate_input_objects(projections, validator, expected_ids=expected_ids)
    input_bytes = _serialize_jsonl(projections)
    input_hash = hashlib.sha256(input_bytes).hexdigest()
    if config.constraints.source_input_sha256 is not None and input_hash != config.constraints.source_input_sha256:
        raise SourceError(
            f"Normalized input hash disagrees with constraints.source_input_sha256: {input_hash}"
        )
    adapter.validate_map_linkage(config, projections, source_map, raw_rows, snapshot=snapshot)

    selected_set = set(selected_native_ids)
    exceptions: list[dict[str, Any]] = []
    eligible_unselected = 0
    for note in snapshot.scoped_notes:
        native_id = int(note["id"])
        if native_id in selected_set:
            continue
        signature = snapshot.note_types.get(int(note["mid"]), ("", ()))[1]
        try:
            candidate = adapter.project_note(note, signature)
            validate_input_objects([candidate.values], validator, expected_ids=None)
            eligible_unselected += 1
        except adapter.MappingFailure as exc:
            exceptions.append(adapter.exception_for(note, signature, exc, selected=False))
        except InputStageError as exc:
            exceptions.append(
                adapter.exception_for(note, signature, adapter.MappingFailure("input_schema_rejection", str(exc)), selected=False)
            )

    exception_doc = {
        "source_sha256": snapshot.sha256,
        "database_member": snapshot.database_member,
        "selection_order": "note_id_ascending",
        "selection_count": len(selected_native_ids),
        "selected_native_note_ids": list(selected_native_ids),
        "selected_project_ids": list(expected_ids),
        "selected_blocker_count": 0,
        "scope_note_count": snapshot.scoped_note_count,
        "unselected_note_count": snapshot.scoped_note_count - len(selected_native_ids),
        "selected_card_count": sum(len(snapshot.selected_cards[native_id]) for native_id in selected_native_ids),
        "unselected_note_ids": [
            int(note["id"]) for note in snapshot.scoped_notes if int(note["id"]) not in selected_set
        ],
        "eligible_unselected_count": eligible_unselected,
        "ineligible_unselected_count": len(exceptions),
        "unselected_assessment": "bounded deterministic mapping eligibility only; not linguistic certification",
        "exceptions": exceptions,
    }
    exception_bytes = (json.dumps(exception_doc, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    source_map_bytes = _serialize_jsonl(source_map)
    raw_bytes = _serialize_jsonl(raw_rows)
    report = {
        "stage": "normalize",
        "status": "pass",
        "source": {
            "path": relative_reference(destinations["report"], snapshot.path),
            "sha256": snapshot.sha256,
            "database_member": snapshot.database_member,
            "collection_version": snapshot.collection_version,
            "target_deck_ids": list(source.deck_ids),
            "supported_note_type_ids": list(source.note_type_ids),
            "mapping_contract": relative_reference(destinations["report"], source.mapping_contract),
            "mapping_contract_version": source.mapping_contract_version,
            "mapping_contract_sha256": source.mapping_contract_sha256,
        },
        "selection": {
            "order": "note_id_ascending",
            "selected_native_note_ids": list(selected_native_ids),
            "selected_project_ids": list(expected_ids),
            "scope_note_count": snapshot.scoped_note_count,
            "unselected_note_count": snapshot.scoped_note_count - len(selected_native_ids),
        },
        "config_sha256": config.config_sha256,
        "checked_counts": {
            "normalized_inputs": len(projections),
            "source_map_rows": len(source_map),
            "raw_note_rows": len(raw_rows),
            "selected_cards": sum(len(snapshot.selected_cards[native_id]) for native_id in selected_native_ids),
            "selected_blockers": 0,
            "unselected_note_count": snapshot.scoped_note_count - len(selected_native_ids),
            "eligible_unselected": eligible_unselected,
            "ineligible_unselected": len(exceptions),
            "source_notes_total": snapshot.all_note_count,
            "source_cards_total": snapshot.all_card_count,
        },
        "artifacts": {name: relative_reference(destinations["report"], path) for name, path in destinations.items()},
        "sha256": {
            "input": input_hash,
            "source_map": hashlib.sha256(source_map_bytes).hexdigest(),
            "raw_notes": hashlib.sha256(raw_bytes).hexdigest(),
            "exceptions": hashlib.sha256(exception_bytes).hexdigest(),
        },
    }
    report_bytes = (json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    payloads = {
        destinations["input"]: input_bytes,
        destinations["source_map"]: source_map_bytes,
        destinations["raw_notes"]: raw_bytes,
        destinations["exceptions"]: exception_bytes,
        destinations["report"]: report_bytes,
    }
    _publish_named_files(payloads, force=force)
    return report
