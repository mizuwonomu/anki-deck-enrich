"""Reusable, hash-bound acceptance and deterministic aggregation of enriched batches."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from .config import StageConfig
from .input_validation import _schema_validator, validate_input_dataset, validate_input_objects
from .pathrefs import relative_reference
from .render import render_record
from .audit import audit_rendered_record
from .source_apkg import file_sha256
from .sources import get_source_adapter
from .validation import ValidationError, _load_json, read_jsonl, resolve_json_pointer, validate_records

MANIFEST_SCHEMA = "jp-deck-batch-manifest/v2"
LEGACY_MANIFEST_SCHEMA = "jp-deck-batch-manifest/v1"
ACCEPTANCE_SCHEMA = "jp-deck-batch-acceptance/v1"
VALIDATION_SCHEMA = "jp-deck-batch-output-validation/v1"
REVIEW_SCHEMA = "jp-deck-batch-review/v1"
HUMAN_DISPOSITION_SCHEMA = "jp-deck-human-disposition/v1"
PROVENANCE_SCHEMA = "jp-deck-aggregate-provenance/v2"
LEGACY_PROVENANCE_SCHEMA = "jp-deck-aggregate-provenance/v1"
REPORT_SCHEMA = "jp-deck-aggregate-report/v2"
LEGACY_REPORT_SCHEMA = "jp-deck-aggregate-report/v1"
STRICT_REVIEW_SCOPE = "structure-and-collocation-attestation/v1"
SAMPLED_REVIEW_SCOPE = "schema-first-sampled-source/v1"
SERIALIZATION = "jsonl-utf8-compact-ensure-ascii-false-v1"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
INTERCHANGE_SCHEMAS = {
    "validation": PROJECT_ROOT / "schemas/batch-output-validation.schema.json",
    "review": PROJECT_ROOT / "schemas/batch-review.schema.json",
    "acceptance": PROJECT_ROOT / "schemas/batch-acceptance.schema.json",
    "human_disposition": PROJECT_ROOT / "schemas/human-disposition.schema.json",
    "provenance": PROJECT_ROOT / "schemas/aggregate-provenance.schema.json",
    "aggregate_report": PROJECT_ROOT / "schemas/aggregate-report.schema.json",
}
_HASH = re.compile(r"^[0-9a-f]{64}$")


class AggregationError(ValidationError):
    """Controlled aggregation/evidence error with CLI-serializable context."""

    def __init__(self, message: str, *, file: Path | str | None = None,
                 record_id: str | None = None, path: str | None = None):
        super().__init__(message, file=str(file) if file is not None else None,
                         record_id=record_id, path=path)


@dataclass(frozen=True)
class BatchEvidence:
    batch_id: str
    input_path: Path
    input_sha256: str
    input_ids: tuple[str, ...]
    output_path: Path
    output_sha256: str
    artifact_revision: int
    record_revisions: dict[str, int]
    validation_path: Path
    validation_sha256: str
    review_path: Path
    review_sha256: str
    acceptance_path: Path
    acceptance_sha256: str
    records: list[dict[str, Any]]
    input_records: list[dict[str, Any]]


@dataclass(frozen=True)
class AggregationContext:
    config: StageConfig
    manifest: dict[str, Any]
    manifest_sha256: str
    master: list[dict[str, Any]]
    master_sha256: str
    input_schema_sha256: str
    output_schema_sha256: str
    contract_sha256: str
    native_source_linkage: dict[str, Any]
    batches: tuple[BatchEvidence, ...]


def _fail(message: str, *, file: Path | str | None = None,
          record_id: str | None = None, path: str | None = None) -> None:
    raise AggregationError(message, file=file, record_id=record_id, path=path)


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _present(path: Path) -> bool:
    return path.exists() or path.is_symlink()


def _is_hash(value: Any) -> bool:
    return isinstance(value, str) and _HASH.fullmatch(value) is not None


def _valid_id(value: Any) -> bool:
    return (isinstance(value, str) and bool(value.strip()) and value == value.strip()
            and not any(ord(char) < 0x20 or ord(char) == 0x7F for char in value))


def _object(value: Any, *, what: str, path: Path, required: set[str], optional: set[str] = frozenset()) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail(f"{what} must be an object", file=path)
    missing = required - set(value)
    unknown = set(value) - required - set(optional)
    if missing:
        _fail(f"{what} is missing required field(s): {', '.join(sorted(missing))}", file=path)
    if unknown:
        _fail(f"{what} has unsupported field(s): {', '.join(sorted(unknown))}", file=path)
    return value


def _string(value: Any, *, what: str, file: Path, path: str | None = None) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail(f"{what} must be a non-blank string", file=file, path=path)
    return value


def _positive_int(value: Any, *, what: str, file: Path, path: str | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        _fail(f"{what} must be a positive integer", file=file, path=path)
    return value


def _resolve_reference(value: Any, *, declaring_file: Path, what: str) -> Path:
    raw = _string(value, what=what, file=declaring_file)
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = declaring_file.parent / candidate
    return candidate.resolve()


def _read_json(path: Path, what: str) -> tuple[bytes, Any]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        _fail(f"cannot read {what} at {path}: {exc.strerror or exc}", file=path)
    try:
        value = json.loads(raw.decode("utf-8"))
    except UnicodeDecodeError as exc:
        _fail(f"{what} at {path} is not strict UTF-8 at byte {exc.start}", file=path)
    except json.JSONDecodeError as exc:
        _fail(f"invalid {what} JSON at {path}:{exc.lineno}:{exc.colno}: {exc.msg}", file=path)
    return raw, value


def _validate_interchange(value: Any, *, schema_name: str, what: str, file: Path) -> None:
    schema_path = INTERCHANGE_SCHEMAS[schema_name]
    schema = _load_json(schema_path, f"{what} interchange schema")
    try:
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        errors = sorted(validator.iter_errors(value), key=lambda err: (list(map(str, err.absolute_path)), err.message))
    except Exception as exc:
        _fail(f"invalid {what} interchange schema {schema_path}: {exc}", file=schema_path)
    if errors:
        error = errors[0]
        pointer = "/" + "/".join(str(item) for item in error.absolute_path) if error.absolute_path else "/"
        _fail(f"malformed {what} at {file} path {pointer}: {error.message}", file=file, path=pointer)


def _read_manifest(config: StageConfig) -> tuple[dict[str, Any], str, list[dict[str, Any]], bytes, dict[str, Any], list[dict[str, Any]], str, str, str]:
    aggregation = config.aggregation
    if aggregation is None or config.paths.source_input is None or config.paths.input_schema is None:
        _fail("aggregation, paths.source_input and paths.input_schema are required", file=config.config_path)
    raw, value = _read_json(aggregation.manifest_path, "frozen input manifest")
    digest = _sha(raw)
    if digest != aggregation.manifest_sha256:
        _fail(f"manifest SHA-256 mismatch: expected {aggregation.manifest_sha256}, got {digest}", file=aggregation.manifest_path, path="/")
    manifest_path = aggregation.manifest_path
    manifest = _object(value, what="batch manifest", path=manifest_path,
                       required={"schema", "job_id", "config", "source", "mapping", "schemas", "master", "provenance", "selection", "batch_size", "batches"})
    if manifest["schema"] not in {MANIFEST_SCHEMA, LEGACY_MANIFEST_SCHEMA}:
        _fail(f"unsupported manifest schema {manifest['schema']!r}", file=manifest_path, path="/schema")
    _string(manifest["job_id"], what="manifest job_id", file=manifest_path, path="/job_id")
    batch_size = _positive_int(manifest["batch_size"], what="manifest batch_size", file=manifest_path, path="/batch_size")
    config_doc = _object(manifest["config"], what="manifest config", path=manifest_path,
                         required={"config_path", "config_sha256", "source_input", "input_schema", "input_ids", "batch_size"},
                         optional={"source_sha256", "source_apkg", "adapter", "deck_ids", "note_type_ids", "mapping_contract",
                                   "mapping_contract_version", "mapping_contract_sha256", "selection_order", "selection_count",
                                   "output_dir", "source_map", "raw_notes"})
    if not _is_hash(config_doc["config_sha256"]):
        _fail("manifest config_sha256 must be a lowercase SHA-256", file=manifest_path, path="/config/config_sha256")
    config_batch_size = _positive_int(config_doc["batch_size"], what="manifest config batch_size",
                                      file=manifest_path, path="/config/batch_size")
    if config_batch_size != batch_size:
        _fail("manifest config batch_size contradicts the top-level batch_size", file=manifest_path, path="/config/batch_size")
    config_ids = config_doc["input_ids"]
    if not isinstance(config_ids, list) or not config_ids or any(not _valid_id(item) for item in config_ids):
        _fail("manifest config input_ids must be a nonempty list of nonblank strings", file=manifest_path, path="/config/input_ids")
    if len(config_ids) != len(set(config_ids)):
        _fail("manifest config input_ids contains duplicates", file=manifest_path, path="/config/input_ids")
    frozen_config_path = _resolve_reference(config_doc["config_path"], declaring_file=manifest_path, what="manifest config_path")
    try:
        frozen_config_raw = frozen_config_path.read_bytes()
    except OSError as exc:
        _fail(f"cannot read frozen batch configuration {frozen_config_path}: {exc.strerror or exc}", file=frozen_config_path)
    if _sha(frozen_config_raw) != config_doc["config_sha256"]:
        _fail("manifest frozen batch config SHA-256 mismatch", file=frozen_config_path, path="/")

    selection = _object(manifest["selection"], what="manifest selection", path=manifest_path, required={"order", "input_ids"})
    order = _string(selection["order"], what="manifest selection order", file=manifest_path, path="/selection/order")
    ids = selection["input_ids"]
    if not isinstance(ids, list) or not ids or any(not _valid_id(item) for item in ids):
        _fail("manifest selection input_ids must be a nonempty string list", file=manifest_path, path="/selection/input_ids")
    if len(ids) != len(set(ids)):
        _fail("manifest selection input_ids contains duplicates", file=manifest_path, path="/selection/input_ids")
    if ids != config_ids:
        _fail("manifest config input_ids differ from frozen selection order", file=manifest_path, path="/config/input_ids")
    if config.constraints.input_ids is None or tuple(ids) != config.constraints.input_ids:
        _fail("constraints.input_ids do not match manifest selection in order", file=config.config_path, path="/constraints/input_ids")

    master_binding = _object(manifest["master"], what="manifest master", path=manifest_path, required={"path", "sha256", "count"})
    master_path = _resolve_reference(master_binding["path"], declaring_file=manifest_path, what="manifest master path")
    config_master_path = _resolve_reference(config_doc["source_input"], declaring_file=manifest_path, what="manifest config source_input")
    configured_master_path = config.paths.source_input.resolve()
    if master_path != config_master_path or master_path != configured_master_path:
        _fail("manifest master/config source_input does not equal configured paths.source_input", file=manifest_path, path="/master/path")
    if not _is_hash(master_binding["sha256"]):
        _fail("manifest master SHA-256 is malformed", file=manifest_path, path="/master/sha256")
    master_count = _positive_int(master_binding["count"], what="manifest master count", file=manifest_path, path="/master/count")
    if master_count != len(ids):
        _fail("manifest master count differs from ordered selection", file=manifest_path, path="/master/count")
    master_raw, master = read_jsonl(master_path, "normalized master JSONL")
    master_sha256 = _sha(master_raw)
    if master_sha256 != master_binding["sha256"]:
        _fail("manifest master complete-file SHA-256 differs from actual master", file=master_path, path="/")
    if config.constraints.source_input_sha256 and master_sha256 != config.constraints.source_input_sha256:
        _fail("constraints.source_input_sha256 differs from frozen master", file=master_path, path="/")
    input_validator = _schema_validator(config.paths.input_schema)
    validate_input_objects(master, input_validator, expected_ids=tuple(ids), file=master_path)
    master_actual_ids = [record["id"] for record in master]
    if master_actual_ids != ids:
        _fail("normalized master order differs from manifest selection", file=master_path, path="/id")

    schemas = _object(manifest["schemas"], what="manifest schemas", path=manifest_path, required={"input_sha256"})
    if not _is_hash(schemas["input_sha256"]):
        _fail("manifest input schema SHA-256 is malformed", file=manifest_path, path="/schemas/input_sha256")
    input_schema_sha256 = file_sha256(config.paths.input_schema)
    output_schema_sha256 = file_sha256(config.paths.output_schema) if config.paths.output_schema else ""
    if schemas["input_sha256"] != input_schema_sha256:
        _fail("manifest input schema fingerprint differs from configured schema bytes", file=manifest_path, path="/schemas/input_sha256")
    if _resolve_reference(config_doc["input_schema"], declaring_file=manifest_path, what="manifest config input_schema") != config.paths.input_schema.resolve():
        _fail("manifest config input_schema path differs from configured schema", file=manifest_path, path="/config/input_schema")

    native = _validate_source_boundary(config, manifest, manifest_path)
    batches_doc = manifest["batches"]
    if not isinstance(batches_doc, list) or not batches_doc:
        _fail("manifest batches must be a nonempty ordered list", file=manifest_path, path="/batches")
    seen_batch_ids: set[str] = set()
    seen_batch_paths: set[Path] = set()
    seen_members: list[str] = []
    member_owners: dict[str, str] = {}
    checked_batches: list[dict[str, Any]] = []
    master_by_id = {record["id"]: record for record in master}
    for index, batch in enumerate(batches_doc):
        prefix = f"/batches/{index}"
        batch = _object(batch, what=f"manifest batch {index + 1}", path=manifest_path,
                        required={"batch_id", "path", "input_ids", "count", "sha256"})
        batch_id = _string(batch["batch_id"], what="batch_id", file=manifest_path, path=f"{prefix}/batch_id")
        if not _valid_id(batch_id):
            _fail("manifest batch_id contains whitespace padding or control characters", file=manifest_path, path=f"{prefix}/batch_id")
        if batch_id in seen_batch_ids:
            _fail(f"manifest contains duplicate batch_id {batch_id!r}", file=manifest_path, path=f"{prefix}/batch_id")
        seen_batch_ids.add(batch_id)
        batch_path = _resolve_reference(batch["path"], declaring_file=manifest_path, what=f"manifest batch {batch_id} path")
        if batch_path in seen_batch_paths:
            _fail(f"manifest batch {batch_id} aliases another input artifact", file=manifest_path, path=f"{prefix}/path")
        seen_batch_paths.add(batch_path)
        members = batch["input_ids"]
        if not isinstance(members, list) or not members or any(not _valid_id(item) for item in members):
            _fail(f"manifest batch {batch_id} input_ids must be a nonempty string list", file=manifest_path, path=f"{prefix}/input_ids")
        if len(members) != len(set(members)):
            _fail(f"manifest batch {batch_id} contains duplicate IDs", file=manifest_path, path=f"{prefix}/input_ids")
        count = _positive_int(batch["count"], what=f"manifest batch {batch_id} count", file=manifest_path, path=f"{prefix}/count")
        if count != len(members) or count > batch_size:
            _fail(f"manifest batch {batch_id} count does not match membership or exceeds batch_size", file=manifest_path, path=f"{prefix}/count")
        if not _is_hash(batch["sha256"]):
            _fail(f"manifest batch {batch_id} SHA-256 is malformed", file=manifest_path, path=f"{prefix}/sha256")
        overlap = [(member, member_owners[member]) for member in members if member in member_owners]
        if overlap:
            member, previous_batch = overlap[0]
            _fail(f"manifest batch overlap duplicates input_id {member!r} across {previous_batch} and {batch_id}", file=manifest_path,
                  record_id=member, path=f"{prefix}/input_ids")
        expected_members = ids[len(seen_members):len(seen_members) + count]
        if members != expected_members:
            _fail(f"manifest batch {batch_id} membership/order differs from frozen selection at offset {len(seen_members)}", file=manifest_path, path=f"{prefix}/input_ids")
        seen_members.extend(members)
        member_owners.update({member: batch_id for member in members})
        input_raw, input_records = read_jsonl(batch_path, f"{batch_id} normalized input JSONL")
        if _sha(input_raw) != batch["sha256"]:
            _fail(f"batch {batch_id} input SHA-256 mismatch", file=batch_path, path="/")
        validate_input_objects(input_records, input_validator, expected_ids=tuple(members), file=batch_path, batch_id=batch_id)
        for line_number, record in enumerate(input_records, start=1):
            input_id = record["id"]
            if input_id not in master_by_id:
                _fail(f"batch {batch_id} line {line_number} has foreign input ID {input_id!r}", file=batch_path, record_id=input_id, path="/id")
            for field in ("id", "expression", "reading", "meaning_vi"):
                if record.get(field) != master_by_id[input_id].get(field):
                    _fail(f"batch {batch_id} line {line_number} input {input_id} path /{field} differs from frozen master", file=batch_path, record_id=input_id, path=f"/{field}")
        checked_batches.append({"manifest": batch, "input_path": batch_path, "input_sha256": batch["sha256"], "input_records": input_records})
    if seen_members != ids:
        missing = [item for item in ids if item not in seen_members]
        foreign = [item for item in seen_members if item not in set(ids)]
        _fail(f"manifest batch union differs from frozen selection (missing={missing}, foreign={foreign})", file=manifest_path, path="/batches")
    if len(seen_members) != len(set(seen_members)):
        duplicates = [item for item, count in Counter(seen_members).items() if count > 1]
        _fail(f"manifest batch memberships overlap: {duplicates}", file=manifest_path, path="/batches")
    return manifest, digest, master, master_raw, native, checked_batches, input_schema_sha256, output_schema_sha256, master_sha256


def _validate_source_boundary(config: StageConfig, manifest: dict[str, Any], manifest_path: Path) -> dict[str, Any]:
    source = manifest["source"]
    mapping = manifest["mapping"]
    provenance = manifest["provenance"]
    if not isinstance(provenance, dict) or set(provenance) != {"source_map", "raw_notes"}:
        _fail("manifest provenance has an invalid shape", file=manifest_path, path="/provenance")
    if source is None:
        native_config_keys = {"source_sha256", "source_apkg", "adapter", "deck_ids", "note_type_ids",
                              "mapping_contract", "mapping_contract_version", "mapping_contract_sha256",
                              "selection_order", "selection_count", "source_map", "raw_notes"}
        if mapping is not None or provenance["source_map"] is not None or provenance["raw_notes"] is not None:
            _fail("generic normalized-source manifest must not claim native/APKG or source-map linkage", file=manifest_path, path="/source")
        if native_config_keys.intersection(manifest["config"]):
            _fail("generic normalized-source manifest config must not claim native/APKG linkage", file=manifest_path, path="/config")
        if config.source is not None:
            _fail("configured native source profile is absent from frozen manifest", file=manifest_path, path="/source")
        return {"verified": False, "evidence": {"kind": "normalized-master-only"}}
    if not isinstance(source, dict) or set(source) != {"path", "sha256", "database_member"}:
        _fail("manifest source binding has an invalid shape", file=manifest_path, path="/source")
    _string(source["database_member"], what="manifest source database_member", file=manifest_path, path="/source/database_member")
    if not isinstance(mapping, dict) or set(mapping) != {"path", "version", "sha256"}:
        _fail("manifest mapping binding has an invalid shape", file=manifest_path, path="/mapping")
    _string(mapping["version"], what="manifest mapping version", file=manifest_path, path="/mapping/version")
    if not isinstance(provenance, dict) or set(provenance) != {"source_map", "raw_notes"}:
        _fail("manifest provenance has an invalid shape", file=manifest_path, path="/provenance")
    if config.source is None or config.normalization is None:
        _fail("native source-backed manifest requires the configured accepted source profile and sidecars", file=manifest_path, path="/source")
    adapter = get_source_adapter(config.source.adapter)
    if source["database_member"] != adapter.DATABASE_MEMBER:
        _fail("manifest source database_member differs from the configured adapter's selected database member",
              file=manifest_path, path="/source/database_member")
    if mapping["version"] != config.source.mapping_contract_version:
        _fail("manifest mapping version differs from the configured accepted mapping contract",
              file=manifest_path, path="/mapping/version")
    if manifest["selection"]["order"] != config.source.selection_order:
        _fail("manifest selection order differs from the configured accepted source profile",
              file=manifest_path, path="/selection/order")
    config_doc = manifest["config"]
    if "selection_count" not in config_doc:
        _fail("source-backed manifest config requires selection_count", file=manifest_path, path="/config/selection_count")
    _positive_int(config_doc["selection_count"], what="manifest config selection_count", file=manifest_path, path="/config/selection_count")
    for list_key in ("deck_ids", "note_type_ids"):
        values = config_doc.get(list_key)
        if not isinstance(values, list) or not values or any(isinstance(item, bool) or not isinstance(item, int) or item <= 0 for item in values):
            _fail(f"manifest config {list_key} must be a nonempty positive-integer list", file=manifest_path, path=f"/config/{list_key}")
    for key, binding in (("source", source), ("mapping", mapping)):
        path_value = binding.get("path")
        digest_value = binding.get("sha256")
        if not isinstance(path_value, str) or not _is_hash(digest_value):
            _fail(f"manifest {key} path/hash binding is invalid", file=manifest_path, path=f"/{key}")
        artifact_path = _resolve_reference(path_value, declaring_file=manifest_path, what=f"manifest {key} path")
        if file_sha256(artifact_path) != digest_value:
            _fail(f"manifest {key} artifact SHA-256 mismatch", file=artifact_path, path="/")
    for name in ("source_map", "raw_notes"):
        item = provenance[name]
        if not isinstance(item, dict) or set(item) != {"path", "sha256"} or not isinstance(item.get("path"), str) or not _is_hash(item.get("sha256")):
            _fail(f"manifest provenance {name} binding is invalid", file=manifest_path, path=f"/provenance/{name}")
        sidecar = _resolve_reference(item["path"], declaring_file=manifest_path, what=f"manifest provenance {name} path")
        if file_sha256(sidecar) != item["sha256"]:
            _fail(f"manifest provenance {name} SHA-256 mismatch", file=sidecar, path="/")
    expected_bindings = (
        (source["path"], config.source.apkg), (source["sha256"], config.source.sha256),
        (mapping["path"], config.source.mapping_contract), (mapping["sha256"], config.source.mapping_contract_sha256),
        (provenance["source_map"]["path"], config.normalization.source_map),
        (provenance["source_map"]["sha256"], file_sha256(config.normalization.source_map)),
        (provenance["raw_notes"]["path"], config.normalization.raw_notes),
        (provenance["raw_notes"]["sha256"], file_sha256(config.normalization.raw_notes)),
    )
    for actual, expected in expected_bindings:
        if isinstance(expected, Path):
            if _resolve_reference(actual, declaring_file=manifest_path, what="manifest source path") != expected.resolve():
                _fail("manifest native source path differs from configured accepted profile", file=manifest_path, path="/source")
        elif actual != expected:
            _fail("manifest native source hash differs from configured accepted profile", file=manifest_path, path="/source")
    related = (
        ("source_apkg", source["path"]), ("source_sha256", source["sha256"]),
        ("mapping_contract", mapping["path"]), ("mapping_contract_version", config.source.mapping_contract_version),
        ("mapping_contract_sha256", mapping["sha256"]),
        ("selection_order", config.source.selection_order),
        ("selection_count", len(manifest["selection"]["input_ids"])),
        ("source_map", provenance["source_map"]["path"]), ("raw_notes", provenance["raw_notes"]["path"]),
        ("adapter", config.source.adapter), ("deck_ids", list(config.source.deck_ids)),
        ("note_type_ids", list(config.source.note_type_ids)),
    )
    for key, expected_value in related:
        if key in {"source_apkg", "mapping_contract", "source_map", "raw_notes"}:
            same = _resolve_reference(config_doc.get(key), declaring_file=manifest_path, what=f"manifest config {key}") == _resolve_reference(expected_value, declaring_file=manifest_path, what=f"manifest {key}")
        else:
            same = config_doc.get(key) == expected_value
        if not same:
            _fail(f"manifest config {key} contradicts its source/membership binding", file=manifest_path, path=f"/config/{key}")
    if config.source.selection_count != len(config.constraints.input_ids or ()):
        _fail("configured native selection count differs from the complete ordered master", file=config.config_path, path="/source/selection/count")
    try:
        input_report = validate_input_dataset(config)
    except (ValidationError, OSError, ValueError) as exc:
        _fail(f"native source linkage validation failed: {exc}", file=getattr(exc, "file", None) or config.config_path,
              record_id=getattr(exc, "record_id", None), path=getattr(exc, "path", None))
    return {"verified": True, "evidence": {"source_path": str(config.source.apkg.resolve()),
                                              "source_sha256": config.source.sha256,
                                              "linked_records": input_report["checked_counts"]["input_records"]}}


def _read_revision_map(value: Any, *, ids: tuple[str, ...], what: str, file: Path) -> dict[str, int]:
    if not isinstance(value, dict):
        _fail(f"{what} must be an object mapping every assigned input ID to a revision", file=file)
    if set(value) != set(ids):
        missing = [item for item in ids if item not in value]
        extra = sorted(set(value) - set(ids))
        _fail(f"{what} is not exact (missing={missing}, extra={extra})", file=file)
    result: dict[str, int] = {}
    for input_id in ids:
        result_value = value[input_id]
        if isinstance(result_value, bool) or not isinstance(result_value, int) or result_value <= 0:
            _fail(f"{what}.{input_id} must be a positive integer revision", file=file, record_id=input_id, path=f"/{input_id}")
        result[input_id] = result_value
    return result


def _path_binding(obj: Any, *, owner: Path, label: str) -> tuple[Path, str]:
    if not isinstance(obj, dict) or not {"path", "sha256"}.issubset(obj):
        _fail(f"{label} binding must contain path and sha256", file=owner)
    path = _resolve_reference(obj["path"], declaring_file=owner, what=f"{label} path")
    digest = obj["sha256"]
    if not _is_hash(digest):
        _fail(f"{label} SHA-256 must be 64 lowercase hexadecimal characters", file=owner)
    return path, digest


def _check_binding(obj: Any, *, owner: Path, label: str, expected_path: Path, expected_hash: str) -> Path:
    path, digest = _path_binding(obj, owner=owner, label=label)
    if path != expected_path.resolve():
        _fail(f"{label} path does not bind the expected artifact {expected_path.resolve()}", file=owner)
    if digest != expected_hash:
        _fail(f"{label} declared SHA-256 does not match frozen binding", file=owner)
    try:
        actual = file_sha256(path)
    except OSError as exc:
        _fail(f"cannot hash {label} at {path}: {exc.strerror or exc}", file=path)
    if actual != digest:
        _fail(f"{label} actual SHA-256 mismatch", file=path, path="/")
    return path


def _check_report_coverage(
    report: dict[str, Any], *, batch_id: str, ids: tuple[str, ...], revisions: dict[str, int],
    output_path: Path, output_sha256: str, input_path: Path, input_sha256: str,
    input_schema_sha256: str, output_schema_sha256: str, schema_version: str,
    file: Path,
) -> None:
    if report["schema"] != VALIDATION_SCHEMA or report["status"] != "pass":
        _fail("validation report must be a passing jp-deck-batch-output-validation/v1 report", file=file)
    if report["batch_id"] != batch_id:
        _fail("validation report batch_id differs from its acceptance", file=file)
    if _resolve_reference(report["artifact_path"], declaring_file=file, what="validation artifact_path") != output_path:
        _fail("validation report artifact_path does not bind accepted output", file=file)
    if report["artifact_sha256"] != output_sha256:
        _fail("validation report artifact_sha256 is stale or mismatched", file=file)
    if _resolve_reference(report["input_path"], declaring_file=file, what="validation input_path") != input_path:
        _fail("validation report input_path does not bind frozen batch input", file=file)
    if report["input_sha256"] != input_sha256 or report["input_ids"] != list(ids):
        _fail("validation report input hash or ordered ID coverage differs from frozen batch", file=file)
    if report["record_revisions"] != revisions:
        _fail("validation report record_revisions differ from accepted output revisions", file=file)
    if report["schema_version"] != schema_version:
        _fail("validation report schema_version differs from configured schema version", file=file)
    if report["schemas"] != {"input_sha256": input_schema_sha256, "output_sha256": output_schema_sha256}:
        _fail("validation report schema fingerprints differ from actual schema bytes", file=file)
    if report["checks"] != {"schema": True, "membership": True, "references": True, "render": True}:
        _fail("validation report must record all four checks as actually passing", file=file)
    if not isinstance(report["command"], str) or not report["command"].strip():
        _fail("validation report command must identify the executed check", file=file)


def _actual_items(record: dict[str, Any], collection: str) -> dict[str, dict[str, Any]]:
    key = "collocation_id" if collection == "collocations" else "example_id"
    return {item[key]: item for item in record[collection]}


def _validate_review(
    review: dict[str, Any], *, config: StageConfig, batch_id: str, ids: tuple[str, ...],
    revisions: dict[str, int], records: list[dict[str, Any]], output_path: Path,
    output_sha256: str, review_path: Path,
) -> None:
    if review["schema"] != REVIEW_SCHEMA or review["batch_id"] != batch_id:
        _fail("review report schema or batch identity is invalid", file=review_path)
    if review["scope"] != config.aggregation.review_scope:
        _fail("review report scope differs from explicitly configured aggregation.review_scope", file=review_path, path="/scope")
    if review["verdict"] != "pass":
        _fail(f"review verdict {review['verdict']!r} does not permit acceptance", file=review_path, path="/verdict")
    if _resolve_reference(review["artifact_path"], declaring_file=review_path, what="review artifact_path") != output_path:
        _fail("review report artifact_path does not bind accepted output", file=review_path)
    if review["artifact_sha256"] != output_sha256:
        _fail("review report artifact_sha256 is stale or mismatched", file=review_path)
    review_records = review["records"]
    if not isinstance(review_records, list) or len(review_records) != len(ids):
        _fail("review report must contain exactly one record entry per assigned input ID", file=review_path, path="/records")
    seen: list[str] = []
    record_by_id = {record["input_id"]: record for record in records}
    for index, entry in enumerate(review_records):
        input_id = entry["input_id"]
        if input_id in seen:
            _fail(f"review report contains duplicate input_id {input_id!r}", file=review_path, record_id=input_id, path=f"/records/{index}/input_id")
        seen.append(input_id)
        if input_id not in record_by_id:
            _fail(f"review report contains foreign input_id {input_id!r}", file=review_path, record_id=input_id, path=f"/records/{index}/input_id")
        if entry["reviewed_revision"] != revisions[input_id]:
            _fail(f"reviewed_revision for {input_id} differs from accepted output", file=review_path, record_id=input_id, path=f"/records/{index}/reviewed_revision")
        if entry["verdict"] != "pass" or entry["structure"]["status"] != "pass":
            _fail(f"review record {input_id} does not pass structural review", file=review_path, record_id=input_id, path=f"/records/{index}")
        actual = record_by_id[input_id]
        expected_collocations = {item["collocation_id"] for item in actual["collocations"]}
        collocations = entry["collocations"]
        if len(collocations) != len(expected_collocations):
            _fail(f"review collocation coverage is incomplete for {input_id}", file=review_path, record_id=input_id, path=f"/records/{index}/collocations")
        seen_collocations: set[str] = set()
        status_by_id: dict[str, dict[str, Any]] = {}
        for collocation in collocations:
            collocation_id = collocation["collocation_id"]
            if collocation_id in seen_collocations:
                _fail(f"duplicate review collocation_id {collocation_id!r}", file=review_path, record_id=input_id, path=f"/records/{index}/collocations")
            seen_collocations.add(collocation_id)
            if collocation_id not in expected_collocations:
                _fail(f"foreign review collocation_id {collocation_id!r}", file=review_path, record_id=input_id, path=f"/records/{index}/collocations")
            status_by_id[collocation_id] = collocation
            if collocation["queries_used"] < len(collocation["queries"]):
                _fail(f"collocation {collocation_id} query count is smaller than its recorded queries", file=review_path, record_id=input_id)
            if collocation["status"] == "contradicted":
                _fail(f"unresolved contradicted collocation claim for {input_id}/{collocation_id}", file=review_path, record_id=input_id)
            _validate_attestation(collocation["status"], collocation["source_url"], collocation["observation"],
                                  where=f"{input_id}/{collocation_id}", file=review_path)
        if seen_collocations != expected_collocations:
            _fail(f"review collocation IDs do not exactly cover {input_id}", file=review_path, record_id=input_id)
        for finding_index, finding in enumerate(entry["findings"]):
            severity = finding.get("severity", "error")
            if severity not in {"error", "advisory"}:
                _fail("review finding severity must be error or advisory", file=review_path, record_id=input_id, path=f"/records/{index}/findings/{finding_index}/severity")
            try:
                resolve_json_pointer(actual, finding["path"], context=f"review finding {input_id}")
            except ValidationError as exc:
                _fail(str(exc), file=review_path, record_id=input_id, path=finding["path"])
            if severity == "error":
                _fail(f"unresolved error finding for {input_id}: {finding['issue']}", file=review_path, record_id=input_id, path=finding["path"])
    if set(seen) != set(ids):
        missing = [input_id for input_id in ids if input_id not in set(seen)]
        _fail(f"review report is missing assigned IDs {missing}", file=review_path, path="/records")

    scope = config.aggregation.review_scope
    strict_scope = scope == STRICT_REVIEW_SCOPE
    if strict_scope:
        for input_id in ids:
            review_entry = next(entry for entry in review_records if entry["input_id"] == input_id)
            if any(item["status"] != "attested" for item in review_entry["collocations"]):
                _fail(f"strict review scope requires complete attested collocation coverage for {input_id}", file=review_path, record_id=input_id)
        # Historical strict reports need no sample, but if one is supplied it is evidence and must be validated.
        if "source_sample" not in review:
            return
    elif scope == SAMPLED_REVIEW_SCOPE:
        if "source_sample" not in review:
            _fail("schema-first review requires an explicit source_sample list (empty is allowed)", file=review_path, path="/source_sample")
    else:
        _fail(f"unsupported review scope {scope!r}", file=review_path, path="/scope")
    if not isinstance(review["source_sample"], list):
        _fail("review source_sample must be an ordered list", file=review_path, path="/source_sample")
    sample_seen: set[tuple[str, str, str]] = set()
    for sample_index, sample in enumerate(review["source_sample"]):
        input_id, collection, item_id = sample["input_id"], sample["collection"], sample["item_id"]
        identity = (input_id, collection, item_id)
        if identity in sample_seen:
            _fail("source_sample contains duplicate item", file=review_path, path=f"/source_sample/{sample_index}")
        sample_seen.add(identity)
        if input_id not in record_by_id:
            _fail(f"source_sample contains foreign input_id {input_id!r}", file=review_path, record_id=input_id)
        record = record_by_id[input_id]
        item_map = _actual_items(record, collection)
        if item_id not in item_map:
            _fail(f"source_sample references foreign {collection} item {item_id!r}", file=review_path, record_id=input_id, path=f"/source_sample/{sample_index}/item_id")
        status = sample["status"]
        if status == "contradicted":
            _fail(f"source_sample records a contradicted claim for {input_id}/{item_id}", file=review_path, record_id=input_id)
        if strict_scope and status != "attested":
            _fail(f"strict review scope permits only attested source_sample items, got {status!r}", file=review_path, record_id=input_id)
        _validate_attestation(status, sample["source_url"], sample["observation"],
                              where=f"sample {input_id}/{item_id}", file=review_path)
        if collection == "collocations":
            reported = next(entry for entry in review_records if entry["input_id"] == input_id)
            collocation_status = next(item for item in reported["collocations"] if item["collocation_id"] == item_id)
            if (status, sample["source_url"], sample["observation"]) != (
                collocation_status["status"], collocation_status["source_url"], collocation_status["observation"]
            ):
                _fail("source_sample collocation status/evidence differs from per-record report", file=review_path,
                      record_id=input_id, path=f"/source_sample/{sample_index}")


def _validate_attestation(status: str, source_url: Any, observation: Any, *, where: str, file: Path) -> None:
    if status not in {"attested", "unverified", "contradicted", "not_checked"}:
        _fail(f"{where} has unsupported review status {status!r}", file=file)
    if source_url is not None and (not isinstance(source_url, str) or not source_url.startswith(("http://", "https://"))):
        _fail(f"{where} source_url must be null or an absolute HTTP(S) URL", file=file)
    if not isinstance(observation, str):
        _fail(f"{where} observation must be a string", file=file)
    if status == "attested" and (not source_url or not observation.strip()):
        _fail(f"{where} attested status requires a supporting source URL and observation", file=file)


def _validate_human_disposition(
    binding: Any, *, receipt_path: Path, batch_id: str, output_path: Path, output_sha256: str,
    review_path: Path, review_sha256: str, revisions: dict[str, int], records: list[dict[str, Any]],
) -> tuple[Path, str] | None:
    if binding is None:
        return None
    path, expected_hash = _path_binding(binding, owner=receipt_path, label="human_disposition")
    raw, disposition = _read_json(path, "human disposition")
    if _sha(raw) != expected_hash:
        _fail("human disposition SHA-256 mismatch", file=path, path="/")
    _validate_interchange(disposition, schema_name="human_disposition", what="human disposition", file=path)
    if disposition["schema"] != HUMAN_DISPOSITION_SCHEMA or disposition["batch_id"] != batch_id:
        _fail("human disposition schema/batch binding mismatch", file=path)
    if _resolve_reference(disposition["artifact_path"], declaring_file=path, what="human disposition artifact_path") != output_path:
        _fail("human disposition artifact_path differs from accepted output", file=path)
    if disposition["artifact_sha256"] != output_sha256:
        _fail("human disposition artifact hash differs from accepted output", file=path)
    if _resolve_reference(disposition["review_path"], declaring_file=path, what="human disposition review_path") != review_path:
        _fail("human disposition review_path differs from accepted review", file=path)
    if disposition["review_sha256"] != review_sha256:
        _fail("human disposition review hash differs from accepted review", file=path)
    if disposition["record_revisions"] != revisions:
        _fail("human disposition record_revisions differ from accepted output", file=path)
    by_id = {record["input_id"]: record for record in records}
    for index, finding in enumerate(disposition["findings"]):
        input_id = finding["input_id"]
        if input_id not in by_id:
            _fail(f"human disposition finding has foreign input_id {input_id!r}", file=path, record_id=input_id)
        try:
            resolve_json_pointer(by_id[input_id], finding["path"], context=f"human disposition {input_id}")
        except ValidationError as exc:
            _fail(str(exc), file=path, record_id=input_id, path=finding["path"])
        if finding["status"] == "contradicted" and finding["requires_correction"]:
            _fail(f"human disposition requires correction of contradicted claim for {input_id}", file=path,
                  record_id=input_id, path=finding["path"])
    return path, expected_hash


def _load_acceptances(
    config: StageConfig, manifest: dict[str, Any], manifest_sha256: str, checked_batches: list[dict[str, Any]],
    input_schema_sha256: str, output_schema_sha256: str,
) -> tuple[BatchEvidence, ...]:
    aggregation = config.aggregation
    assert aggregation is not None and config.paths.output_schema is not None and config.constraints.schema_version is not None
    required = {batch["manifest"]["batch_id"]: batch for batch in checked_batches}
    by_batch: dict[str, BatchEvidence] = {}
    output_paths: dict[Path, str] = {}
    for acceptance_path in aggregation.acceptances:
        receipt_raw, receipt_value = _read_json(acceptance_path, "batch acceptance receipt")
        _validate_interchange(receipt_value, schema_name="acceptance", what="acceptance receipt", file=acceptance_path)
        receipt = receipt_value
        if receipt["job_id"] != manifest["job_id"]:
            _fail("acceptance job_id differs from frozen manifest job_id", file=acceptance_path, path="/job_id")
        batch_id = receipt["batch_id"]
        if batch_id not in required:
            _fail(f"foreign acceptance batch_id {batch_id!r}", file=acceptance_path, path="/batch_id")
        if batch_id in by_batch:
            _fail(f"duplicate acceptance for batch {batch_id!r}", file=acceptance_path, path="/batch_id")
        if receipt["review_scope"] != aggregation.review_scope:
            _fail("acceptance review_scope differs from aggregation config", file=acceptance_path, path="/review_scope")
        expected = required[batch_id]
        manifest_batch = expected["manifest"]
        expected_ids = tuple(manifest_batch["input_ids"])
        if receipt["input"]["input_ids"] != list(expected_ids):
            _fail(f"acceptance {batch_id} input IDs differ from frozen ordered membership", file=acceptance_path, path="/input/input_ids")
        if receipt["input"]["sha256"] != expected["input_sha256"]:
            _fail(f"acceptance {batch_id} input hash differs from frozen batch input", file=acceptance_path, path="/input/sha256")
        _check_binding(receipt["input_manifest"], owner=acceptance_path, label="acceptance input_manifest",
                       expected_path=aggregation.manifest_path, expected_hash=manifest_sha256)
        _check_binding(receipt["input"], owner=acceptance_path, label="acceptance input",
                       expected_path=expected["input_path"], expected_hash=expected["input_sha256"])
        _check_binding(receipt["contract"], owner=acceptance_path, label="acceptance contract",
                       expected_path=aggregation.contract_path, expected_hash=aggregation.contract_sha256)
        if receipt["schemas"] != {"input_sha256": input_schema_sha256, "output_sha256": output_schema_sha256}:
            _fail("acceptance schema fingerprints differ from configured schema bytes", file=acceptance_path, path="/schemas")
        if file_sha256(aggregation.contract_path) != aggregation.contract_sha256:
            _fail("configured enrichment contract SHA-256 mismatch", file=aggregation.contract_path, path="/")
        output_path, output_sha256 = _path_binding(receipt["output"], owner=acceptance_path, label="acceptance output")
        if _sha(output_path.read_bytes()) != output_sha256:
            _fail(f"accepted output SHA-256 mismatch for batch {batch_id}", file=output_path, path="/")
        previous = output_paths.get(output_path)
        if previous is not None:
            _fail(f"different batches {previous} and {batch_id} reference the same enriched artifact", file=acceptance_path, path="/output/path")
        output_paths[output_path] = batch_id
        revisions = _read_revision_map(receipt["output"]["record_revisions"], ids=expected_ids,
                                       what=f"acceptance {batch_id} record_revisions", file=acceptance_path)
        if isinstance(receipt["output"]["artifact_revision"], bool) or not isinstance(receipt["output"]["artifact_revision"], int) or receipt["output"]["artifact_revision"] <= 0:
            _fail("acceptance artifact_revision must be a positive integer", file=acceptance_path, path="/output/artifact_revision")
        if config.constraints.revisions is None:
            _fail("constraints.revisions is required for acceptance validation", file=config.config_path)
        for input_id in expected_ids:
            if revisions[input_id] != config.constraints.revisions[input_id]:
                _fail(f"accepted revision for {input_id} differs from constraints.revisions", file=acceptance_path,
                      record_id=input_id, path=f"/output/record_revisions/{input_id}")
        output_raw, records = read_jsonl(output_path, f"{batch_id} enriched output JSONL")
        if _sha(output_raw) != output_sha256:
            _fail(f"accepted output SHA-256 changed while reading batch {batch_id}", file=output_path)
        actual_ids = [item.get("input_id") for item in records]
        for line_number, input_id in enumerate(actual_ids, start=1):
            if not isinstance(input_id, str) or not input_id.strip():
                _fail("enriched output input_id must be a nonblank string", file=output_path,
                      record_id=None, path=f"/records/{line_number}/input_id")
        if len(actual_ids) != len(set(actual_ids)):
            duplicate = next(item for index, item in enumerate(actual_ids) if item in actual_ids[:index])
            missing = [item for item in expected_ids if item not in actual_ids]
            foreign = [item for item in actual_ids if item not in expected_ids]
            _fail(f"batch {batch_id} enriched output contains duplicate input_id {duplicate!r} (missing={missing}, foreign={foreign})",
                  file=output_path, record_id=duplicate, path="/input_id")
        if tuple(actual_ids) != expected_ids:
            missing = [item for item in expected_ids if item not in actual_ids]
            foreign = [item for item in actual_ids if item not in expected_ids]
            for input_id in foreign:
                other_batch = next((other_id for other_id, item in required.items()
                                    if other_id != batch_id and input_id in item["manifest"]["input_ids"]), None)
                if other_batch is not None:
                    _fail(f"input_id {input_id!r} is assigned to {other_batch} but appears in enriched batch {batch_id}",
                          file=output_path, record_id=input_id, path="/input_id")
            _fail(f"batch {batch_id} enriched output order/membership mismatch (missing={missing}, foreign={foreign}, expected={list(expected_ids)!r}, got={actual_ids!r})",
                  file=output_path, path="/input_id")
        try:
            validate_records(records, expected["input_records"],
                             _load_json(config.paths.output_schema, "output schema"),
                             _load_json(config.paths.input_schema, "input schema"),
                             output_schema_path=config.paths.output_schema, input_schema_path=config.paths.input_schema,
                             expected_ids=expected_ids, expected_revision=None,
                             expected_schema_version=config.constraints.schema_version,
                             expected_revisions=revisions)
            for record in records:
                rendered = render_record(record)
                audit_rendered_record(record, rendered)
        except (ValidationError, ValueError, RuntimeError) as exc:
            _fail(f"batch {batch_id} enriched output validation/render failed: {exc}",
                  file=getattr(exc, "file", None) or output_path,
                  record_id=getattr(exc, "record_id", None), path=getattr(exc, "path", None))

        validation_path, validation_hash = _path_binding(receipt["validation"], owner=acceptance_path, label="acceptance validation")
        validation_raw, validation = _read_json(validation_path, "batch validation report")
        if _sha(validation_raw) != validation_hash:
            _fail("batch validation report SHA-256 mismatch", file=validation_path, path="/")
        _validate_interchange(validation, schema_name="validation", what="batch validation report", file=validation_path)
        _check_report_coverage(validation, batch_id=batch_id, ids=expected_ids, revisions=revisions,
                               output_path=output_path, output_sha256=output_sha256,
                               input_path=expected["input_path"], input_sha256=expected["input_sha256"],
                               input_schema_sha256=input_schema_sha256, output_schema_sha256=output_schema_sha256,
                               schema_version=config.constraints.schema_version, file=validation_path)
        review_path, review_hash = _path_binding(receipt["review"], owner=acceptance_path, label="acceptance review")
        review_raw, review = _read_json(review_path, "batch review report")
        if _sha(review_raw) != review_hash:
            _fail("batch review report SHA-256 mismatch", file=review_path, path="/")
        _validate_interchange(review, schema_name="review", what="batch review report", file=review_path)
        _validate_review(review, config=config, batch_id=batch_id, ids=expected_ids, revisions=revisions,
                         records=records, output_path=output_path, output_sha256=output_sha256, review_path=review_path)
        _validate_human_disposition(receipt.get("human_disposition"), receipt_path=acceptance_path,
                                    batch_id=batch_id, output_path=output_path, output_sha256=output_sha256,
                                    review_path=review_path, review_sha256=review_hash,
                                    revisions=revisions, records=records)
        by_batch[batch_id] = BatchEvidence(
            batch_id=batch_id, input_path=expected["input_path"], input_sha256=expected["input_sha256"],
            input_ids=expected_ids, output_path=output_path, output_sha256=output_sha256,
            artifact_revision=receipt["output"]["artifact_revision"], record_revisions=revisions,
            validation_path=validation_path, validation_sha256=validation_hash,
            review_path=review_path, review_sha256=review_hash, acceptance_path=acceptance_path,
            acceptance_sha256=_sha(receipt_raw), records=records, input_records=expected["input_records"],
        )
    missing_batches = [batch["manifest"]["batch_id"] for batch in checked_batches if batch["manifest"]["batch_id"] not in by_batch]
    if missing_batches:
        _fail(f"missing batch acceptance(s): {missing_batches}", file=config.config_path, path="/aggregation/acceptances")
    return tuple(by_batch[batch["manifest"]["batch_id"]] for batch in checked_batches)


def _collect(config: StageConfig) -> AggregationContext:
    if config.aggregation is None:
        _fail("aggregation config is required", file=config.config_path)
    if file_sha256(config.config_path) != config.config_sha256:
        _fail("configuration bytes changed after typed YAML loading", file=config.config_path, path="/")
    if config.paths.input is None or config.paths.source_input is None or config.paths.input_schema is None or config.paths.output_schema is None:
        _fail("aggregation requires paths.input, source_input, input_schema, and output_schema", file=config.config_path)
    if config.constraints.input_ids is None or config.constraints.revisions is None or config.constraints.schema_version is None:
        _fail("aggregation requires input_ids, revisions, and schema_version", file=config.config_path)
    if file_sha256(config.aggregation.contract_path) != config.aggregation.contract_sha256:
        _fail("configured enrichment contract SHA-256 mismatch", file=config.aggregation.contract_path, path="/")
    manifest, manifest_hash, master, _master_raw, native, checked_batches, input_schema_sha, output_schema_sha, master_sha = _read_manifest(config)
    batch_evidence = _load_acceptances(config, manifest, manifest_hash, checked_batches, input_schema_sha, output_schema_sha)
    expected_revisions = dict(config.constraints.revisions)
    actual_revisions = {input_id: revision for batch in batch_evidence for input_id, revision in batch.record_revisions.items()}
    if actual_revisions != expected_revisions:
        _fail("accepted per-ID revision map differs from constraints.revisions", file=config.config_path, path="/constraints/revisions")
    if config.constraints.input_sha256 is not None:
        # This is checked against the aggregate after canonical merge and in replay.
        if not _is_hash(config.constraints.input_sha256):
            _fail("constraints.input_sha256 is malformed", file=config.config_path, path="/constraints/input_sha256")
    return AggregationContext(config, manifest, manifest_hash, master, master_sha, input_schema_sha,
                              output_schema_sha, config.aggregation.contract_sha256, native, batch_evidence)


def _canonical_jsonl(records: list[dict[str, Any]]) -> bytes:
    return b"".join(
        (json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
        for record in records
    )


def _merge(context: AggregationContext) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    expected_ids = context.config.constraints.input_ids or ()
    rows: list[dict[str, Any]] = []
    row_bindings: list[dict[str, Any]] = []
    all_ids: list[str] = []
    by_id: dict[str, tuple[dict[str, Any], BatchEvidence, int]] = {}
    for batch in context.batches:
        for line_number, record in enumerate(batch.records, start=1):
            input_id = record["input_id"]
            all_ids.append(input_id)
            if input_id in by_id:
                _fail(f"accepted batch overlap duplicates input_id {input_id!r}", file=batch.output_path,
                      record_id=input_id, path="/input_id")
            by_id[input_id] = (record, batch, line_number)
    if len(all_ids) != len(set(all_ids)):
        _fail("global accepted output contains duplicate IDs", file=context.config.config_path, path="/input_id")
    missing = [input_id for input_id in expected_ids if input_id not in by_id]
    foreign = [input_id for input_id in all_ids if input_id not in expected_ids]
    if missing or foreign or len(all_ids) != len(expected_ids):
        _fail(f"global accepted output cardinality/membership mismatch (missing={missing}, foreign={foreign}, expected={len(expected_ids)}, actual={len(all_ids)})",
              file=context.config.config_path, path="/input_id")
    for row_number, input_id in enumerate(expected_ids, start=1):
        record, batch, source_record_number = by_id[input_id]
        rows.append(record)
        row_bindings.append({
            "row": row_number, "input_id": input_id, "batch_id": batch.batch_id,
            "source_output_path": str(batch.output_path), "source_output_sha256": batch.output_sha256,
            "source_record_number": source_record_number, "record_revision": record["revision"],
        })
    return rows, row_bindings


def _provenance(context: AggregationContext, records: list[dict[str, Any]], aggregate_raw: bytes,
                aggregate_path: Path, row_bindings: list[dict[str, Any]]) -> dict[str, Any]:
    aggregation = context.config.aggregation
    assert aggregation is not None and context.config.paths.source_input is not None
    portable = context.manifest["schema"] == MANIFEST_SCHEMA
    owner = aggregation.provenance_path
    ref = lambda path: relative_reference(owner, path) if portable else str(Path(path).resolve())
    ids = list(context.config.constraints.input_ids or ())
    revision_map = {record["input_id"]: record["revision"] for record in records}
    batches = []
    for batch in context.batches:
        batches.append({
            "batch_id": batch.batch_id, "input_path": ref(batch.input_path), "input_sha256": batch.input_sha256,
            "input_ids": list(batch.input_ids), "output_path": ref(batch.output_path), "output_sha256": batch.output_sha256,
            "artifact_revision": batch.artifact_revision, "record_revisions": batch.record_revisions,
            "validation_path": ref(batch.validation_path), "validation_sha256": batch.validation_sha256,
            "review_path": ref(batch.review_path), "review_sha256": batch.review_sha256,
        })
    native_linkage = context.native_source_linkage
    if portable and native_linkage.get("verified"):
        evidence = dict(native_linkage["evidence"])
        if "source_path" in evidence:
            evidence["source_path"] = ref(Path(evidence["source_path"]))
        native_linkage = {**native_linkage, "evidence": evidence}
    rows = [
        {**binding, "source_output_path": ref(Path(binding["source_output_path"]))}
        for binding in row_bindings
    ] if portable else row_bindings
    value = {
        "schema": PROVENANCE_SCHEMA if portable else LEGACY_PROVENANCE_SCHEMA,
        "serialization": SERIALIZATION,
        "config": {"path": ref(context.config.config_path), "sha256": context.config.config_sha256},
        "review_scope": aggregation.review_scope,
        "manifest": {"path": ref(aggregation.manifest_path), "sha256": context.manifest_sha256},
        "contract": {"path": ref(aggregation.contract_path), "sha256": context.contract_sha256},
        "schemas": {"input_sha256": context.input_schema_sha256, "output_sha256": context.output_schema_sha256},
        "master": {"path": ref(context.config.paths.source_input), "sha256": context.master_sha256,
                   "count": len(ids), "input_ids": ids},
        "native_source_linkage": native_linkage,
        "acceptances": [{"path": ref(batch.acceptance_path), "sha256": batch.acceptance_sha256} for batch in context.batches],
        "batches": batches,
        "aggregate": {"path": ref(aggregate_path), "sha256": _sha(aggregate_raw),
                      "count": len(records), "input_ids": ids, "unique_count": len(set(ids)),
                      "record_revisions": revision_map},
        "rows": rows,
    }
    _validate_interchange(value, schema_name="provenance", what="aggregate provenance", file=owner)
    return value


def _verify_aggregate(context: AggregationContext, *, aggregate_path: Path | None = None,
                      provenance_path: Path | None = None) -> tuple[list[dict[str, Any]], str, dict[str, Any], bytes]:
    config = context.config
    aggregation = config.aggregation
    assert aggregation is not None and config.paths.input is not None
    target_path = aggregate_path or config.paths.input
    stored_provenance_path = provenance_path or aggregation.provenance_path
    raw, actual_records = read_jsonl(target_path, "persisted aggregate JSONL")
    actual_hash = _sha(raw)
    merged, rows = _merge(context)
    if len(actual_records) != len(merged):
        _fail(f"persisted aggregate count differs from accepted full payloads (expected {len(merged)}, got {len(actual_records)})",
              file=target_path, path="/input_id")
    for index, (actual_record, expected_record) in enumerate(zip(actual_records, merged, strict=True), start=1):
        if actual_record != expected_record:
            input_id = actual_record.get("input_id")
            _fail("persisted aggregate full payload differs from accepted batch record", file=target_path,
                  record_id=input_id, path=f"/records/{index}")
    expected_raw = _canonical_jsonl(merged)
    expected_hash = _sha(expected_raw)
    if actual_hash != expected_hash:
        _fail(f"persisted aggregate bytes/hash differ from deterministic accepted merge (expected {expected_hash}, got {actual_hash})", file=target_path, path="/")
    if config.constraints.input_sha256 is not None and actual_hash != config.constraints.input_sha256:
        _fail(f"constraints.input_sha256 mismatch: expected {config.constraints.input_sha256}, got {actual_hash}", file=target_path, path="/")
    validate_records(actual_records, context.master,
                     _load_json(config.paths.output_schema, "output schema"),
                     _load_json(config.paths.input_schema, "input schema"),
                     output_schema_path=config.paths.output_schema, input_schema_path=config.paths.input_schema,
                     expected_ids=config.constraints.input_ids, expected_revision=None,
                     expected_schema_version=config.constraints.schema_version or "",
                     expected_revisions=dict(config.constraints.revisions or {}))
    for record in actual_records:
        audit_rendered_record(record, render_record(record))
    expected_provenance = _provenance(context, merged, expected_raw, config.paths.input, rows)
    provenance_raw, stored = _read_json(stored_provenance_path, "aggregate provenance")
    _validate_interchange(stored, schema_name="provenance", what="aggregate provenance", file=stored_provenance_path)
    if stored != expected_provenance:
        _fail("persisted aggregate provenance does not exactly bind accepted full payloads and current config", file=stored_provenance_path, path="/")
    return actual_records, actual_hash, stored, provenance_raw


def _report(context: AggregationContext, records: list[dict[str, Any]], digest: str,
            provenance_raw: bytes) -> dict[str, Any]:
    aggregation = context.config.aggregation
    assert aggregation is not None and context.config.paths.input is not None
    portable = context.manifest["schema"] == MANIFEST_SCHEMA
    owner = aggregation.report_path
    ref = lambda path: relative_reference(owner, path) if portable else str(Path(path).resolve())
    native_linkage = context.native_source_linkage
    if portable and native_linkage.get("verified"):
        evidence = dict(native_linkage["evidence"])
        if "source_path" in evidence:
            evidence["source_path"] = ref(Path(evidence["source_path"]))
        native_linkage = {**native_linkage, "evidence": evidence}
    return {
        "schema": REPORT_SCHEMA if portable else LEGACY_REPORT_SCHEMA, "status": "pass",
        "aggregate_path": ref(context.config.paths.input), "aggregate_sha256": digest,
        "provenance_path": ref(aggregation.provenance_path),
        "provenance_sha256": _sha(provenance_raw), "manifest_path": ref(aggregation.manifest_path),
        "manifest_sha256": context.manifest_sha256,
        "checked_counts": {"master_records": len(context.master), "batches": len(context.batches),
                            "output_records": len(records), "unique_ids": len({row['input_id'] for row in records}),
                            "unique_expressions": len({row['headword']['expression'] for row in records})},
        "input_ids": [row["input_id"] for row in records],
        "record_revisions": {row["input_id"]: row["revision"] for row in records},
        "review_scope": context.config.aggregation.review_scope,
        "native_source_linkage": native_linkage,
        "checks": {"acceptance": True, "manifest": True, "membership": True, "payload": True,
                   "schema": True, "references": True, "render": True, "provenance": True},
    }


def _protected_paths(context: AggregationContext) -> set[Path]:
    config = context.config
    frozen_config_path = _resolve_reference(context.manifest["config"]["config_path"],
                                            declaring_file=config.aggregation.manifest_path,
                                            what="manifest frozen config path")
    protected = {
        config.config_path.resolve(), frozen_config_path, config.paths.source_input.resolve(),
        config.paths.input_schema.resolve(), config.paths.output_schema.resolve(),
        config.aggregation.manifest_path.resolve(), config.aggregation.contract_path.resolve(),
        *(path.resolve() for path in INTERCHANGE_SCHEMAS.values()),
    }
    if config.declared_paths is not None:
        for name in ("source_input", "input_schema", "output_schema"):
            path = getattr(config.declared_paths, name)
            if path is not None:
                protected.add(path.resolve())
    if config.source is not None:
        protected.update({config.source.apkg.resolve(), config.source.mapping_contract.resolve()})
    if config.normalization is not None:
        protected.update({config.normalization.source_map.resolve(), config.normalization.raw_notes.resolve(),
                          config.normalization.exceptions.resolve(), config.normalization.report.resolve()})
    for batch in context.batches:
        protected.update({batch.input_path.resolve(), batch.output_path.resolve(), batch.acceptance_path.resolve(),
                          batch.validation_path.resolve(), batch.review_path.resolve()})
    for acceptance_path in config.aggregation.acceptances:
        receipt_raw, receipt = _read_json(acceptance_path, "acceptance receipt for path protection")
        if "human_disposition" in receipt:
            protected.add(_resolve_reference(receipt["human_disposition"]["path"], declaring_file=acceptance_path,
                                              what="human disposition path"))
    return protected


def _all_named_targets(config: StageConfig) -> dict[str, Path]:
    aggregation = config.aggregation
    assert aggregation is not None and config.paths.input is not None
    targets = {"aggregate": config.paths.input.resolve(), "provenance": aggregation.provenance_path.resolve(),
               "report": aggregation.report_path.resolve()}
    if len(set(targets.values())) != len(targets):
        raise AggregationError("aggregate/provenance/report targets resolve to a collision",
                               file=config.config_path, path="/aggregation")

    # Preview/audit targets are already named by an output directory, even when
    # a partial aggregation config does not yet declare a package. Include both
    # the original YAML declaration and the effective (possibly overridden)
    # directory, and add the APKG only when its basename is actually known.
    build_targets: dict[Path, set[str]] = {}
    for label, paths in (("declared", config.declared_paths), ("effective", config.paths)):
        output_dir = paths.output_dir if paths is not None else None
        if output_dir is None:
            continue
        named = {"preview": output_dir / "preview.html", "audit": output_dir / "audit.json"}
        if config.package is not None:
            named["apkg"] = output_dir / config.package.apkg_filename
        for name, path in named.items():
            build_targets.setdefault(path.resolve(), set()).add(f"{label} {name}")

    for aggregate_name, aggregate_path in targets.items():
        for build_path, labels in build_targets.items():
            if aggregate_path == build_path:
                _fail(f"aggregate {aggregate_name} target aliases named build output ({', '.join(sorted(labels))}): {build_path}",
                      file=build_path, path="/paths/output_dir")
            if aggregate_path in build_path.parents or build_path in aggregate_path.parents:
                _fail(f"aggregate {aggregate_name} target overlaps named build output ({', '.join(sorted(labels))}): {build_path}",
                      file=build_path, path="/paths/output_dir")
    for left_name, left in targets.items():
        for right_name, right in targets.items():
            if left_name != right_name and (left in right.parents or right in left.parents):
                _fail(f"output target {left_name} overlaps {right_name}", file=config.config_path, path="/aggregation")
    return targets


def _preflight_publication(context: AggregationContext, *, force: bool) -> dict[str, Path]:
    targets = _all_named_targets(context.config)
    protected = _protected_paths(context)
    for name in ("aggregate", "provenance", "report"):
        target = targets[name]
        if target in protected:
            _fail(f"aggregate {name} target aliases a protected input/evidence path: {target}", file=target, path="/aggregation")
        if _present(target) and target.is_dir():
            _fail(f"aggregate {name} target is a directory, not a generated file", file=target)
    existing = [str(targets[name]) for name in ("aggregate", "provenance", "report") if _present(targets[name])]
    if existing and not force:
        raise FileExistsError("Aggregate outputs already exist; use --force to replace only named aggregate/provenance/report outputs: " + ", ".join(existing))
    return {key: targets[key] for key in ("aggregate", "provenance", "report")}


def _publish_staged(staged: list[tuple[Path, Path]], *, force: bool, stage_dir: Path) -> None:
    backups: dict[Path, Path] = {}
    published: list[Path] = []
    try:
        for _, target in staged:
            if _present(target) and not force:
                raise FileExistsError(f"Aggregate output appeared during staging; use --force: {target}")
            if _present(target) and target.is_dir():
                raise IsADirectoryError(str(target))
        for index, (_, target) in enumerate(staged):
            if _present(target):
                backup = stage_dir / f"backup-{index}"
                os.replace(target, backup)
                backups[target] = backup
        for staged_path, target in staged:
            target.parent.mkdir(parents=True, exist_ok=True)
            os.replace(staged_path, target)
            published.append(target)
    except Exception:
        for target in reversed(published):
            try:
                target.unlink(missing_ok=True)
            except OSError:
                pass
        for target, backup in backups.items():
            if backup.exists():
                os.replace(backup, target)
        raise


def _write_staged(path: Path, payload: bytes) -> None:
    with path.open("wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def aggregate_output(config: StageConfig, *, force: bool = False) -> dict[str, Any]:
    """Accept, merge, stage, replay-validate, then publish the named aggregate outputs."""
    context = _collect(config)
    targets = _preflight_publication(context, force=force)
    records, row_bindings = _merge(context)
    aggregate_raw = _canonical_jsonl(records)
    aggregate_hash = _sha(aggregate_raw)
    if config.constraints.input_sha256 is not None and config.constraints.input_sha256 != aggregate_hash:
        _fail(f"configured enriched input hash differs from deterministic aggregate: expected {config.constraints.input_sha256}, got {aggregate_hash}",
              file=config.paths.input, path="/")
    provenance = _provenance(context, records, aggregate_raw, config.paths.input, row_bindings)
    provenance_raw = (json.dumps(provenance, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    report = _report(context, records, aggregate_hash, provenance_raw)
    _validate_interchange(report, schema_name="aggregate_report", what="aggregate report", file=targets["report"])
    report_raw = (json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode("utf-8")

    # Stage alongside the aggregate, then validate the bytes actually written before publication.
    stage_parent = targets["aggregate"].parent
    stage_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".aggregate-stage-", dir=stage_parent) as stage_name:
        stage_dir = Path(stage_name)
        staged_aggregate = stage_dir / "aggregate.jsonl"
        staged_provenance = stage_dir / "provenance.json"
        staged_report = stage_dir / "report.json"
        _write_staged(staged_aggregate, aggregate_raw)
        _write_staged(staged_provenance, provenance_raw)
        verified_records, verified_hash, verified_provenance, verified_provenance_raw = _verify_aggregate(
            context, aggregate_path=staged_aggregate, provenance_path=staged_provenance)
        if verified_hash != aggregate_hash or verified_records != records or verified_provenance != provenance:
            _fail("staged aggregate did not replay to the exact expected full-payload merge", file=staged_aggregate)
        _write_staged(staged_report, report_raw)
        # Reparse staged run report to reject encoding/serialization issues before publishing.
        _, report_check = _read_json(staged_report, "staged aggregate report")
        _validate_interchange(report_check, schema_name="aggregate_report", what="staged aggregate report", file=staged_report)
        if report_check != report or report_check.get("status") != "pass":
            _fail("staged aggregate report did not validate", file=staged_report)
        _publish_staged([(staged_aggregate, targets["aggregate"]),
                         (staged_provenance, targets["provenance"]),
                         (staged_report, targets["report"])], force=force, stage_dir=stage_dir)
    return {
        "stage": "aggregate-output", "status": "pass", "input_sha256": aggregate_hash,
        "source_input_sha256": context.master_sha256, "checked_counts": report["checked_counts"],
        "aggregate_path": str(targets["aggregate"]), "provenance_path": str(targets["provenance"]),
        "report_path": str(targets["report"]), "provenance": provenance,
    }


def validate_aggregate(config: StageConfig) -> dict[str, Any]:
    """Read-only replay of acceptance bindings, persisted aggregate payload and provenance."""
    context = _collect(config)
    records, digest, provenance, provenance_raw = _verify_aggregate(context)
    report = _report(context, records, digest, provenance_raw)
    report_path = config.aggregation.report_path
    _, stored_report = _read_json(report_path, "persisted aggregate report")
    _validate_interchange(stored_report, schema_name="aggregate_report", what="persisted aggregate report", file=report_path)
    if stored_report != report:
        _fail("persisted aggregate report does not bind current aggregate/provenance bytes", file=report_path, path="/")
    return {
        "stage": "validate-aggregate", "status": "pass", "input_sha256": digest,
        "source_input_sha256": context.master_sha256, "checked_counts": report["checked_counts"],
        "aggregate_path": str(config.paths.input.resolve()), "provenance_path": str(config.aggregation.provenance_path),
        "report_path": str(config.aggregation.report_path), "provenance": provenance,
        "checks": report["checks"],
    }


def protected_evidence_paths(config: StageConfig) -> set[Path]:
    """Resolve every verified aggregation input/output path for build target protection."""
    if config.aggregation is None:
        return set()
    context = _collect(config)
    protected = _protected_paths(context)
    if config.paths.input is not None:
        protected.add(config.paths.input.resolve())
    protected.update({config.aggregation.provenance_path.resolve(), config.aggregation.report_path.resolve()})
    return protected
