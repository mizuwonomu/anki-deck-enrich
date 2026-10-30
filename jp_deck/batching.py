"""Kiểm tra và chuẩn bị các lô đầu vào có membership cố định."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from .config import StageConfig
from .pathrefs import relative_reference
from .input_validation import (
    InputStageError,
    _schema_validator,
    validate_input_dataset,
    validate_input_objects,
    validation_report_path,
)
from .source_apkg import SourceError, file_sha256
from .validation import read_jsonl

MANIFEST_SCHEMA = "jp-deck-batch-manifest/v2"
LEGACY_MANIFEST_SCHEMA = "jp-deck-batch-manifest/v1"
AUDIT_SCHEMA = "jp-deck-batch-audit/v1"
JOB_ID = "batching-mimi"
_HASH = re.compile(r"[0-9a-f]{64}")


def _fail(message: str, *, file: Path | None = None, record_id: str | None = None, path: str | None = None) -> None:
    raise InputStageError(message, file=str(file) if file is not None else None, record_id=record_id, path=path)


def _compact_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _pretty_json(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _present(path: Path) -> bool:
    return path.exists() or path.is_symlink()


def _require_settings(config: StageConfig) -> tuple[tuple[str, ...], int, Path]:
    if config.batching is None or config.constraints.input_ids is None:
        _fail("batching and constraints.input_ids are required", file=config.config_path)
    ids = config.constraints.input_ids
    if not ids or len(ids) != len(set(ids)):
        _fail("constraints.input_ids must be a nonempty ordered list of unique IDs", file=config.config_path)
    size = config.batching.batch_size
    if isinstance(size, bool) or not isinstance(size, int) or size <= 0:
        _fail("batching.batch_size must be a positive integer", file=config.config_path)
    return ids, size, config.batching.output_dir.resolve()


def _chunks(ids: tuple[str, ...], size: int) -> list[tuple[str, ...]]:
    return [ids[index:index + size] for index in range(0, len(ids), size)]


def _expected_batches(ids: tuple[str, ...], size: int) -> list[dict[str, Any]]:
    return [
        {
            "batch_id": f"batch-{index:03d}",
            "path": f"batch-{index:03d}/input.jsonl",
            "input_ids": list(members),
            "count": len(members),
        }
        for index, members in enumerate(_chunks(ids, size), start=1)
    ]


def _protected_paths(config: StageConfig) -> set[Path]:
    protected = {config.config_path.resolve()}
    for paths in (config.declared_paths, config.paths):
        if paths is None:
            continue
        for name in ("input", "source_input", "input_schema", "output_schema", "output_dir"):
            candidate = getattr(paths, name)
            if candidate is not None:
                protected.add(candidate.resolve())
        if paths.output_dir is not None:
            protected.update((paths.output_dir / name).resolve() for name in ("preview.html", "audit.json"))
            if config.package is not None:
                protected.add((paths.output_dir / config.package.apkg_filename).resolve())
    if config.source is not None:
        protected.update({config.source.apkg.resolve(), config.source.mapping_contract.resolve()})
    if config.normalization is not None:
        protected.update(Path(getattr(config.normalization, name)).resolve() for name in (
            "source_map", "raw_notes", "exceptions", "report"
        ))
        protected.add(validation_report_path(config).resolve())
    return protected


def _targets(config: StageConfig) -> dict[str, Path]:
    ids, size, output_dir = _require_settings(config)
    targets = {
        "manifest": (output_dir / "manifest.json").resolve(),
        "audit": (output_dir / "audit.json").resolve(),
    }
    for batch in _expected_batches(ids, size):
        targets[batch["batch_id"]] = (output_dir / batch["path"]).resolve()
    if len(set(targets.values())) != len(targets):
        _fail("batch output targets resolve to duplicate paths", file=config.config_path)
    protected = _protected_paths(config)
    for name, target in targets.items():
        if target in protected:
            _fail(f"batch output {name} aliases a protected configured path: {target}", file=target)
        if _present(target) and target.is_dir():
            _fail(f"batch output {name} is a directory, not a generated file: {target}", file=target)
    return targets


def _preflight(config: StageConfig, *, force: bool) -> dict[str, Path]:
    targets = _targets(config)
    existing = [str(path) for path in targets.values() if _present(path)]
    if existing and not force:
        raise FileExistsError("Batch output already exists; use --force to replace generated batch artifacts: " + ", ".join(existing))
    return targets


def _manifest_reference(owner: Path, target: Path, *, schema: str) -> str:
    if schema == MANIFEST_SCHEMA:
        return relative_reference(owner, target)
    return str(target.resolve())


def _effective_binding(config: StageConfig, *, owner: Path, schema: str) -> dict[str, Any]:
    ids, size, output_dir = _require_settings(config)
    source = config.source
    norm = config.normalization
    if source is None or norm is None or config.paths.source_input is None or config.paths.input_schema is None:
        _fail("source, normalization, source_input, and input_schema are required", file=config.config_path)
    ref = lambda path: _manifest_reference(owner, path, schema=schema)
    return {
        "config_path": ref(config.config_path),
        "config_sha256": config.config_sha256,
        "source_input": ref(config.paths.source_input),
        "input_schema": ref(config.paths.input_schema),
        "source_apkg": ref(source.apkg),
        "source_sha256": source.sha256,
        "adapter": source.adapter,
        "deck_ids": list(source.deck_ids),
        "note_type_ids": list(source.note_type_ids),
        "mapping_contract": ref(source.mapping_contract),
        "mapping_contract_version": source.mapping_contract_version,
        "mapping_contract_sha256": source.mapping_contract_sha256,
        "selection_order": source.selection_order,
        "selection_count": source.selection_count,
        "input_ids": list(ids),
        "batch_size": size,
        "output_dir": ref(output_dir),
        "source_map": ref(norm.source_map),
        "raw_notes": ref(norm.raw_notes),
    }


def _base_manifest(
    config: StageConfig, master_raw: bytes, *, owner_path: Path | None = None, schema: str = MANIFEST_SCHEMA
) -> dict[str, Any]:
    ids, size, output_dir = _require_settings(config)
    if config.source is None or config.normalization is None or config.paths.source_input is None or config.paths.input_schema is None:
        _fail("source-aware normalized input settings are required", file=config.config_path)
    source = config.source
    owner = (owner_path or output_dir / "manifest.json").resolve()
    ref = lambda path: _manifest_reference(owner, path, schema=schema)
    return {
        "schema": schema,
        "job_id": JOB_ID,
        "config": _effective_binding(config, owner=owner, schema=schema),
        "source": {
            "path": ref(source.apkg),
            "sha256": file_sha256(source.apkg),
            "database_member": "collection.anki21b",
        },
        "mapping": {
            "path": ref(source.mapping_contract),
            "version": source.mapping_contract_version,
            "sha256": file_sha256(source.mapping_contract),
        },
        "schemas": {"input_sha256": file_sha256(config.paths.input_schema)},
        "master": {
            "path": ref(config.paths.source_input),
            "sha256": _sha(master_raw),
            "count": len(ids),
        },
        "provenance": {
            "source_map": {
                "path": ref(config.normalization.source_map),
                "sha256": file_sha256(config.normalization.source_map),
            },
            "raw_notes": {
                "path": ref(config.normalization.raw_notes),
                "sha256": file_sha256(config.normalization.raw_notes),
            },
        },
        "selection": {"order": source.selection_order, "input_ids": list(ids)},
        "batch_size": size,
        "batches": [],
    }


def _validate_manifest_shape(value: Any, path: Path) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {
        "schema", "job_id", "config", "source", "mapping", "schemas", "master", "provenance",
        "selection", "batch_size", "batches",
    }:
        _fail("manifest must have exactly the declared top-level fields", file=path)
    for key in ("schema", "job_id"):
        if not isinstance(value[key], str):
            _fail(f"manifest /{key} must be a string", file=path, path=f"/{key}")
    if value["schema"] not in {MANIFEST_SCHEMA, LEGACY_MANIFEST_SCHEMA} or value["job_id"] != JOB_ID:
        _fail("manifest schema or job identity is unsupported", file=path)
    if not isinstance(value["config"], dict) or not isinstance(value["source"], dict):
        _fail("manifest /config and /source must be objects", file=path)
    if not isinstance(value["mapping"], dict) or not isinstance(value["schemas"], dict):
        _fail("manifest /mapping and /schemas must be objects", file=path)
    if not isinstance(value["master"], dict) or not isinstance(value["provenance"], dict):
        _fail("manifest /master and /provenance must be objects", file=path)
    selection = value["selection"]
    if not isinstance(selection, dict) or set(selection) != {"order", "input_ids"}:
        _fail("manifest /selection has an invalid shape", file=path, path="/selection")
    if not isinstance(selection["order"], str) or not isinstance(selection["input_ids"], list):
        _fail("manifest /selection values have invalid types", file=path, path="/selection")
    if any(not isinstance(item, str) or not item.strip() for item in selection["input_ids"]):
        _fail("manifest /selection/input_ids must contain nonblank strings", file=path, path="/selection/input_ids")
    if len(selection["input_ids"]) != len(set(selection["input_ids"])):
        _fail("manifest /selection/input_ids contains duplicates", file=path, path="/selection/input_ids")
    size = value["batch_size"]
    if isinstance(size, bool) or not isinstance(size, int) or size <= 0:
        _fail("manifest /batch_size must be a positive integer", file=path, path="/batch_size")
    if not isinstance(value["batches"], list) or not value["batches"]:
        _fail("manifest /batches must be a nonempty list", file=path, path="/batches")
    _check_object_fields(value["config"], {"config_path", "config_sha256", "source_input", "input_schema", "source_apkg",
        "source_sha256", "adapter", "deck_ids", "note_type_ids", "mapping_contract", "mapping_contract_version",
        "mapping_contract_sha256", "selection_order", "selection_count", "input_ids", "batch_size", "output_dir",
        "source_map", "raw_notes"}, path, "/config")
    for key in ("config_sha256", "source_sha256", "mapping_contract_sha256"):
        _check_hash(value["config"].get(key), path, f"/config/{key}")
    if isinstance(value["config"].get("selection_count"), bool) or not isinstance(value["config"].get("selection_count"), int):
        _fail("manifest config selection_count must be an integer", file=path, path="/config/selection_count")
    for list_key in ("input_ids", "deck_ids", "note_type_ids"):
        item_list = value["config"].get(list_key)
        if not isinstance(item_list, list) or not item_list:
            _fail(f"manifest config {list_key} must be a nonempty list", file=path, path=f"/config/{list_key}")
        if any(not isinstance(item, str if list_key == "input_ids" else int) or isinstance(item, bool) for item in item_list):
            _fail(f"manifest config {list_key} has invalid element types", file=path, path=f"/config/{list_key}")
    if any(not item.strip() for item in value["config"]["input_ids"]):
        _fail("manifest config input_ids must be a nonblank string list", file=path, path="/config/input_ids")
    for list_key in ("input_ids", "deck_ids", "note_type_ids"):
        if len(value["config"][list_key]) != len(set(value["config"][list_key])):
            _fail(f"manifest config {list_key} contains duplicates", file=path, path=f"/config/{list_key}")
    _check_object_fields(value["source"], {"path", "sha256", "database_member"}, path, "/source")
    _check_hash(value["source"].get("sha256"), path, "/source/sha256")
    _check_object_fields(value["mapping"], {"path", "version", "sha256"}, path, "/mapping")
    _check_hash(value["mapping"].get("sha256"), path, "/mapping/sha256")
    _check_object_fields(value["schemas"], {"input_sha256"}, path, "/schemas")
    _check_hash(value["schemas"].get("input_sha256"), path, "/schemas/input_sha256")
    _check_object_fields(value["master"], {"path", "sha256", "count"}, path, "/master")
    _check_hash(value["master"].get("sha256"), path, "/master/sha256")
    if isinstance(value["master"].get("count"), bool) or not isinstance(value["master"].get("count"), int):
        _fail("manifest master count must be an integer", file=path, path="/master/count")
    if not isinstance(value["provenance"], dict) or set(value["provenance"]) != {"source_map", "raw_notes"}:
        _fail("manifest /provenance has an invalid shape", file=path, path="/provenance")
    for name in ("source_map", "raw_notes"):
        item = value["provenance"][name]
        if not isinstance(item, dict):
            _fail(f"manifest provenance /{name} must be an object", file=path, path=f"/provenance/{name}")
        _check_object_fields(item, {"path", "sha256"}, path, f"/provenance/{name}")
        _check_hash(item.get("sha256"), path, f"/provenance/{name}/sha256")
    for index, batch in enumerate(value["batches"]):
        prefix = f"/batches/{index}"
        if not isinstance(batch, dict):
            _fail("manifest batch entry must be an object", file=path, path=prefix)
        _check_object_fields(batch, {"batch_id", "path", "input_ids", "count", "sha256"}, path, prefix)
        if not all(isinstance(batch.get(key), str) for key in ("batch_id", "path")):
            _fail("manifest batch id and path must be strings", file=path, path=prefix)
        if not isinstance(batch.get("input_ids"), list) or any(not isinstance(item, str) for item in batch["input_ids"]):
            _fail("manifest batch input_ids must be a string list", file=path, path=f"{prefix}/input_ids")
        if isinstance(batch.get("count"), bool) or not isinstance(batch.get("count"), int):
            _fail("manifest batch count must be an integer", file=path, path=f"{prefix}/count")
        _check_hash(batch.get("sha256"), path, f"{prefix}/sha256")
    return value


def _check_object_fields(value: Any, fields: set[str], file: Path, path: str) -> None:
    if not isinstance(value, dict) or set(value) != fields:
        _fail(f"manifest {path} must contain exactly {sorted(fields)}", file=file, path=path)
    for key, item in value.items():
        if key in {"input_ids", "deck_ids", "note_type_ids"}:
            continue
        if key in {"selection_count", "batch_size", "count"}:
            valid = isinstance(item, int) and not isinstance(item, bool)
        else:
            valid = isinstance(item, str)
        if not valid:
            _fail(f"manifest {path}/{key} has an invalid type", file=file, path=f"{path}/{key}")


def _check_hash(value: Any, file: Path, path: str) -> None:
    if not isinstance(value, str) or _HASH.fullmatch(value) is None:
        _fail("manifest SHA-256 value must be 64 lowercase hexadecimal characters", file=file, path=path)


def _read_json(path: Path, label: str) -> Any:
    try:
        raw = path.read_bytes()
        return json.loads(raw.decode("utf-8"))
    except OSError as exc:
        _fail(f"cannot read {label}: {exc}", file=path)
    except UnicodeDecodeError as exc:
        _fail(f"{label} is not strict UTF-8 at byte {exc.start}", file=path)
    except json.JSONDecodeError as exc:
        _fail(f"invalid {label} JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}", file=path)


def _compare_manifest_binding(actual: dict[str, Any], expected: dict[str, Any], manifest_path: Path) -> None:
    for key in ("config", "source", "mapping", "schemas", "master", "provenance", "selection", "batch_size"):
        if actual[key] != expected[key]:
            _fail(f"manifest /{key} does not match current config or validated master provenance", file=manifest_path, path=f"/{key}")


def _read_master(config: StageConfig) -> tuple[bytes, list[dict[str, Any]], dict[str, Any]]:
    report = validate_input_dataset(config)
    assert config.paths.source_input is not None
    raw, records = read_jsonl(config.paths.source_input, "normalized master JSONL")
    ids = config.constraints.input_ids
    if ids is None or tuple(record.get("id") for record in records) != ids:
        _fail("normalized master IDs differ from frozen configured selection", file=config.paths.source_input, path="/id")
    return raw, records, report


def _audit_doc(
    config: StageConfig,
    master: list[dict[str, Any]],
    batch_results: list[dict[str, Any]],
    manifest_raw: bytes,
) -> dict[str, Any]:
    ids, _, _ = _require_settings(config)
    all_ids = [item for batch in batch_results for item in batch["actual_ids"]]
    overlaps: list[str] = []
    seen: set[str] = set()
    for item in all_ids:
        if item in seen and item not in overlaps:
            overlaps.append(item)
        seen.add(item)
    missing = [item for item in ids if item not in seen]
    foreign = [item for item in all_ids if item not in set(ids)]
    if config.source is None or config.normalization is None or config.paths.input_schema is None:
        _fail("source linkage audit settings are incomplete", file=config.config_path)
    _, source_map = read_jsonl(config.normalization.source_map, "source map JSONL")
    _, raw_notes = read_jsonl(config.normalization.raw_notes, "raw source notes JSONL")
    return {
        "schema": AUDIT_SCHEMA,
        "job_id": JOB_ID,
        "source_linkage": {
            "status": "pass",
            "master_records": len(master),
            "source_map_rows": len(source_map),
            "raw_note_rows": len(raw_notes),
            "native_project_id_pairs": len({(row.get("native_note_id"), row.get("project_id")) for row in source_map}),
            "unique_native_note_ids": len({row.get("native_note_id") for row in source_map}),
            "unique_project_ids": len({row.get("project_id") for row in source_map}),
        },
        "membership": {
            "status": "pass",
            "expected_count": len(ids),
            "actual_count": len(all_ids),
            "unique_count": len(set(all_ids)),
            "overlap_ids": overlaps,
            "missing_ids": missing,
            "foreign_ids": foreign,
        },
        "content_preserved": {
            "status": "pass",
            "master_records_compared": sum(item["content_compared"] for item in batch_results),
            "mismatches": [],
        },
        "hashes": {
            "config_sha256": config.config_sha256,
            "source_sha256": file_sha256(config.source.apkg),
            "mapping_contract_sha256": file_sha256(config.source.mapping_contract),
            "input_schema_sha256": file_sha256(config.paths.input_schema),
            "source_map_sha256": file_sha256(config.normalization.source_map),
            "raw_notes_sha256": file_sha256(config.normalization.raw_notes),
            "manifest_sha256": _sha(manifest_raw),
            "master_sha256": _sha(read_jsonl(config.paths.source_input, "normalized master JSONL")[0]),
            "batches": [
                {"batch_id": item["batch_id"], "path": item["path"], "sha256": item["sha256"]}
                for item in batch_results
            ],
        },
        "counts": {
            "master_records": len(master),
            "unique_master_ids": len({record["id"] for record in master}),
            "unique_master_expressions": len({record["expression"] for record in master}),
            "batches": len(batch_results),
        },
    }


def validate_batches(
    config: StageConfig, *, artifact_dir: Path | None = None, binding_owner: Path | None = None
) -> dict[str, Any]:
    """Validate membership/content, resolving new refs from the final manifest owner."""
    ids, size, output_dir = _require_settings(config)
    if config.source is None or config.normalization is None or config.paths.input_schema is None:
        _fail("source-aware validation config is incomplete", file=config.config_path)
    artifacts = Path(artifact_dir).resolve() if artifact_dir is not None else output_dir
    owner_path = (binding_owner or output_dir / "manifest.json").resolve()
    manifest_path = artifacts / "manifest.json"
    audit_path = artifacts / "audit.json"
    manifest_raw = manifest_path.read_bytes() if manifest_path.is_file() else b""
    if not manifest_raw:
        _fail("batch manifest is missing or empty", file=manifest_path)
    try:
        manifest_value = json.loads(manifest_raw.decode("utf-8"))
    except UnicodeDecodeError as exc:
        _fail(f"manifest is not strict UTF-8 at byte {exc.start}", file=manifest_path)
    except json.JSONDecodeError as exc:
        _fail(f"manifest JSON error at line {exc.lineno}, column {exc.colno}: {exc.msg}", file=manifest_path)
    manifest = _validate_manifest_shape(manifest_value, manifest_path)
    master_raw, master, _ = _read_master(config)
    expected_manifest = _base_manifest(config, master_raw, owner_path=owner_path, schema=manifest["schema"])
    expected_manifest["batches"] = [
        {**batch, "sha256": "0" * 64} for batch in _expected_batches(ids, size)
    ]
    _compare_manifest_binding(manifest, expected_manifest, manifest_path)
    if manifest["master"]["count"] != len(master) or manifest["master"]["sha256"] != _sha(master_raw):
        _fail("manifest master count or complete-file hash differs from validated master", file=manifest_path, path="/master")
    expected_batches = _expected_batches(ids, size)
    if len(manifest["batches"]) != len(expected_batches):
        _fail("manifest batch count differs from frozen selection and batch_size", file=manifest_path, path="/batches")
    master_by_id = {record["id"]: record for record in master}
    validator = _schema_validator(config.paths.input_schema)
    batch_results: list[dict[str, Any]] = []
    all_batch_ids: list[str] = []
    paths_seen: set[Path] = set()
    batch_ids_seen: set[str] = set()
    for index, (actual, expected) in enumerate(zip(manifest["batches"], expected_batches, strict=True), start=1):
        batch_id = expected["batch_id"]
        batch_file = artifacts / expected["path"]
        resolved_file = batch_file.resolve()
        if actual["batch_id"] in batch_ids_seen:
            _fail(f"duplicate batch ID {actual['batch_id']!r}", file=manifest_path, path=f"/batches/{index - 1}/batch_id")
        if resolved_file in paths_seen:
            _fail("duplicate resolved batch artifact path", file=manifest_path, path=f"/batches/{index - 1}/path")
        batch_ids_seen.add(actual["batch_id"])
        paths_seen.add(resolved_file)
        for key in ("batch_id", "path", "input_ids", "count"):
            if actual[key] != expected[key]:
                _fail(f"manifest batch {batch_id} /{key} differs from frozen ordered membership", file=manifest_path, path=f"/batches/{index - 1}/{key}")
        if actual["count"] != len(expected["input_ids"]) or actual["count"] > size or actual["count"] <= 0:
            _fail(f"manifest batch {batch_id} has invalid count", file=manifest_path, path=f"/batches/{index - 1}/count")
        if not batch_file.is_file():
            _fail(f"batch input file is missing for {batch_id}", file=batch_file)
        raw, records = read_jsonl(batch_file, f"{batch_id} JSONL")
        digest = _sha(raw)
        if digest != actual["sha256"]:
            _fail(f"batch {batch_id} complete-file SHA-256 mismatch", file=batch_file, path="/")
        validate_input_objects(
            records,
            validator,
            expected_ids=tuple(expected["input_ids"]),
            file=batch_file,
            batch_id=batch_id,
        )
        content_compared = 0
        for line, record in enumerate(records, start=1):
            input_id = record["id"]
            all_batch_ids.append(input_id)
            expected_record = master_by_id.get(input_id)
            if expected_record is None:
                _fail(f"batch {batch_id} line {line} has foreign input ID {input_id!r}", file=batch_file, record_id=input_id, path=f"/id")
            for field in ("id", "expression", "reading", "meaning_vi"):
                if record.get(field) != expected_record.get(field):
                    _fail(
                        f"batch {batch_id} line {line} input {input_id} path /{field} differs from validated master",
                        file=batch_file,
                        record_id=input_id,
                        path=f"/{field}",
                    )
            content_compared += 1
        batch_results.append({
            "batch_id": batch_id,
            "path": expected["path"],
            "count": len(records),
            "actual_ids": [record["id"] for record in records],
            "content_compared": content_compared,
            "sha256": digest,
        })
    if len(all_batch_ids) != len(set(all_batch_ids)):
        duplicate = next(item for i, item in enumerate(all_batch_ids) if item in all_batch_ids[:i])
        _fail(f"batch memberships overlap or duplicate input ID {duplicate!r}", file=manifest_path, path="/batches")
    if tuple(all_batch_ids) != ids:
        _fail("batch union does not equal the frozen ordered selection", file=manifest_path, path="/batches")
    audit = _audit_doc(config, master, batch_results, manifest_raw)
    if not audit_path.is_file():
        _fail("batch audit is missing", file=audit_path)
    stored_audit = _read_json(audit_path, "batch audit")
    if stored_audit != audit:
        _fail("persisted audit does not match validated artifacts", file=audit_path, path="/")
    return {
        "stage": "validate-batches",
        "status": "pass",
        "job_id": JOB_ID,
        "checked_counts": {
            "master_records": len(master),
            "batch_records": len(all_batch_ids),
            "batches": len(batch_results),
            "unique_ids": len(set(all_batch_ids)),
            "unique_expressions": len({record["expression"] for record in master}),
        },
        "manifest_path": str(manifest_path),
        "audit_path": str(audit_path),
        "membership": audit["membership"],
        "source_linkage": audit["source_linkage"],
        "content_preserved": audit["content_preserved"],
        "hashes": audit["hashes"],
    }


def prepare_batches(config: StageConfig, *, force: bool = False) -> dict[str, Any]:
    """Xác thực master đã chuẩn hóa rồi xuất bản các lô đầu vào ổn định."""
    ids, size, output_dir = _require_settings(config)
    targets = _preflight(config, force=force)
    master_raw, master, _ = _read_master(config)
    if tuple(record["id"] for record in master) != ids:
        _fail("normalized master order differs from frozen selection", file=config.paths.source_input, path="/id")
    groups = _expected_batches(ids, size)
    master_by_id = {record["id"]: record for record in master}
    batch_payloads: list[tuple[dict[str, Any], bytes]] = []
    manifest = _base_manifest(config, master_raw)
    for batch in groups:
        payload = b"".join(_compact_json(master_by_id[input_id]) + b"\n" for input_id in batch["input_ids"])
        batch_payloads.append((batch, payload))
        manifest["batches"].append({**batch, "sha256": _sha(payload)})
    manifest_raw = _pretty_json(manifest)
    provisional_results = [
        {
            "batch_id": batch["batch_id"],
            "path": batch["path"],
            "actual_ids": batch["input_ids"],
            "content_compared": batch["count"],
            "sha256": _sha(payload),
        }
        for batch, payload in batch_payloads
    ]
    audit = _audit_doc(config, master, provisional_results, manifest_raw)
    payloads: dict[Path, bytes] = {
        output_dir / "manifest.json": manifest_raw,
        output_dir / "audit.json": _pretty_json(audit),
    }
    for batch, raw in batch_payloads:
        payloads[output_dir / batch["path"]] = raw
    for target, payload in payloads.items():
        expected = targets.get("manifest" if target.name == "manifest.json" else "audit" if target.name == "audit.json" else target.parent.name)
        if expected is None or expected.resolve() != target.resolve():
            _fail("internal batch target calculation mismatch", file=target)
    output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".batching-stage-", dir=output_dir) as stage_name:
        stage = Path(stage_name)
        staged_targets: list[tuple[Path, Path]] = []
        for target, payload in payloads.items():
            relative = target.relative_to(output_dir)
            staged = stage / relative
            staged.parent.mkdir(parents=True, exist_ok=True)
            with staged.open("wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            staged_targets.append((staged, target))
        try:
            validate_batches(config, artifact_dir=stage, binding_owner=output_dir / "manifest.json")
        except InputStageError:
            raise
        for _, target in staged_targets:
            if _present(target) and not force:
                raise FileExistsError(f"Batch output appeared during staging; use --force: {target}")
        for staged, target in staged_targets:
            target.parent.mkdir(parents=True, exist_ok=True)
            os.replace(staged, target)
    return {
        "stage": "prepare-batches",
        "status": "pass",
        "job_id": JOB_ID,
        "checked_counts": {
            "master_records": len(master),
            "batches": len(groups),
            "batch_records": sum(item["count"] for item in groups),
            "unique_ids": len(ids),
            "unique_expressions": len({record["expression"] for record in master}),
        },
        "batch_sizes": [item["count"] for item in groups],
        "manifest_path": str(output_dir / "manifest.json"),
        "audit_path": str(output_dir / "audit.json"),
        "artifacts": {item["batch_id"]: str(output_dir / item["path"]) for item in groups},
        "hashes": {target.name if target.parent == output_dir else target.parent.name: _sha(payload) for target, payload in payloads.items()},
    }
