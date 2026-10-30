"""Build a synthetic native-linked acceptance graph through the production adapter."""

from __future__ import annotations

import copy
import hashlib
import json
import os
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import yaml

from jp_deck.aggregation import aggregate_output
from jp_deck.batching import prepare_batches
from jp_deck.config import load_stage_config
from jp_deck.normalization import normalize_source
from jp_deck.source_apkg import file_sha256
import jp_deck.sources.tango_n1_mimi.adapter as tango_adapter
from jp_deck.sources.tango_n1_mimi.adapter import FIELD_SIGNATURE
from helpers.synthetic_source import SYNTHETIC_DECK_ID, SYNTHETIC_NOTE_TYPE_ID, write_synthetic_apkg


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _json(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _jsonl(rows: list[dict]) -> bytes:
    return b"".join((json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8") for row in rows)


def _write(path: Path, raw: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return path


def _ref(owner: Path, target: Path) -> str:
    return Path(os.path.relpath(target.resolve(), owner.resolve().parent)).as_posix()


def _patch_profile(config, stack: ExitStack) -> None:
    source = config.source
    stack.enter_context(patch.object(tango_adapter, "SOURCE_SHA256", source.sha256))
    stack.enter_context(patch.object(tango_adapter, "MAPPING_SHA256", source.mapping_contract_sha256))
    stack.enter_context(patch.object(tango_adapter, "TARGET_DECK_ID", source.deck_ids[0]))
    stack.enter_context(patch.object(tango_adapter, "SUPPORTED_NOTE_TYPE_ID", source.note_type_ids[0]))


def _output(record: dict, revision: int) -> dict:
    sense_id = f"native-sense-{record['id'].rsplit('-', 1)[1]}"
    suffix = record["id"].rsplit("-", 1)[1]
    return {
        "schema_version": "0.1.0", "input_id": record["id"], "revision": revision,
        "headword": {"expression": record["expression"], "reading": record["reading"],
                     "pos": ["danh từ giả lập"], "evidence_refs": []},
        "senses": [{"sense_id": sense_id, "meaning_vi": f"Nghĩa giả lập {suffix}.",
                    "explanation_vi": f"Giải thích giả lập {suffix}.", "evidence_refs": []}],
        "examples": [],
        "collocations": [{"collocation_id": f"native-collocation-{suffix}", "sense_id": sense_id,
                           "expression": record["expression"] + "を試す", "reading": record["reading"] + "をためす",
                           "meaning_vi": "cụm kiểm thử", "usage_vi": "ngữ cảnh giả lập",
                           "frequency": None, "evidence_refs": []}],
        "related_terms": [], "confusables": [], "sources": [], "uncertainties": [],
    }


def build_native_aggregation_fixture(root: Path, *, package: bool = True) -> dict:
    """Generate a source-backed 3-note 2+1 replay using only fabricated source rows."""
    root = Path(root)
    native = root / "native"
    native.mkdir(parents=True, exist_ok=True)
    (native / "schemas").mkdir(parents=True, exist_ok=True)
    repo_root = Path(__file__).resolve().parents[2]
    for name in ("input.schema.json", "output.schema.json"):
        (native / "schemas" / name).write_bytes((repo_root / "schemas" / name).read_bytes())
    contract = native / "mapping-contract.md"
    contract.write_text("Synthetic native-linkage test contract; no real source is represented.\n", encoding="utf-8")
    source_path = native / "Tango_N1_MiMi_n1.apkg"
    notes = [
        {"id": 990001, "stt": "1", "furigana": "かくうごこう", "kanji": "架空語甲", "hanviet": "GIA KHONG",
         "nghia": "nghĩa giả lập alpha", "vidu": "架空語甲を試す。", "nghiavidu": "Thử từ giả lập.",
         "tudongnghia": "", "lientuong": "", "tutrainghia": "", "sound": ""},
        {"id": 990002, "stt": "2", "furigana": "きりわ", "kanji": "霧環", "hanviet": "VU HOAN",
         "nghia": "vòng sương giả lập", "vidu": "霧環を試す。", "nghiavidu": "Thử vòng sương.",
         "tudongnghia": "", "lientuong": "", "tutrainghia": "", "sound": ""},
        {"id": 990003, "stt": "3", "furigana": "ほしつづり", "kanji": "星綴", "hanviet": "TINH CHU",
         "nghia": "dệt sao giả lập", "vidu": "星綴を試す。", "nghiavidu": "Thử dệt sao.",
         "tudongnghia": "", "lientuong": "", "tutrainghia": "", "sound": ""},
    ]
    # Keep the exact production signature while every field value/GUID/native ID is fabricated.
    write_synthetic_apkg(source_path, notes, signature=FIELD_SIGNATURE)
    mapping_version = tango_adapter.MAPPING_VERSION
    project_ids = [f"{tango_adapter.PROJECT_ID_PREFIX}{note['id']}" for note in notes]
    batching_document = {
        "config_version": 2,
        "paths": {"source_input": "native-master.jsonl", "input_schema": "schemas/input.schema.json",
                  "output_schema": "schemas/output.schema.json", "output_dir": "build"},
        "source": {"apkg": source_path.name, "sha256": file_sha256(source_path),
                   "adapter": tango_adapter.ADAPTER_ID, "mapping_contract": contract.name,
                   "mapping_contract_version": mapping_version,
                   "mapping_contract_sha256": _sha(contract.read_bytes()),
                   "deck_ids": [SYNTHETIC_DECK_ID], "note_type_ids": [SYNTHETIC_NOTE_TYPE_ID],
                   "selection": {"order": "note_id_ascending", "count": len(notes)}},
        "normalization": {"source_map": "source-map.jsonl", "raw_notes": "raw-notes.jsonl",
                          "exceptions": "exceptions.json", "report": "normalization-report.json"},
        "constraints": {"input_ids": project_ids},
        "batching": {"batch_size": 2, "output_dir": "batches"},
    }
    batch_config_path = native / "batching.yaml"
    batch_config_path.write_text(yaml.safe_dump(batching_document, allow_unicode=True, sort_keys=False), encoding="utf-8")
    with ExitStack() as stack:
        normalize_config = load_stage_config(batch_config_path, stage="normalize")
        _patch_profile(normalize_config, stack)
        normalize_source(normalize_config)
        batch_config = load_stage_config(batch_config_path, stage="prepare-batches")
        prepared = prepare_batches(batch_config)
    manifest_path = native / "batches/manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    master_path = native / "native-master.jsonl"
    master_rows = [json.loads(line) for line in master_path.read_text(encoding="utf-8").splitlines()]
    input_schema_hash = _sha((native / "schemas/input.schema.json").read_bytes())
    output_schema_hash = _sha((native / "schemas/output.schema.json").read_bytes())
    contract_path = root / "data/enrichment-contract.md"
    contract_path.parent.mkdir(parents=True, exist_ok=True)
    contract_path.write_text("Synthetic enrichment acceptance contract; no linguistic approval is claimed.\n", encoding="utf-8")
    acceptance_paths: list[Path] = []
    revision_map: dict[str, int] = {}
    for batch_index, batch in enumerate(manifest["batches"], start=1):
        batch_id = batch["batch_id"]
        batch_input = native / "batches" / batch["path"]
        batch_inputs = [json.loads(line) for line in batch_input.read_text(encoding="utf-8").splitlines()]
        output_records = []
        for local_index, record in enumerate(batch_inputs):
            revision = 2 if batch_index == 1 and local_index == 0 else 1
            output_records.append(_output(record, revision)); revision_map[record["id"]] = revision
        output_path = _write(root / "data/outputs" / f"{batch_id}.jsonl", _jsonl(output_records))
        acceptance_dir = root / "data/acceptance"; acceptance_dir.mkdir(parents=True, exist_ok=True)
        validation_path = acceptance_dir / f"{batch_id}-validation.json"
        review_path = acceptance_dir / f"{batch_id}-review.json"
        acceptance_path = acceptance_dir / f"{batch_id}-acceptance.json"
        validation = {
            "schema": "jp-deck-batch-output-validation/v1", "status": "pass", "batch_id": batch_id,
            "artifact_path": _ref(validation_path, output_path), "artifact_sha256": _sha(output_path.read_bytes()),
            "input_path": _ref(validation_path, batch_input), "input_sha256": _sha(batch_input.read_bytes()),
            "input_ids": batch["input_ids"],
            "record_revisions": {row["input_id"]: row["revision"] for row in output_records},
            "schema_version": "0.1.0",
            "schemas": {"input_sha256": input_schema_hash, "output_sha256": output_schema_hash},
            "checks": {"schema": True, "membership": True, "references": True, "render": True},
            "command": "fabricated native-linkage test; no semantic attestation claimed",
        }
        review_records = []
        for row in output_records:
            review_records.append({
                "input_id": row["input_id"], "reviewed_revision": row["revision"],
                "structure": {"status": "pass", "method": "production native-linkage synthetic regression", "command": "test fixture"},
                "collocations": [{"collocation_id": row["collocations"][0]["collocation_id"],
                                  "status": "not_checked", "source_url": None,
                                  "observation": "Synthetic test evidence only; no source claim is made.",
                                  "queries_used": 0, "queries": []}],
                "findings": [], "verdict": "pass",
            })
        review = {
            "schema": "jp-deck-batch-review/v1", "batch_id": batch_id,
            "artifact_path": _ref(review_path, output_path), "artifact_sha256": _sha(output_path.read_bytes()),
            "scope": "schema-first-sampled-source/v1", "verdict": "pass", "source_sample": [],
            "records": review_records, "limitations": ["Fabricated native-linkage fixture; no linguistic attestation."],
        }
        validation_raw, review_raw = _json(validation), _json(review)
        validation_path.write_bytes(validation_raw); review_path.write_bytes(review_raw)
        receipt = {
            "schema": "jp-deck-batch-acceptance/v1", "job_id": manifest["job_id"],
            "batch_id": batch_id, "status": "accepted", "review_scope": review["scope"],
            "input_manifest": {"path": _ref(acceptance_path, manifest_path), "sha256": _sha(manifest_path.read_bytes())},
            "input": {"path": _ref(acceptance_path, batch_input), "sha256": _sha(batch_input.read_bytes()),
                      "input_ids": batch["input_ids"]},
            "contract": {"path": _ref(acceptance_path, contract_path), "sha256": _sha(contract_path.read_bytes())},
            "schemas": {"input_sha256": input_schema_hash, "output_sha256": output_schema_hash},
            "output": {"path": _ref(acceptance_path, output_path), "sha256": _sha(output_path.read_bytes()),
                       "artifact_revision": max(row["revision"] for row in output_records),
                       "record_revisions": {row["input_id"]: row["revision"] for row in output_records}},
            "validation": {"path": validation_path.name, "sha256": _sha(validation_raw)},
            "review": {"path": review_path.name, "sha256": _sha(review_raw)},
        }
        acceptance_path.write_bytes(_json(receipt)); acceptance_paths.append(acceptance_path)

    normalized_hash = _sha(master_path.read_bytes())
    aggregation_document = {
        "config_version": 2,
        "paths": {
            "input": "generated/aggregate.jsonl", "source_input": "native/native-master.jsonl",
            "input_schema": "native/schemas/input.schema.json", "output_schema": "native/schemas/output.schema.json",
        },
        "source": {
            **batching_document["source"], "apkg": "native/" + source_path.name,
            "mapping_contract": "native/" + contract.name,
        },
        "normalization": {key: "native/" + value for key, value in batching_document["normalization"].items()},
        "constraints": {"input_ids": project_ids, "revisions": revision_map, "schema_version": "0.1.0",
                        "source_input_sha256": normalized_hash},
        "aggregation": {
            "manifest": {"path": "native/batches/manifest.json", "sha256": _sha(manifest_path.read_bytes())},
            "acceptances": [_ref(root / "aggregation.yaml", path) for path in acceptance_paths],
            "contract": {"path": _ref(root / "aggregation.yaml", contract_path), "sha256": _sha(contract_path.read_bytes())},
            "provenance": "generated/provenance.json", "report": "generated/report.json",
            "review_scope": "schema-first-sampled-source/v1",
        },
    }
    if package:
        aggregation_document["paths"]["output_dir"] = "generated/apkg"
        aggregation_document["package"] = {
            "apkg_filename": "synthetic-native.apkg", "model_name": "Synthetic native source test model",
            "model_id": 1848570013, "deck_name": "Synthetic native source test deck", "deck_id": 1848570012,
            "guid_namespace": "jp-deck/synthetic-native-aggregation/v1", "stable_id_epoch_seconds": 1800000000.0,
        }
    config_path = root / "aggregation.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(yaml.safe_dump(aggregation_document, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return {
        "root": root, "config": config_path, "batch_config": batch_config_path, "manifest_path": manifest_path,
        "manifest": manifest, "acceptances": acceptance_paths, "input_ids": project_ids,
        "revisions": revision_map, "source_path": native / source_path.name,
        "expected_records": [_output(record, revision_map[record["id"]]) for record in master_rows],
    }
