"""Regression tests for deterministic enriched-batch aggregation and consumers."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
import zipfile
from unittest.mock import patch
from dataclasses import replace
from pathlib import Path

import yaml
from genanki import guid_for

from jp_deck.aggregation import AggregationContext, _report
from jp_deck.config import AggregationSettings, ConfigError, StageConfig, StageConstraints, StagePaths, load_stage_config
from jp_deck.validation import read_jsonl
from helpers.native_aggregation import build_native_aggregation_fixture

ROOT = Path(__file__).resolve().parents[1]
INPUT_SCHEMA = ROOT / "schemas/input.schema.json"
OUTPUT_SCHEMA = ROOT / "schemas/output.schema.json"
R5_EXPECTED_REVISIONS = {
    "word-00": 2,
    "word-01": 1,
    "word-02": 1,
    "word-03": 1,
    "word-04": 1,
}


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _jsonl_bytes(rows: list[dict]) -> bytes:
    return b"".join(
        (json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
        for row in rows
    )


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _write(path: Path, data: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def _source(input_id: str, expression: str) -> dict:
    return {"id": input_id, "expression": expression, "reading": "かな", "meaning_vi": "nghĩa"}


def _output(input_id: str, expression: str, revision: int, *, marker: str | None = None, reading: str = "かな") -> dict:
    marker = marker or input_id
    return {
        "schema_version": "0.1.0",
        "input_id": input_id,
        "revision": revision,
        "headword": {"expression": expression, "reading": reading, "pos": ["danh từ"], "evidence_refs": []},
        "senses": [{"sense_id": f"sense-{marker}", "meaning_vi": "nghĩa", "explanation_vi": f"giải thích {marker}", "evidence_refs": []}],
        "examples": [],
        "collocations": [{
            "collocation_id": f"coll-{marker}", "sense_id": f"sense-{marker}",
            "expression": f"{expression} を使う", "reading": f"{reading}をつかう",
            "meaning_vi": "dùng", "usage_vi": "cách dùng", "frequency": None, "evidence_refs": [],
        }],
        "related_terms": [],
        "confusables": [],
        "sources": [],
        "uncertainties": [],
    }


def _fixture(root: Path, *, group_sizes: tuple[int, ...] = (3, 2), package: bool = False,
             input_ids: tuple[str, ...] | None = None) -> dict:
    """Build an independent no-native-linkage manifest/receipt graph in a temp tree."""
    data = root / "data"
    master_ids = list(input_ids) if input_ids is not None else [f"word-{index:02d}" for index in range(sum(group_sizes))]
    if len(master_ids) != sum(group_sizes) or len(set(master_ids)) != len(master_ids):
        raise ValueError("synthetic fixture input_ids must be unique and match group_sizes")
    expressions = ["重複語" if index in (0, 3) else f"語{index:02d}" for index in range(len(master_ids))]
    master_rows = [_source(input_id, expression) for input_id, expression in zip(master_ids, expressions, strict=True)]
    master_raw = _jsonl_bytes(master_rows)
    master_path = _write(data / "master.jsonl", master_raw)
    contract_path = _write(data / "enrichment-contract.md", b"Synthetic enrichment contract for aggregation tests.\n")
    config_raw = b"synthetic-batching-config: independent fixture\n"
    batch_config_path = _write(data / "batching-config.yaml", config_raw)
    input_schema_path = _write(data / "schemas/input.schema.json", INPUT_SCHEMA.read_bytes())
    output_schema_path = _write(data / "schemas/output.schema.json", OUTPUT_SCHEMA.read_bytes())
    input_schema_hash = _sha(input_schema_path.read_bytes())
    output_schema_hash = _sha(output_schema_path.read_bytes())
    contract_hash = _sha(contract_path.read_bytes())

    batches: list[dict] = []
    acceptances: list[Path] = []
    revisions: dict[str, int] = {}
    offset = 0
    for batch_number, count in enumerate(group_sizes, start=1):
        batch_id = f"group-{batch_number:02d}"
        ids = master_ids[offset:offset + count]
        source_rows = master_rows[offset:offset + count]
        batch_input_raw = _jsonl_bytes(source_rows)
        batch_input_path = _write(data / "batches" / f"{batch_id}.jsonl", batch_input_raw)
        output_rows: list[dict] = []
        for local, (input_id, source) in enumerate(zip(ids, source_rows, strict=True)):
            revision = 2 if batch_number == 1 and local == 0 else 1
            revisions[input_id] = revision
            output_rows.append(_output(input_id, source["expression"], revision,
                                       marker=f"content-{offset + local:02d}", reading=source["reading"]))
        output_raw = _jsonl_bytes(output_rows)
        output_path = _write(data / "outputs" / f"{batch_id}.jsonl", output_raw)
        validation_path = data / "acceptance" / f"{batch_id}-validation.json"
        review_path = data / "acceptance" / f"{batch_id}-review.json"
        acceptance_path = data / "acceptance" / f"{batch_id}-acceptance.json"
        validation = {
            "schema": "jp-deck-batch-output-validation/v1", "status": "pass", "batch_id": batch_id,
            "artifact_path": "../outputs/" + output_path.name, "artifact_sha256": _sha(output_raw),
            "input_path": "../batches/" + batch_input_path.name, "input_sha256": _sha(batch_input_raw),
            "input_ids": ids, "record_revisions": {row["input_id"]: row["revision"] for row in output_rows},
            "schema_version": "0.1.0",
            "schemas": {"input_sha256": input_schema_hash, "output_sha256": output_schema_hash},
            "checks": {"schema": True, "membership": True, "references": True, "render": True},
            "command": "python -m jp_deck validate-output --config configs/synthetic-demo.yaml",
        }
        review_records = []
        for local, row in enumerate(output_rows):
            status = "unverified" if local == 0 else "not_checked"
            review_records.append({
                "input_id": row["input_id"], "reviewed_revision": row["revision"],
                "structure": {"status": "pass", "method": "synthetic schema/reference/render fixture", "command": "test fixture"},
                "collocations": [{
                    "collocation_id": row["collocations"][0]["collocation_id"], "status": status,
                    "source_url": None, "observation": "Source status is explicitly unverified in this structural test fixture.",
                    "queries_used": 0, "queries": [],
                }],
                "findings": [], "verdict": "pass",
            })
        source_sample = []
        if output_rows:
            first = output_rows[0]
            collocation_review = review_records[0]["collocations"][0]
            source_sample = [{
                "input_id": first["input_id"], "collection": "collocations",
                "item_id": first["collocations"][0]["collocation_id"], "status": collocation_review["status"],
                "source_url": collocation_review["source_url"], "observation": collocation_review["observation"],
            }]
        review = {
            "schema": "jp-deck-batch-review/v1", "batch_id": batch_id,
            "artifact_path": "../outputs/" + output_path.name, "artifact_sha256": _sha(output_raw),
            "scope": "schema-first-sampled-source/v1", "verdict": "pass",
            "source_sample": source_sample, "records": review_records,
            "limitations": ["Synthetic structural evidence only; no linguistic/source claim is made."],
        }
        validation_raw = _json_bytes(validation)
        review_raw = _json_bytes(review)
        _write(validation_path, validation_raw)
        _write(review_path, review_raw)
        receipt = {
            "schema": "jp-deck-batch-acceptance/v1", "job_id": "synthetic-independent-fixture",
            "batch_id": batch_id, "status": "accepted", "review_scope": "schema-first-sampled-source/v1",
            "input_manifest": {"path": "../manifest.json", "sha256": "pending"},
            "input": {"path": "../batches/" + batch_input_path.name, "sha256": _sha(batch_input_raw), "input_ids": ids},
            "contract": {"path": "../enrichment-contract.md", "sha256": contract_hash},
            "schemas": {"input_sha256": input_schema_hash, "output_sha256": output_schema_hash},
            "output": {"path": "../outputs/" + output_path.name, "sha256": _sha(output_raw),
                       "artifact_revision": max(row["revision"] for row in output_rows),
                       "record_revisions": {row["input_id"]: row["revision"] for row in output_rows}},
            "validation": {"path": validation_path.name, "sha256": _sha(validation_raw)},
            "review": {"path": review_path.name, "sha256": _sha(review_raw)},
        }
        _write(acceptance_path, _json_bytes(receipt))
        acceptances.append(acceptance_path)
        batches.append({"batch_id": batch_id, "path": f"batches/{batch_input_path.name}", "input_ids": ids,
                        "count": count, "sha256": _sha(batch_input_raw)})
        offset += count

    manifest = {
        "schema": "jp-deck-batch-manifest/v2", "job_id": "synthetic-independent-fixture",
        "config": {"config_path": "batching-config.yaml", "config_sha256": _sha(config_raw),
                   "source_input": "master.jsonl", "input_schema": "schemas/input.schema.json",
                   "input_ids": master_ids, "batch_size": max(group_sizes), "output_dir": "."},
        "source": None, "mapping": None, "schemas": {"input_sha256": input_schema_hash},
        "master": {"path": "master.jsonl", "sha256": _sha(master_raw), "count": len(master_rows)},
        "provenance": {"source_map": None, "raw_notes": None},
        "selection": {"order": "explicit_frozen_order", "input_ids": master_ids},
        "batch_size": max(group_sizes), "batches": batches,
    }
    manifest_path = _write(data / "manifest.json", _json_bytes(manifest))
    manifest_hash = _sha(manifest_path.read_bytes())
    for acceptance in acceptances:
        receipt = json.loads(acceptance.read_text(encoding="utf-8"))
        receipt["input_manifest"]["sha256"] = manifest_hash
        _write(acceptance, _json_bytes(receipt))

    paths = {
        "input": str((root / "generated/aggregate.jsonl").relative_to(root)),
        "source_input": str(master_path.relative_to(root)),
        "input_schema": str(input_schema_path.relative_to(root)),
        "output_schema": str(output_schema_path.relative_to(root)),
    }
    doc: dict = {
        "config_version": 2, "paths": paths,
        "constraints": {"input_ids": master_ids, "revisions": revisions,
                       "schema_version": "0.1.0", "source_input_sha256": _sha(master_raw)},
        "aggregation": {
            "manifest": {"path": str(manifest_path.relative_to(root)), "sha256": manifest_hash},
            "acceptances": [str(path.relative_to(root)) for path in acceptances],
            "contract": {"path": str(contract_path.relative_to(root)), "sha256": contract_hash},
            "provenance": "generated/provenance.json", "report": "generated/report.json",
            "review_scope": "schema-first-sampled-source/v1",
        },
    }
    if package:
        paths["output_dir"] = str((root / "generated/apkg").relative_to(root))
        doc["package"] = {
            "apkg_filename": "synthetic.apkg", "model_name": "Synthetic vocabulary", "model_id": 1661854648,
            "deck_name": "Synthetic deck", "deck_id": 1348730326,
            "guid_namespace": "jp-deck/aggregation-synthetic/v1", "stable_id_epoch_seconds": 1792454400.0,
        }
    config_path = _write(root / "aggregation.yaml", yaml.safe_dump(doc, allow_unicode=True, sort_keys=False).encode("utf-8"))
    return {"root": root, "config": config_path, "document": doc, "manifest": manifest,
            "master": master_rows, "expected_ids": master_ids, "expected_records": [
                _output(row["id"], row["expression"], revisions[row["id"]],
                        marker=f"content-{index:02d}", reading=row["reading"])
                for index, row in enumerate(master_rows)
            ], "revisions": revisions, "acceptances": acceptances}


def _rebind_output(acceptance_path: Path, rows: list[dict], expected_revisions: dict[str, int]) -> None:
    """Rebind all non-cryptographic outer claims so inner membership/schema gates are reached."""
    receipt = json.loads(acceptance_path.read_text(encoding="utf-8"))
    output_path = (acceptance_path.parent / receipt["output"]["path"]).resolve()
    output_raw = _jsonl_bytes(rows)
    output_path.write_bytes(output_raw)
    receipt["output"]["sha256"] = _sha(output_raw)
    receipt["output"]["record_revisions"] = expected_revisions
    validation_path = (acceptance_path.parent / receipt["validation"]["path"]).resolve()
    validation = json.loads(validation_path.read_text(encoding="utf-8"))
    validation["artifact_sha256"] = _sha(output_raw)
    validation["record_revisions"] = expected_revisions
    validation_raw = _json_bytes(validation)
    validation_path.write_bytes(validation_raw)
    receipt["validation"]["sha256"] = _sha(validation_raw)
    review_path = (acceptance_path.parent / receipt["review"]["path"]).resolve()
    review = json.loads(review_path.read_text(encoding="utf-8"))
    review["artifact_sha256"] = _sha(output_raw)
    review_raw = _json_bytes(review)
    review_path.write_bytes(review_raw)
    receipt["review"]["sha256"] = _sha(review_raw)
    acceptance_path.write_bytes(_json_bytes(receipt))


def _cli(root: Path, *args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    return subprocess.run([sys.executable, "-m", "jp_deck", *args], cwd=cwd or ROOT,
                          env=env, text=True, capture_output=True)


def _source_cli(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    wrapper = ROOT / "tests/helpers/run_synthetic_source_cli.py"
    return subprocess.run([sys.executable, str(wrapper), *args], cwd=cwd or ROOT,
                          env=env, text=True, capture_output=True)


class AggregationTests(unittest.TestCase):
    def test_config_typed_aggregation_and_exact_revision_map(self):
        with tempfile.TemporaryDirectory() as temp:
            fixture = _fixture(Path(temp) / "fixture")
            config = load_stage_config(fixture["config"], stage="aggregate-output")
            self.assertEqual(config.constraints.input_ids, tuple(fixture["expected_ids"]))
            self.assertIsNone(config.constraints.revision)
            self.assertEqual(config.constraints.revisions, fixture["revisions"])
            self.assertEqual(config.aggregation.review_scope, "schema-first-sampled-source/v1")
            for mutation, message in (
                (lambda d: d["constraints"]["revisions"].__setitem__(fixture["expected_ids"][0], True), "revisions"),
                (lambda d: d["constraints"]["revisions"].pop(fixture["expected_ids"][0]), "exact"),
                (lambda d: d["constraints"].__setitem__("revision", 1), "mutually exclusive"),
                (lambda d: d["aggregation"].__setitem__("skip_review", True), "unknown key"),
            ):
                document = copy.deepcopy(fixture["document"])
                mutation(document)
                path = fixture["root"] / "invalid.yaml"
                path.write_text(yaml.safe_dump(document, allow_unicode=True, sort_keys=False), encoding="utf-8")
                with self.subTest(expected=message), self.assertRaisesRegex(ConfigError, message):
                    load_stage_config(path, stage="aggregate-output")

    def test_aggregate_cli_deterministic_full_payload_and_receipt_order(self):
        with tempfile.TemporaryDirectory() as temp:
            fixture = _fixture(Path(temp) / "fixture")
            unrelated = Path(temp) / "unrelated"; unrelated.mkdir()
            result = _cli(fixture["root"], "aggregate-output", "--config", str(fixture["config"]), cwd=unrelated)
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["status"], "pass")
            aggregate_path = Path(fixture["document"]["paths"]["input"])
            if not aggregate_path.is_absolute():
                aggregate_path = fixture["root"] / aggregate_path
            first_bytes = aggregate_path.read_bytes()
            _, rows = read_jsonl(aggregate_path, "test aggregate")
            literal_facts = [
                ("word-00", "重複語", 2, "content-00", "group-01", 1),
                ("word-01", "語01", 1, "content-01", "group-01", 2),
                ("word-02", "語02", 1, "content-02", "group-01", 3),
                ("word-03", "重複語", 1, "content-03", "group-02", 1),
                ("word-04", "語04", 1, "content-04", "group-02", 2),
            ]
            self.assertEqual([row["input_id"] for row in rows], [fact[0] for fact in literal_facts])
            literal_expected = []
            for input_id, expression, revision, marker, _batch, _source_row in literal_facts:
                sense_id, collocation_id = f"sense-{marker}", f"coll-{marker}"
                literal_expected.append({
                    "schema_version": "0.1.0", "input_id": input_id, "revision": revision,
                    "headword": {"expression": expression, "reading": "かな", "pos": ["danh từ"], "evidence_refs": []},
                    "senses": [{"sense_id": sense_id, "meaning_vi": "nghĩa", "explanation_vi": f"giải thích {marker}", "evidence_refs": []}],
                    "examples": [],
                    "collocations": [{"collocation_id": collocation_id, "sense_id": sense_id,
                                      "expression": f"{expression} を使う", "reading": "かなをつかう",
                                      "meaning_vi": "dùng", "usage_vi": "cách dùng", "frequency": None, "evidence_refs": []}],
                    "related_terms": [], "confusables": [], "sources": [], "uncertainties": [],
                })
            self.assertEqual(rows, literal_expected)
            self.assertEqual(payload["input_sha256"], _sha(first_bytes))
            expected_rows = []
            for row_number, (input_id, _expression, revision, _marker, batch_id, source_row) in enumerate(literal_facts, start=1):
                source_path = fixture["root"] / "data/outputs" / f"{batch_id}.jsonl"
                expected_rows.append({
                    "row": row_number, "input_id": input_id, "batch_id": batch_id,
                    "source_output_path": "../data/outputs/" + source_path.name,
                    "source_output_sha256": _sha(source_path.read_bytes()),
                    "source_record_number": source_row,
                    "record_revision": revision,
                })
            self.assertEqual(payload["provenance"]["rows"], expected_rows)
            second = _cli(fixture["root"], "aggregate-output", "--config", str(fixture["config"]), "--force")
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(aggregate_path.read_bytes(), first_bytes)
            validate = _cli(fixture["root"], "validate-aggregate", "--config", str(fixture["config"]), cwd=unrelated)
            self.assertEqual(validate.returncode, 0, validate.stderr)
            self.assertEqual(json.loads(validate.stdout)["status"], "pass")

    def test_portable_graph_relocates_from_final_owners_and_runs_all_downstream_consumers(self):
        with tempfile.TemporaryDirectory() as temp:
            temporary_root = Path(temp)
            original = temporary_root / "original"
            fixture = _fixture(original, package=True)
            aggregate = _cli(original, "aggregate-output", "--config", str(fixture["config"]))
            self.assertEqual(aggregate.returncode, 0, aggregate.stderr)
            self.assertEqual(json.loads(aggregate.stdout)["status"], "pass")

            manifest_path = original / "data/manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["schema"], "jp-deck-batch-manifest/v2")
            for binding in ("config_path", "source_input", "input_schema", "output_dir"):
                self.assertFalse(Path(manifest["config"][binding]).is_absolute(), binding)
            self.assertFalse(Path(manifest["master"]["path"]).is_absolute())
            self.assertFalse(Path(manifest["batches"][0]["path"]).is_absolute())

            provenance_path = original / "generated/provenance.json"
            report_path = original / "generated/report.json"
            provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(provenance["schema"], "jp-deck-aggregate-provenance/v2")
            self.assertEqual(report["schema"], "jp-deck-aggregate-report/v2")
            self.assertFalse(Path(provenance["config"]["path"]).is_absolute())
            self.assertFalse(Path(provenance["aggregate"]["path"]).is_absolute())
            self.assertFalse(Path(provenance["rows"][0]["source_output_path"]).is_absolute())
            self.assertFalse(Path(report["aggregate_path"]).is_absolute())
            self.assertFalse(Path(report["provenance_path"]).is_absolute())

            protected_names = [
                "data/manifest.json", "data/acceptance/group-01-acceptance.json",
                "data/acceptance/group-01-review.json", "data/acceptance/group-01-validation.json",
                "generated/aggregate.jsonl", "generated/provenance.json", "generated/report.json",
            ]
            original_hashes = {name: _sha((original / name).read_bytes()) for name in protected_names}
            relocated = temporary_root / "relocated-tree"
            shutil.copytree(original, relocated)
            shutil.rmtree(original)
            cwd = temporary_root / "unrelated-cwd"
            cwd.mkdir()
            (cwd / "manifest.json").write_text("not the declaring manifest", encoding="utf-8")
            (cwd / "group-01-review.json").write_text("not the declaring review", encoding="utf-8")
            config = relocated / "aggregation.yaml"

            for stage in ("validate-aggregate", "validate-output", "build"):
                result = _cli(relocated, stage, "--config", str(config), cwd=cwd)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(json.loads(result.stdout)["status"], "pass")
            audit_path = relocated / "generated/apkg/audit.json"
            audit = json.loads(audit_path.read_text(encoding="utf-8"))
            self.assertEqual(audit["audit_version"], 3)
            for raw in (audit["build"]["input_path"], audit["build"]["source_input_path"],
                        audit["build"]["configuration"]["path"]):
                self.assertFalse(Path(raw).is_absolute())
            self.assertEqual(
                {name: _sha((relocated / name).read_bytes()) for name in protected_names},
                original_hashes,
            )
            replay = _cli(relocated, "validate-aggregate", "--config", str(config), cwd=cwd)
            self.assertEqual(replay.returncode, 0, replay.stderr)

    def test_portable_report_rebases_native_source_path_after_relocation(self):
        def report_for(root: Path, *, schema: str = "jp-deck-batch-manifest/v2") -> dict:
            aggregation = AggregationSettings(
                manifest_path=root / "data/manifest.json", manifest_sha256="a" * 64,
                acceptances=(), contract_path=root / "data/contract.md", contract_sha256="b" * 64,
                provenance_path=root / "generated/provenance.json", report_path=root / "generated/report.json",
                review_scope="schema-first-sampled-source/v1",
            )
            config = StageConfig(
                paths=StagePaths(
                    input=root / "generated/aggregate.jsonl", source_input=root / "data/master.jsonl",
                    input_schema=INPUT_SCHEMA, output_schema=OUTPUT_SCHEMA,
                ),
                package=None,
                constraints=StageConstraints(input_ids=("demo-001",), revisions={"demo-001": 1}, schema_version="0.1.0"),
                source=None, normalization=None, config_path=root / "aggregation.yaml", config_sha256="c" * 64,
                aggregation=aggregation,
            )
            context = AggregationContext(
                config=config, manifest={"schema": schema}, manifest_sha256="d" * 64,
                master=[_source("demo-001", "架空語")], master_sha256="e" * 64,
                input_schema_sha256="f" * 64, output_schema_sha256="0" * 64, contract_sha256="b" * 64,
                native_source_linkage={"verified": True, "evidence": {
                    "source_path": str((root / "source/synthetic.apkg").resolve()),
                    "source_sha256": "1" * 64, "linked_records": 1,
                }},
                batches=(object(),),
            )
            return _report(context, [_output("demo-001", "架空語", 1)], "2" * 64, b"synthetic provenance")

        with tempfile.TemporaryDirectory() as temp:
            original = Path(temp) / "original"
            relocated = Path(temp) / "relocated"
            original_report = report_for(original)
            relocated_report = report_for(relocated)
            source_reference = original_report["native_source_linkage"]["evidence"]["source_path"]
            self.assertEqual(source_reference, "../source/synthetic.apkg")
            self.assertEqual(original_report, relocated_report)
            self.assertFalse(Path(source_reference).is_absolute())
            legacy_report = report_for(original, schema="jp-deck-batch-manifest/v1")
            self.assertEqual(legacy_report["schema"], "jp-deck-aggregate-report/v1")
            self.assertTrue(Path(legacy_report["native_source_linkage"]["evidence"]["source_path"]).is_absolute())

    def test_schema_first_review_accepts_unverified_sample_but_strict_scope_rejects(self):
        with tempfile.TemporaryDirectory() as temp:
            fixture = _fixture(Path(temp) / "fixture")
            ok = _cli(fixture["root"], "aggregate-output", "--config", str(fixture["config"]))
            self.assertEqual(ok.returncode, 0, ok.stderr)
            strict = copy.deepcopy(fixture["document"])
            strict["aggregation"]["review_scope"] = "structure-and-collocation-attestation/v1"
            for acceptance_path in fixture["acceptances"]:
                receipt = json.loads(acceptance_path.read_text(encoding="utf-8"))
                receipt["review_scope"] = strict["aggregation"]["review_scope"]
                review_path = (acceptance_path.parent / receipt["review"]["path"]).resolve()
                review = json.loads(review_path.read_text(encoding="utf-8"))
                review["scope"] = strict["aggregation"]["review_scope"]
                review_raw = _json_bytes(review)
                review_path.write_bytes(review_raw)
                receipt["review"]["sha256"] = _sha(review_raw)
                acceptance_path.write_bytes(_json_bytes(receipt))
            path = fixture["root"] / "strict.yaml"
            path.write_text(yaml.safe_dump(strict, allow_unicode=True, sort_keys=False), encoding="utf-8")
            failed = _cli(fixture["root"], "aggregate-output", "--config", str(path), "--force")
            self.assertEqual(failed.returncode, 2, failed.stdout + failed.stderr)
            self.assertIn("attested", failed.stderr)

    def test_reordered_unbound_candidate_fails_accepted_output_hash(self):
        with tempfile.TemporaryDirectory() as temp:
            fixture = _fixture(Path(temp) / "fixture")
            receipt_path = fixture["acceptances"][0]
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            output_path = (receipt_path.parent / receipt["output"]["path"]).resolve()
            rows = [json.loads(line) for line in output_path.read_text(encoding="utf-8").splitlines()]
            rows[0], rows[1] = rows[1], rows[0]
            output_path.write_bytes(_jsonl_bytes(rows))
            failed = _cli(fixture["root"], "aggregate-output", "--config", str(fixture["config"]))
            self.assertEqual(failed.returncode, 2, failed.stdout + failed.stderr)
            self.assertIn("SHA-256", failed.stderr)
            self.assertFalse((fixture["root"] / "generated/aggregate.jsonl").exists())

    def test_missing_foreign_duplicate_acceptances_and_artifact_aliases_fail(self):
        cases = ("missing", "foreign", "duplicate_batch", "duplicate_path", "same_output")
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temp:
                fixture = _fixture(Path(temp) / "fixture")
                document = copy.deepcopy(fixture["document"])
                acceptance_paths = list(fixture["acceptances"])
                if case == "missing":
                    document["aggregation"]["acceptances"] = [str(acceptance_paths[0].relative_to(fixture["root"]))]
                    diagnostic = "missing batch acceptance"
                elif case == "duplicate_path":
                    document["aggregation"]["acceptances"] = [str(acceptance_paths[0].relative_to(fixture["root"]))] * 2
                    diagnostic = "duplicate resolved artifact paths"
                else:
                    receipt = json.loads(acceptance_paths[1].read_text(encoding="utf-8"))
                    if case == "foreign":
                        receipt["batch_id"] = "foreign-group"
                    elif case == "duplicate_batch":
                        receipt["batch_id"] = json.loads(acceptance_paths[0].read_text(encoding="utf-8"))["batch_id"]
                    else:
                        first_receipt = json.loads(acceptance_paths[0].read_text(encoding="utf-8"))
                        receipt["output"]["path"] = first_receipt["output"]["path"]
                        receipt["output"]["sha256"] = first_receipt["output"]["sha256"]
                    acceptance_paths[1].write_bytes(_json_bytes(receipt))
                    diagnostic = ("foreign acceptance" if case == "foreign" else
                                  "duplicate acceptance" if case == "duplicate_batch" else "same enriched artifact")
                path = fixture["root"] / f"{case}.yaml"
                path.write_text(yaml.safe_dump(document, allow_unicode=True, sort_keys=False), encoding="utf-8")
                result = _cli(fixture["root"], "aggregate-output", "--config", str(path))
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertIn(diagnostic, result.stderr)
                self.assertFalse((fixture["root"] / "generated/aggregate.jsonl").exists())

    def test_rebound_candidate_membership_mutations_fail_at_inner_gate(self):
        for case in ("missing", "foreign", "duplicate", "reordered", "cross_batch_duplicate", "cross_batch_swap"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temp:
                fixture = _fixture(Path(temp) / "fixture")
                first = [copy.deepcopy(row) for row in fixture["expected_records"][:3]]
                second = [copy.deepcopy(row) for row in fixture["expected_records"][3:]]
                if case == "missing":
                    first.pop()
                elif case == "foreign":
                    first[0]["input_id"] = "foreign-word"
                elif case == "duplicate":
                    first[1] = copy.deepcopy(first[0])
                elif case == "reordered":
                    first[0], first[1] = first[1], first[0]
                elif case == "cross_batch_duplicate":
                    second[0] = copy.deepcopy(first[0])
                else:
                    first[0], second[0] = second[0], first[0]
                expected_first_revisions = {input_id: fixture["revisions"][input_id] for input_id in fixture["expected_ids"][:3]}
                expected_second_revisions = {input_id: fixture["revisions"][input_id] for input_id in fixture["expected_ids"][3:]}
                if case != "cross_batch_duplicate":
                    _rebind_output(fixture["acceptances"][0], first, expected_first_revisions)
                if case in {"cross_batch_duplicate", "cross_batch_swap"}:
                    _rebind_output(fixture["acceptances"][1], second, expected_second_revisions)
                result = _cli(fixture["root"], "aggregate-output", "--config", str(fixture["config"]))
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                if case == "duplicate":
                    self.assertIn("duplicate input_id", result.stderr)
                    self.assertIn("missing=", result.stderr)
                elif case in {"cross_batch_duplicate", "cross_batch_swap"}:
                    self.assertIn("assigned to", result.stderr)
                    self.assertIn("word-00" if case == "cross_batch_duplicate" else "word-03", result.stderr)
                else:
                    self.assertIn("membership", result.stderr)
                self.assertFalse((fixture["root"] / "generated/aggregate.jsonl").exists())

    def test_receipt_review_scope_coverage_revision_and_schema_bindings_are_enforced(self):
        cases = ("missing-review", "parent-verdict", "incomplete-records", "wrong-revision", "wrong-scope",
                 "not-run", "attested-without-url", "contradicted", "foreign-sample", "sample-status-mismatch")
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temp:
                fixture = _fixture(Path(temp) / "fixture")
                acceptance = fixture["acceptances"][0]
                receipt = json.loads(acceptance.read_text(encoding="utf-8"))
                review_path = (acceptance.parent / receipt["review"]["path"]).resolve()
                if case == "missing-review":
                    review_path.unlink()
                else:
                    review = json.loads(review_path.read_text(encoding="utf-8"))
                    if case == "parent-verdict":
                        review["verdict"] = "needs_revision"
                    elif case == "incomplete-records":
                        review["records"].pop()
                    elif case == "wrong-revision":
                        review["records"][0]["reviewed_revision"] += 1
                    elif case == "wrong-scope":
                        review["scope"] = "structure-and-collocation-attestation/v1"
                    elif case == "not-run":
                        review["records"][0]["structure"]["status"] = "not_run"
                    elif case == "attested-without-url":
                        review["records"][0]["collocations"][0]["status"] = "attested"
                        review["records"][0]["collocations"][0]["observation"] = "Claimed support without a URL."
                        review["source_sample"][0]["status"] = "attested"
                        review["source_sample"][0]["observation"] = "Claimed support without a URL."
                    elif case == "contradicted":
                        review["records"][0]["collocations"][0]["status"] = "contradicted"
                        review["source_sample"][0]["status"] = "contradicted"
                    elif case == "foreign-sample":
                        review["source_sample"][0]["item_id"] = "missing-collocation"
                    elif case == "sample-status-mismatch":
                        review["source_sample"][0]["status"] = "not_checked"
                    review_raw = _json_bytes(review)
                    review_path.write_bytes(review_raw)
                    receipt["review"]["sha256"] = _sha(review_raw)
                    acceptance.write_bytes(_json_bytes(receipt))
                result = _cli(fixture["root"], "aggregate-output", "--config", str(fixture["config"]))
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertFalse((fixture["root"] / "generated/aggregate.jsonl").exists())

    def test_report_and_receipt_schemas_reject_unknown_and_malformed_values(self):
        with tempfile.TemporaryDirectory() as temp:
            fixture = _fixture(Path(temp) / "fixture")
            acceptance = fixture["acceptances"][0]
            receipt = json.loads(acceptance.read_text(encoding="utf-8"))
            receipt["accepted"] = True
            acceptance.write_bytes(_json_bytes(receipt))
            result = _cli(fixture["root"], "aggregate-output", "--config", str(fixture["config"]))
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertIn("Additional properties", result.stderr)
        with tempfile.TemporaryDirectory() as temp:
            fixture = _fixture(Path(temp) / "fixture")
            acceptance = fixture["acceptances"][0]
            receipt = json.loads(acceptance.read_text(encoding="utf-8"))
            review_path = (acceptance.parent / receipt["review"]["path"]).resolve()
            review = json.loads(review_path.read_text(encoding="utf-8"))
            review["records"][0]["structure"]["status"] = "maybe"
            review_raw = _json_bytes(review)
            review_path.write_bytes(review_raw)
            receipt["review"]["sha256"] = _sha(review_raw)
            acceptance.write_bytes(_json_bytes(receipt))
            result = _cli(fixture["root"], "aggregate-output", "--config", str(fixture["config"]))
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertIn("malformed batch review report", result.stderr)

    def test_human_disposition_is_hash_revision_path_and_correction_bound(self):
        cases = ("valid-nonblocking", "stale-output-hash", "foreign-id", "wrong-revision",
                 "wrong-review-hash", "bad-pointer", "wrong-output-path", "wrong-review-path", "malformed")
        expected_messages = {
            "stale-output-hash": "artifact hash differs",
            "foreign-id": "foreign input_id",
            "wrong-revision": "record_revisions differ",
            "wrong-review-hash": "review hash differs",
            "bad-pointer": "target does not exist",
            "wrong-output-path": "artifact_path differs",
            "wrong-review-path": "review_path differs",
            "malformed": "malformed human disposition",
        }
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temp:
                fixture = _fixture(Path(temp) / "fixture", package=True)
                acceptance = fixture["acceptances"][0]
                receipt = copy.deepcopy(json.loads(acceptance.read_text(encoding="utf-8")))
                review_path = (acceptance.parent / receipt["review"]["path"]).resolve()
                output_path = (acceptance.parent / receipt["output"]["path"]).resolve()
                input_path = (acceptance.parent / receipt["input"]["path"]).resolve()
                validation_path = (acceptance.parent / receipt["validation"]["path"]).resolve()
                manifest_path = (acceptance.parent / receipt["input_manifest"]["path"]).resolve()
                contract_path = (acceptance.parent / receipt["contract"]["path"]).resolve()
                input_id = fixture["expected_ids"][0]
                disposition = {
                    "schema": "jp-deck-human-disposition/v1", "batch_id": receipt["batch_id"],
                    "artifact_path": receipt["output"]["path"],
                    "artifact_sha256": _sha(output_path.read_bytes()),
                    "review_path": receipt["review"]["path"],
                    "review_sha256": _sha(review_path.read_bytes()),
                    "record_revisions": copy.deepcopy(receipt["output"]["record_revisions"]),
                    "findings": [{"input_id": input_id, "path": "/collocations/0/expression",
                                  "status": "unverified", "requires_correction": False,
                                  "observation": "Valid nonblocking control; no approval is claimed."}],
                }
                if case == "stale-output-hash":
                    disposition["artifact_sha256"] = "0" * 64
                elif case == "foreign-id":
                    disposition["findings"][0]["input_id"] = "foreign-id"
                elif case == "wrong-revision":
                    disposition["record_revisions"][input_id] = 99
                elif case == "wrong-review-hash":
                    disposition["review_sha256"] = "0" * 64
                elif case == "bad-pointer":
                    disposition["findings"][0]["path"] = "/missing"
                elif case == "wrong-output-path":
                    disposition["artifact_path"] = "../outputs/another-output.jsonl"
                elif case == "wrong-review-path":
                    disposition["review_path"] = "../acceptance/another-review.json"
                elif case == "malformed":
                    disposition["accepted"] = True
                disposition_path = acceptance.parent / "human-disposition.json"
                disposition_raw = _json_bytes(disposition)
                disposition_path.write_bytes(disposition_raw)
                receipt["human_disposition"] = {"path": disposition_path.name, "sha256": _sha(disposition_raw)}
                acceptance.write_bytes(_json_bytes(receipt))
                receipt_bytes = acceptance.read_bytes()
                protected = {path: _sha(path.read_bytes()) for path in
                             (output_path, review_path, validation_path, input_path, manifest_path, contract_path,
                              acceptance, disposition_path, fixture["config"])}
                result = _cli(fixture["root"], "aggregate-output", "--config", str(fixture["config"]))
                if case == "valid-nonblocking":
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertTrue((fixture["root"] / "generated/aggregate.jsonl").is_file())
                    continue
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                failure = json.loads(result.stderr)
                error = failure["errors"][0]
                self.assertEqual(error["file"], str(disposition_path.resolve()))
                self.assertIn(expected_messages[case], error["message"])
                if case == "foreign-id":
                    self.assertEqual(error["record_id"], "foreign-id")
                if case == "bad-pointer":
                    self.assertEqual(error["path"], "/missing")
                self.assertEqual(_sha(acceptance.read_bytes()), _sha(receipt_bytes))
                self.assertEqual({path: _sha(path.read_bytes()) for path in protected}, protected)
                for generated in (fixture["root"] / "generated/aggregate.jsonl",
                                  fixture["root"] / "generated/provenance.json",
                                  fixture["root"] / "generated/report.json",
                                  fixture["root"] / "generated/apkg/synthetic.apkg",
                                  fixture["root"] / "generated/apkg/preview.html",
                                  fixture["root"] / "generated/apkg/audit.json"):
                    self.assertFalse(generated.exists(), generated)

    def test_stale_review_hash_and_frozen_master_or_batch_bytes_fail(self):
        with tempfile.TemporaryDirectory() as temp:
            fixture = _fixture(Path(temp) / "fixture")
            acceptance = fixture["acceptances"][0]
            receipt = json.loads(acceptance.read_text(encoding="utf-8"))
            receipt["review"]["sha256"] = "0" * 64
            acceptance.write_bytes(_json_bytes(receipt))
            result = _cli(fixture["root"], "aggregate-output", "--config", str(fixture["config"]))
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertIn("review report SHA-256 mismatch", result.stderr)
            self.assertFalse((fixture["root"] / "generated/aggregate.jsonl").exists())

        for relative_path, expected_error in (("data/master.jsonl", "master complete-file SHA-256"),
                                              ("data/batches/group-01.jsonl", "batch group-01 input SHA-256 mismatch")):
            with self.subTest(path=relative_path), tempfile.TemporaryDirectory() as temp:
                fixture = _fixture(Path(temp) / "fixture")
                path = fixture["root"] / relative_path
                mutated = path.read_bytes().replace('"meaning_vi":"nghĩa"'.encode("utf-8"), b'"meaning_vi":"mutation"', 1)
                self.assertNotEqual(mutated, path.read_bytes())
                path.write_bytes(mutated)
                result = _cli(fixture["root"], "aggregate-output", "--config", str(fixture["config"]))
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertIn(expected_error, result.stderr)
                self.assertFalse((fixture["root"] / "generated/aggregate.jsonl").exists())

        with tempfile.TemporaryDirectory() as temp:
            fixture = _fixture(Path(temp) / "fixture")
            manifest_path = fixture["root"] / "data/manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            batch_path = fixture["root"] / "data/batches/group-01.jsonl"
            batch_rows = [json.loads(line) for line in batch_path.read_text(encoding="utf-8").splitlines()]
            batch_rows[0]["meaning_vi"] = "rebound but differs from frozen master"
            batch_raw = _jsonl_bytes(batch_rows)
            batch_path.write_bytes(batch_raw)
            manifest["batches"][0]["sha256"] = _sha(batch_raw)
            manifest_raw = _json_bytes(manifest)
            manifest_path.write_bytes(manifest_raw)
            manifest_hash = _sha(manifest_raw)
            config_doc = copy.deepcopy(fixture["document"])
            config_doc["aggregation"]["manifest"]["sha256"] = manifest_hash
            config_path = fixture["root"] / "rebound-input-manifest.yaml"
            config_path.write_text(yaml.safe_dump(config_doc, allow_unicode=True, sort_keys=False), encoding="utf-8")
            for acceptance in fixture["acceptances"]:
                receipt = json.loads(acceptance.read_text(encoding="utf-8"))
                receipt["input_manifest"]["sha256"] = manifest_hash
                if receipt["batch_id"] == "group-01":
                    receipt["input"]["sha256"] = _sha(batch_raw)
                    validation_path = (acceptance.parent / receipt["validation"]["path"]).resolve()
                    validation = json.loads(validation_path.read_text(encoding="utf-8"))
                    validation["input_sha256"] = _sha(batch_raw)
                    validation_raw = _json_bytes(validation)
                    validation_path.write_bytes(validation_raw)
                    receipt["validation"]["sha256"] = _sha(validation_raw)
                acceptance.write_bytes(_json_bytes(receipt))
            result = _cli(fixture["root"], "aggregate-output", "--config", str(config_path))
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            error = json.loads(result.stderr)["errors"][0]
            self.assertIn("/meaning_vi differs from frozen master", error["message"])
            self.assertEqual(error["record_id"], "word-00")
            self.assertEqual(error["file"], str(batch_path.resolve()))
            self.assertEqual(error["path"], "/meaning_vi")
            self.assertFalse((fixture["root"] / "generated/aggregate.jsonl").exists())

    def test_schema_reference_and_accepted_hash_checks_survive_rebound_outer_reports(self):
        for case in ("schema", "reference"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temp:
                fixture = _fixture(Path(temp) / "fixture")
                rows = copy.deepcopy(fixture["expected_records"][:3])
                expected_revisions = {input_id: fixture["revisions"][input_id] for input_id in fixture["expected_ids"][:3]}
                if case == "schema":
                    rows[0]["not_allowed"] = 1
                    expected_message = "Additional properties"
                else:
                    rows[0]["senses"][0]["evidence_refs"] = [{"source_id": "absent", "claim_path": "/senses/0/meaning_vi"}]
                    expected_message = "unknown source_id"
                _rebind_output(fixture["acceptances"][0], rows, expected_revisions)
                result = _cli(fixture["root"], "aggregate-output", "--config", str(fixture["config"]))
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertIn(expected_message, result.stderr)
                self.assertFalse((fixture["root"] / "generated/aggregate.jsonl").exists())

    def test_manifest_schema_master_and_contract_fingerprints_are_cross_checked(self):
        with tempfile.TemporaryDirectory() as temp:
            fixture = _fixture(Path(temp) / "fixture")
            manifest_path = fixture["root"] / "data/manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["schemas"]["input_sha256"] = "0" * 64
            manifest_raw = _json_bytes(manifest)
            manifest_path.write_bytes(manifest_raw)
            doc = copy.deepcopy(fixture["document"])
            doc["aggregation"]["manifest"]["sha256"] = _sha(manifest_raw)
            path = fixture["root"] / "mutated-manifest.yaml"
            path.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")
            result = _cli(fixture["root"], "aggregate-output", "--config", str(path))
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertIn("schema fingerprint", result.stderr)
            self.assertFalse((fixture["root"] / "generated/aggregate.jsonl").exists())

        with tempfile.TemporaryDirectory() as temp:
            fixture = _fixture(Path(temp) / "fixture")
            doc = copy.deepcopy(fixture["document"])
            doc["aggregation"]["contract"]["sha256"] = "0" * 64
            path = fixture["root"] / "bad-contract.yaml"
            path.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")
            result = _cli(fixture["root"], "aggregate-output", "--config", str(path))
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertIn("contract SHA-256 mismatch", result.stderr)

        with tempfile.TemporaryDirectory() as temp:
            fixture = _fixture(Path(temp) / "fixture")
            manifest_path = fixture["root"] / "data/manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["config"]["batch_size"] = 3.0
            manifest_raw = _json_bytes(manifest)
            manifest_path.write_bytes(manifest_raw)
            manifest_hash = _sha(manifest_raw)
            doc = copy.deepcopy(fixture["document"])
            doc["aggregation"]["manifest"]["sha256"] = manifest_hash
            path = fixture["root"] / "float-manifest-config.yaml"
            path.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")
            for acceptance in fixture["acceptances"]:
                receipt = json.loads(acceptance.read_text(encoding="utf-8"))
                receipt["input_manifest"]["sha256"] = manifest_hash
                acceptance.write_bytes(_json_bytes(receipt))
            result = _cli(fixture["root"], "aggregate-output", "--config", str(path))
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            error = json.loads(result.stderr)["errors"][0]
            self.assertEqual(error["file"], str(manifest_path.resolve()))
            self.assertEqual(error["path"], "/config/batch_size")
            self.assertIn("integer", error["message"])

    def test_persisted_aggregate_full_payload_and_explicit_hash_are_verified(self):
        with tempfile.TemporaryDirectory() as temp:
            fixture = _fixture(Path(temp) / "fixture")
            wrong_hash_doc = copy.deepcopy(fixture["document"])
            wrong_hash_doc["constraints"]["input_sha256"] = "0" * 64
            wrong_hash_config = fixture["root"] / "wrong-enriched-hash.yaml"
            wrong_hash_config.write_text(yaml.safe_dump(wrong_hash_doc, allow_unicode=True, sort_keys=False), encoding="utf-8")
            wrong_hash_result = _cli(fixture["root"], "aggregate-output", "--config", str(wrong_hash_config))
            self.assertEqual(wrong_hash_result.returncode, 2, wrong_hash_result.stdout + wrong_hash_result.stderr)
            self.assertIn("configured enriched input hash", wrong_hash_result.stderr)
            self.assertFalse((fixture["root"] / "generated/aggregate.jsonl").exists())
            # The output's literal order is frozen manifest order, not lexical ID order; compute independent contract serialization.
            expected_raw = b"".join((json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8") for row in fixture["expected_records"])
            doc = copy.deepcopy(fixture["document"])
            doc["constraints"]["input_sha256"] = _sha(expected_raw)
            config_path = fixture["root"] / "explicit-hash.yaml"
            config_path.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")
            result = _cli(fixture["root"], "aggregate-output", "--config", str(config_path))
            self.assertEqual(result.returncode, 0, result.stderr)
            aggregate_path = fixture["root"] / "generated/aggregate.jsonl"
            aggregate_rows = [json.loads(line) for line in aggregate_path.read_text(encoding="utf-8").splitlines()]
            aggregate_rows[0]["senses"][0]["explanation_vi"] += " altered"
            aggregate_path.write_bytes(_jsonl_bytes(aggregate_rows))
            provenance_path = fixture["root"] / "generated/provenance.json"
            provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
            provenance["aggregate"]["sha256"] = _sha(aggregate_path.read_bytes())
            provenance_path.write_bytes(_json_bytes(provenance))
            readonly_report = fixture["root"] / "generated/report.json"
            report_before = _sha(readonly_report.read_bytes())
            failed = _cli(fixture["root"], "validate-aggregate", "--config", str(config_path))
            self.assertEqual(failed.returncode, 2, failed.stdout + failed.stderr)
            self.assertIn("full payload", failed.stderr)
            self.assertEqual(_sha(readonly_report.read_bytes()), report_before)

    def test_readonly_aggregate_validator_checks_persisted_run_report(self):
        with tempfile.TemporaryDirectory() as temp:
            fixture = _fixture(Path(temp) / "fixture")
            aggregate = _cli(fixture["root"], "aggregate-output", "--config", str(fixture["config"]))
            self.assertEqual(aggregate.returncode, 0, aggregate.stderr)
            report_path = fixture["root"] / "generated/report.json"
            report = json.loads(report_path.read_text(encoding="utf-8"))
            report["checked_counts"]["output_records"] -= 1
            report_path.write_bytes(_json_bytes(report))
            before = _sha(report_path.read_bytes())
            result = _cli(fixture["root"], "validate-aggregate", "--config", str(fixture["config"]))
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertIn("aggregate report", result.stderr)
            self.assertEqual(_sha(report_path.read_bytes()), before)

    def test_public_aggregate_validate_output_build_reject_revision_in_shared_accepted_batch_replay(self):
        literal_expected = {"word-00": 2, "word-01": 1, "word-02": 1, "word-03": 1, "word-04": 1}
        for consumer in ("aggregate-output", "validate-output", "build"):
            with self.subTest(consumer=consumer), tempfile.TemporaryDirectory() as temp:
                fixture = _fixture(Path(temp) / "fixture", package=consumer == "build")
                self.assertEqual(fixture["document"]["constraints"]["revisions"], literal_expected)
                # These public paths all encounter the accepted-batch revision gate before inner consumer checks
                self.assertFalse((fixture["root"] / "generated/aggregate.jsonl").exists())
                acceptance = fixture["acceptances"][0]
                rows = copy.deepcopy(fixture["expected_records"][:3])
                rows[0]["revision"] = 9
                assigned = {"word-00": 2, "word-01": 1, "word-02": 1}
                _rebind_output(acceptance, rows, assigned)
                receipt = json.loads(acceptance.read_text(encoding="utf-8"))
                self.assertEqual(receipt["output"]["record_revisions"], assigned)
                review_path = (acceptance.parent / receipt["review"]["path"]).resolve()
                review = json.loads(review_path.read_text(encoding="utf-8"))
                self.assertEqual({item["input_id"]: item["reviewed_revision"] for item in review["records"]}, assigned)
                output_path = (acceptance.parent / receipt["output"]["path"]).resolve()
                result = _cli(fixture["root"], consumer, "--config", str(fixture["config"]))
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                failure = json.loads(result.stderr)
                error = failure["errors"][0]
                self.assertIn("expected revision 2, got 9", error["message"])
                self.assertEqual(error["record_id"], "word-00")
                self.assertEqual(error["file"], str(output_path.resolve()))
                self.assertEqual(error["path"], "/revision")
                self.assertFalse((fixture["root"] / "generated/aggregate.jsonl").exists())
                self.assertFalse((fixture["root"] / "generated/provenance.json").exists())
                self.assertFalse((fixture["root"] / "generated/report.json").exists())
                if consumer == "build":
                    for name in ("synthetic.apkg", "preview.html", "audit.json"):
                        self.assertFalse((fixture["root"] / "generated/apkg" / name).exists())

    def test_typed_builder_loader_checks_revision_on_persisted_input(self):
        from jp_deck.config import DatasetConstraints
        from jp_deck.validation import ValidationError, load_and_validate_dataset

        with tempfile.TemporaryDirectory() as temp:
            fixture = _fixture(Path(temp) / "fixture", package=True)
            persisted_path = fixture["root"] / "persisted-consumer-input.jsonl"
            expected = dict(R5_EXPECTED_REVISIONS)
            self.assertEqual(fixture["revisions"], expected)
            constraints_base = {
                "input_ids": tuple(R5_EXPECTED_REVISIONS),
                "revision": None,
                "schema_version": "0.1.0",
                "revisions": expected,
            }

            for adverse in (False, True):
                with self.subTest(adverse=adverse):
                    records = copy.deepcopy(fixture["expected_records"])
                    if adverse:
                        records[0]["revision"] = 9
                    persisted_path.write_bytes(_jsonl_bytes(records))
                    self.assertTrue(persisted_path.is_file())
                    persisted_raw = persisted_path.read_bytes()
                    actual_hash = _sha(persisted_raw)
                    self.assertEqual(json.loads(persisted_raw.splitlines()[0])["revision"], 9 if adverse else 2)
                    constraints = DatasetConstraints(input_sha256=actual_hash, **constraints_base)

                    if not adverse:
                        loaded, loaded_hash, source_records = load_and_validate_dataset(
                            persisted_path,
                            fixture["root"] / "data/master.jsonl",
                            ROOT / "schemas/output.schema.json",
                            INPUT_SCHEMA,
                            constraints,
                        )
                        self.assertEqual(loaded, records)
                        self.assertEqual(loaded_hash, actual_hash)
                        self.assertEqual([record["id"] for record in source_records], list(R5_EXPECTED_REVISIONS))
                        continue

                    with self.assertRaises(ValidationError) as raised:
                        load_and_validate_dataset(
                            persisted_path,
                            fixture["root"] / "data/master.jsonl",
                            ROOT / "schemas/output.schema.json",
                            INPUT_SCHEMA,
                            constraints,
                        )
                    error = raised.exception
                    self.assertIn("expected revision 2, got 9", str(error))
                    self.assertEqual(error.record_id, "word-00")
                    self.assertEqual(error.path, "/revision")

    def test_standalone_output_body_checks_revision_on_persisted_input(self):
        from jp_deck.output_validation import OutputStageError, validate_output

        with tempfile.TemporaryDirectory() as temp:
            fixture = _fixture(Path(temp) / "fixture", package=True)
            persisted_path = fixture["root"] / "persisted-output-body-input.jsonl"
            config = load_stage_config(fixture["config"], stage="validate-output")
            self.assertIsNotNone(config.aggregation)
            # Isolate the already-loaded validation body; this is not an ordinary non-aggregation YAML mode
            isolated = replace(config, aggregation=None)
            expected = dict(R5_EXPECTED_REVISIONS)
            self.assertEqual(fixture["revisions"], expected)

            for adverse in (False, True):
                with self.subTest(adverse=adverse):
                    records = copy.deepcopy(fixture["expected_records"])
                    if adverse:
                        records[0]["revision"] = 9
                    persisted_path.write_bytes(_jsonl_bytes(records))
                    self.assertTrue(persisted_path.is_file())
                    persisted_raw = persisted_path.read_bytes()
                    actual_hash = _sha(persisted_raw)
                    self.assertEqual(json.loads(persisted_raw.splitlines()[0])["revision"], 9 if adverse else 2)
                    stage = replace(
                        isolated,
                        paths=replace(isolated.paths, input=persisted_path),
                        constraints=replace(
                            isolated.constraints,
                            input_sha256=actual_hash,
                            revisions=expected,
                        ),
                    )

                    if not adverse:
                        result = validate_output(stage)
                        self.assertEqual(result["status"], "pass")
                        self.assertEqual(result["input_sha256"], actual_hash)
                        self.assertEqual(result["input_path"], str(persisted_path.resolve()))
                        self.assertEqual(result["record_revisions"], expected)
                        continue

                    with self.assertRaises(OutputStageError) as raised:
                        validate_output(stage)
                    error = raised.exception
                    self.assertIn("expected revision 2, got 9", str(error))
                    self.assertEqual(error.record_id, "word-00")
                    self.assertEqual(error.path, "/revision")
                    self.assertEqual(error.file, str(persisted_path.resolve()))

    def test_build_rejects_revision_map_drift_in_shared_aggregate_replay(self):
        with tempfile.TemporaryDirectory() as temp:
            fixture = _fixture(Path(temp) / "fixture", package=True)
            aggregate = _cli(fixture["root"], "aggregate-output", "--config", str(fixture["config"]))
            self.assertEqual(aggregate.returncode, 0, aggregate.stderr)
            standalone = _cli(fixture["root"], "validate-output", "--config", str(fixture["config"]))
            self.assertEqual(standalone.returncode, 0, standalone.stderr)
            self.assertEqual(json.loads(standalone.stdout)["record_revisions"], fixture["revisions"])
            doc = copy.deepcopy(fixture["document"])
            doc["constraints"]["revisions"][fixture["expected_ids"][0]] = 99
            wrong = fixture["root"] / "wrong-revision-map.yaml"
            wrong.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")
            result = _cli(fixture["root"], "build", "--config", str(wrong))
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertIn("differs from constraints.revisions", result.stderr)
            self.assertFalse((fixture["root"] / "generated/apkg").exists())

    def test_single_short_and_synthetic_25_plus_20_counts(self):
        for sizes in ((1,), (2, 1), (25, 20)):
            with self.subTest(sizes=sizes), tempfile.TemporaryDirectory() as temp:
                fixture = _fixture(Path(temp) / "fixture", group_sizes=sizes)
                result = _cli(fixture["root"], "aggregate-output", "--config", str(fixture["config"]))
                self.assertEqual(result.returncode, 0, result.stderr)
                payload = json.loads(result.stdout)
                self.assertEqual(payload["checked_counts"]["batches"], len(sizes))
                self.assertEqual(payload["checked_counts"]["output_records"], sum(sizes))
                self.assertEqual(payload["checked_counts"]["unique_ids"], sum(sizes))

    def test_partial_package_configs_protect_preview_audit_and_known_apkg_targets(self):
        cases = ("preview", "audit", "symlink-preview", "apkg")
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temp:
                fixture = _fixture(Path(temp) / "fixture", package=case == "apkg")
                doc = copy.deepcopy(fixture["document"])
                build_dir = fixture["root"] / "build-output"
                doc["paths"]["output_dir"] = "build-output"
                if case == "apkg":
                    protected_target = build_dir / "synthetic.apkg"
                    input_value = "build-output/synthetic.apkg"
                else:
                    basename = "audit.json" if case == "audit" else "preview.html"
                    protected_target = build_dir / basename
                    input_value = f"build-output/{basename}"
                protected_target.parent.mkdir(parents=True, exist_ok=True)
                sentinel = b"pre-existing build artifact: must remain byte-identical"
                protected_target.write_bytes(sentinel)
                if case == "symlink-preview":
                    alias = fixture["root"] / "build-output/aggregate-alias.jsonl"
                    alias.symlink_to(protected_target)
                    input_value = "build-output/aggregate-alias.jsonl"
                doc["paths"]["input"] = input_value
                config_path = fixture["root"] / f"r1-{case}.yaml"
                config_path.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")
                protected_before = _sha(protected_target.read_bytes())
                receipt_hashes = {path: _sha(path.read_bytes()) for path in fixture["acceptances"]}
                result = _cli(fixture["root"], "aggregate-output", "--config", str(config_path), "--force")
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                failure = json.loads(result.stderr)
                self.assertEqual((failure["stage"], failure["status"]), ("aggregate-output", "fail"))
                error = failure["errors"][0]
                self.assertEqual(error["file"], str(protected_target.resolve()))
                self.assertEqual(error["path"], "/paths/output_dir")
                self.assertIn("build", error["message"].lower())
                self.assertEqual(protected_target.read_bytes(), sentinel)
                self.assertEqual(_sha(protected_target.read_bytes()), protected_before)
                self.assertEqual({path: _sha(path.read_bytes()) for path in fixture["acceptances"]}, receipt_hashes)
                self.assertFalse((fixture["root"] / "generated/provenance.json").exists())
                self.assertFalse((fixture["root"] / "generated/report.json").exists())

    def test_declared_and_effective_partial_output_directories_are_both_protected(self):
        from jp_deck.aggregation import AggregationError, _all_named_targets
        with tempfile.TemporaryDirectory() as temp:
            fixture = _fixture(Path(temp) / "fixture")
            config = load_stage_config(fixture["config"], stage="aggregate-output")
            declared_dir, effective_dir = fixture["root"] / "declared-build", fixture["root"] / "effective-build"
            declared_target = declared_dir / "preview.html"
            effective_target = effective_dir / "audit.json"
            for target in (declared_target, effective_target):
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(b"sentinel")
            declared = replace(config.declared_paths, output_dir=declared_dir)
            effective = replace(config.paths, output_dir=effective_dir)
            for target in (declared_target, effective_target):
                altered = replace(config, paths=replace(effective, input=target), declared_paths=declared)
                with self.subTest(target=target.name), self.assertRaises(AggregationError) as caught:
                    _all_named_targets(altered)
                self.assertEqual(caught.exception.file, str(target.resolve()))
                self.assertEqual(caught.exception.path, "/paths/output_dir")
                self.assertEqual(target.read_bytes(), b"sentinel")

    def test_force_symlink_and_named_target_protection_preserve_acceptances(self):
        with tempfile.TemporaryDirectory() as temp:
            fixture = _fixture(Path(temp) / "fixture")
            acceptance = fixture["acceptances"][0]
            before = _sha(acceptance.read_bytes())
            alias = fixture["root"] / "generated/aggregate.jsonl"
            alias.parent.mkdir(parents=True)
            alias.symlink_to(acceptance)
            result = _cli(fixture["root"], "aggregate-output", "--config", str(fixture["config"]), "--force")
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertIn("protected", result.stderr)
            self.assertEqual(_sha(acceptance.read_bytes()), before)

        with tempfile.TemporaryDirectory() as temp:
            fixture = _fixture(Path(temp) / "fixture")
            acceptance = fixture["acceptances"][0]
            before = _sha(acceptance.read_bytes())
            doc = copy.deepcopy(fixture["document"])
            doc["aggregation"]["provenance"] = str(acceptance.relative_to(fixture["root"]))
            bad = fixture["root"] / "target-alias.yaml"
            bad.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")
            result = _cli(fixture["root"], "aggregate-output", "--config", str(bad), "--force")
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertIn("protected", result.stderr)
            self.assertEqual(_sha(acceptance.read_bytes()), before)

        with tempfile.TemporaryDirectory() as temp:
            fixture = _fixture(Path(temp) / "fixture")
            target = fixture["root"] / "generated/aggregate.jsonl"
            target.parent.mkdir(parents=True)
            target.write_bytes(b"keep-me\n")
            result = _cli(fixture["root"], "aggregate-output", "--config", str(fixture["config"]))
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertIn("use --force", result.stderr)
            self.assertEqual(target.read_bytes(), b"keep-me\n")

    def test_cli_requires_config_rejects_unknown_args_and_protects_build_overrides(self):
        missing = _cli(ROOT, "validate-aggregate")
        self.assertEqual(missing.returncode, 2)
        self.assertIn("--config", missing.stderr)
        unknown = _cli(ROOT, "aggregate-output", "--config", str(ROOT / "configs/synthetic-demo.yaml"), "--unknown")
        self.assertEqual(unknown.returncode, 2)
        self.assertIn("unrecognized arguments", unknown.stderr)
        with tempfile.TemporaryDirectory() as temp:
            fixture = _fixture(Path(temp) / "fixture", package=True)
            _cli(fixture["root"], "aggregate-output", "--config", str(fixture["config"]))
            override = _cli(fixture["root"], "build", "--config", str(fixture["config"]), "--input", str(fixture["root"] / "wrong.jsonl"))
            self.assertEqual(override.returncode, 2, override.stdout + override.stderr)
            self.assertIn("does not permit overriding verified input", override.stderr)

    def test_mixed_revision_package_uses_exact_guid_and_note_card_identity(self):
        with tempfile.TemporaryDirectory() as temp:
            fixture = _fixture(Path(temp) / "fixture", package=True)
            aggregate = _cli(fixture["root"], "aggregate-output", "--config", str(fixture["config"]))
            self.assertEqual(aggregate.returncode, 0, aggregate.stderr)
            result = _cli(fixture["root"], "build", "--config", str(fixture["config"]))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            package_path = Path(json.loads(result.stdout)["artifacts"]["apkg"])
            with zipfile.ZipFile(package_path) as archive:
                self.assertIsNone(archive.testzip())
                database = fixture["root"] / "collection.anki2"
                database.write_bytes(archive.read("collection.anki2"))
            connection = sqlite3.connect(database)
            try:
                notes = connection.execute("SELECT id, guid, mid, flds FROM notes").fetchall()
                cards = connection.execute("SELECT nid, did, ord FROM cards").fetchall()
            finally:
                connection.close()
            # Literal per-ID oracle: the two equal-expression notes have distinct backs.
            expected_by_guid = {
                guid_for("jp-deck/aggregation-synthetic/v1", "word-00"): ("重複語", "content-00"),
                guid_for("jp-deck/aggregation-synthetic/v1", "word-01"): ("語01", "content-01"),
                guid_for("jp-deck/aggregation-synthetic/v1", "word-02"): ("語02", "content-02"),
                guid_for("jp-deck/aggregation-synthetic/v1", "word-03"): ("重複語", "content-03"),
                guid_for("jp-deck/aggregation-synthetic/v1", "word-04"): ("語04", "content-04"),
            }
            self.assertEqual({row[1] for row in notes}, set(expected_by_guid))
            self.assertEqual(len(notes), 5)
            self.assertEqual(len(cards), 5)
            self.assertEqual({row[2] for row in notes}, {1661854648})
            self.assertEqual({row[1] for row in cards}, {1348730326})
            self.assertEqual({row[2] for row in cards}, {0})
            self.assertEqual({row[0] for row in cards}, {row[0] for row in notes})
            for _note_id, guid, _model_id, fields_text in notes:
                fields = fields_text.split("\x1f")
                expression, marker = expected_by_guid[guid]
                self.assertEqual(len(fields), 3)
                self.assertEqual(fields[0], expression)
                self.assertEqual(fields[1], f"{expression} を使う")
                self.assertIn(f"giải thích {marker}", fields[2])
                for _other_expression, other_marker in expected_by_guid.values():
                    if other_marker != marker:
                        self.assertNotIn(f"giải thích {other_marker}", fields[2])
            self.assertEqual(sum(expression == "重複語" for expression, _marker in expected_by_guid.values()), 2)

    def test_nonlexical_frozen_order_is_never_sorted_by_input_id(self):
        frozen_ids = ("word-z", "word-a", "word-y", "word-b", "word-x")
        with tempfile.TemporaryDirectory() as temp:
            fixture = _fixture(Path(temp) / "fixture", input_ids=frozen_ids)
            result = _cli(fixture["root"], "aggregate-output", "--config", str(fixture["config"]))
            self.assertEqual(result.returncode, 0, result.stderr)
            aggregate = [json.loads(line) for line in (fixture["root"] / "generated/aggregate.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual(tuple(row["input_id"] for row in aggregate), frozen_ids)
            provenance = json.loads((fixture["root"] / "generated/provenance.json").read_text(encoding="utf-8"))
            self.assertEqual(provenance["master"]["input_ids"], list(frozen_ids))
            self.assertEqual([row["input_id"] for row in provenance["rows"]], list(frozen_ids))
            self.assertEqual([row["batch_id"] for row in provenance["rows"]],
                             ["group-01", "group-01", "group-01", "group-02", "group-02"])

    def test_receipt_order_does_not_change_aggregate_or_row_provenance(self):
        with tempfile.TemporaryDirectory() as temp:
            fixture = _fixture(Path(temp) / "fixture")
            first = _cli(fixture["root"], "aggregate-output", "--config", str(fixture["config"]))
            self.assertEqual(first.returncode, 0, first.stderr)
            aggregate_path = fixture["root"] / "generated/aggregate.jsonl"
            first_bytes = aggregate_path.read_bytes()
            first_provenance = json.loads((fixture["root"] / "generated/provenance.json").read_text(encoding="utf-8"))
            document = copy.deepcopy(fixture["document"])
            document["aggregation"]["acceptances"].reverse()
            reversed_config = fixture["root"] / "reversed-receipt-order.yaml"
            reversed_config.write_text(yaml.safe_dump(document, allow_unicode=True, sort_keys=False), encoding="utf-8")
            second = _cli(fixture["root"], "aggregate-output", "--config", str(reversed_config), "--force")
            self.assertEqual(second.returncode, 0, second.stderr)
            second_provenance = json.loads((fixture["root"] / "generated/provenance.json").read_text(encoding="utf-8"))
            self.assertEqual(aggregate_path.read_bytes(), first_bytes)
            self.assertEqual(second_provenance["aggregate"]["sha256"], first_provenance["aggregate"]["sha256"])
            self.assertEqual(second_provenance["rows"], first_provenance["rows"])
            self.assertEqual([item["batch_id"] for item in second_provenance["batches"]], ["group-01", "group-02"])

    def test_confirmed_quoted_provenance_error_blocks_schema_first_acceptance(self):
        with tempfile.TemporaryDirectory() as temp:
            fixture = _fixture(Path(temp) / "fixture")
            acceptance = fixture["acceptances"][0]
            receipt = json.loads(acceptance.read_text(encoding="utf-8"))
            output_path = (acceptance.parent / receipt["output"]["path"]).resolve()
            rows = [json.loads(line) for line in output_path.read_text(encoding="utf-8").splitlines()]
            first = rows[0]
            first["sources"] = [{
                "source_id": "quoted-source", "provider": "tatoeba", "underlying_source": None,
                "url": "https://example.invalid/sentence/42", "locator": "synthetic sentence 42",
                "accessed_on": "2026-10-24", "observation": "Synthetic source row for provenance-gate testing.",
                "attribution": None, "license": None,
            }]
            first["examples"] = [{
                "example_id": "quoted-example", "sense_id": first["senses"][0]["sense_id"],
                "sentence_ja": "これは例文です。", "reading": "これはれいぶんです", "translation_vi": "Đây là câu ví dụ.",
                "origin": "quoted", "origin_source_ids": ["quoted-source"],
                "evidence_refs": [{"source_id": "quoted-source", "claim_path": "/examples/0/sentence_ja"}],
            }]
            expected_revisions = {input_id: fixture["revisions"][input_id] for input_id in fixture["expected_ids"][:3]}
            _rebind_output(acceptance, rows, expected_revisions)
            receipt = json.loads(acceptance.read_text(encoding="utf-8"))
            output_hash = receipt["output"]["sha256"]
            review_path = (acceptance.parent / receipt["review"]["path"]).resolve()
            human = {
                "schema": "jp-deck-human-disposition/v1", "batch_id": receipt["batch_id"],
                "artifact_path": receipt["output"]["path"], "artifact_sha256": output_hash,
                "review_path": receipt["review"]["path"], "review_sha256": _sha(review_path.read_bytes()),
                "record_revisions": receipt["output"]["record_revisions"],
                "findings": [{"input_id": fixture["expected_ids"][0], "path": "/examples/0/origin",
                              "status": "contradicted", "requires_correction": True,
                              "observation": "The reported quoted origin is known to be incorrect."}],
            }
            human_path = acceptance.parent / "human-disposition.json"
            human_raw = _json_bytes(human)
            human_path.write_bytes(human_raw)
            receipt["human_disposition"] = {"path": "../acceptance/human-disposition.json", "sha256": _sha(human_raw)}
            acceptance.write_bytes(_json_bytes(receipt))
            result = _cli(fixture["root"], "aggregate-output", "--config", str(fixture["config"]))
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertIn("requires correction", result.stderr)
            self.assertFalse((fixture["root"] / "generated/aggregate.jsonl").exists())

    def test_strict_scope_validates_optional_samples_and_preserves_legacy_reports(self):
        for case in ("valid-strict-sample", "legacy-no-sample", "contradicted-sample", "foreign-sample", "duplicate-sample"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temp:
                fixture = _fixture(Path(temp) / "fixture")
                document = copy.deepcopy(fixture["document"])
                document["aggregation"]["review_scope"] = "structure-and-collocation-attestation/v1"
                for acceptance in fixture["acceptances"]:
                    receipt = json.loads(acceptance.read_text(encoding="utf-8"))
                    review_path = (acceptance.parent / receipt["review"]["path"]).resolve()
                    review = json.loads(review_path.read_text(encoding="utf-8"))
                    review["scope"] = document["aggregation"]["review_scope"]
                    for entry in review["records"]:
                        for collocation in entry["collocations"]:
                            collocation["status"] = "attested"
                            collocation["source_url"] = "https://example.invalid/strict-evidence"
                            collocation["observation"] = "Synthetic attested strict-profile control."
                    for sample in review["source_sample"]:
                        sample["status"] = "attested"
                        sample["source_url"] = "https://example.invalid/strict-evidence"
                        sample["observation"] = "Synthetic attested strict-profile control."
                    if case == "legacy-no-sample":
                        review.pop("source_sample")
                    elif case == "contradicted-sample":
                        review["source_sample"][0]["status"] = "contradicted"
                        review["source_sample"][0]["observation"] = "Bound strict evidence states the claim is contradicted."
                    elif case == "foreign-sample":
                        review["source_sample"][0]["item_id"] = "missing-collocation"
                    elif case == "duplicate-sample":
                        review["source_sample"].append(copy.deepcopy(review["source_sample"][0]))
                    review_raw = _json_bytes(review)
                    review_path.write_bytes(review_raw)
                    receipt["review_scope"] = document["aggregation"]["review_scope"]
                    receipt["review"]["sha256"] = _sha(review_raw)
                    acceptance.write_bytes(_json_bytes(receipt))
                config_path = fixture["root"] / f"{case}.yaml"
                config_path.write_text(yaml.safe_dump(document, allow_unicode=True, sort_keys=False), encoding="utf-8")
                result = _cli(fixture["root"], "aggregate-output", "--config", str(config_path))
                if case in {"valid-strict-sample", "legacy-no-sample"}:
                    self.assertEqual(result.returncode, 0, result.stderr)
                else:
                    self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                    expected_message = {
                        "contradicted-sample": "contradicted",
                        "foreign-sample": "foreign collocations item",
                        "duplicate-sample": "duplicate item",
                    }[case]
                    self.assertIn(expected_message, result.stderr)
                    self.assertFalse((fixture["root"] / "generated/aggregate.jsonl").exists())

    def test_schema_first_empty_sample_is_explicit_and_not_checked_is_not_attestation(self):
        with tempfile.TemporaryDirectory() as temp:
            fixture = _fixture(Path(temp) / "fixture")
            for acceptance in fixture["acceptances"]:
                receipt = json.loads(acceptance.read_text(encoding="utf-8"))
                review_path = (acceptance.parent / receipt["review"]["path"]).resolve()
                review = json.loads(review_path.read_text(encoding="utf-8"))
                review["source_sample"] = []
                for record in review["records"]:
                    for collocation in record["collocations"]:
                        collocation["status"] = "not_checked"
                review_raw = _json_bytes(review)
                review_path.write_bytes(review_raw)
                receipt["review"]["sha256"] = _sha(review_raw)
                acceptance.write_bytes(_json_bytes(receipt))
            result = _cli(fixture["root"], "aggregate-output", "--config", str(fixture["config"]))
            self.assertEqual(result.returncode, 0, result.stderr)
            provenance = json.loads((fixture["root"] / "generated/provenance.json").read_text(encoding="utf-8"))
            self.assertEqual(provenance["review_scope"], "schema-first-sampled-source/v1")
            self.assertEqual(provenance["native_source_linkage"]["verified"], False)

    def test_yaml_revision_map_rejects_zero_noninteger_extra_missing_and_unknown_scope(self):
        with tempfile.TemporaryDirectory() as temp:
            fixture = _fixture(Path(temp) / "fixture")
            variants = (
                (lambda d: d["constraints"]["revisions"].__setitem__(fixture["expected_ids"][0], 0), "integer"),
                (lambda d: d["constraints"]["revisions"].__setitem__(fixture["expected_ids"][0], 1.5), "integer"),
                (lambda d: d["constraints"]["revisions"].__setitem__("foreign", 1), "exact"),
                (lambda d: d["aggregation"].__setitem__("review_scope", "skip_sources/v1"), "review_scope"),
            )
            for index, (mutate, diagnostic) in enumerate(variants):
                document = copy.deepcopy(fixture["document"])
                mutate(document)
                path = fixture["root"] / f"bad-config-{index}.yaml"
                path.write_text(yaml.safe_dump(document, allow_unicode=True, sort_keys=False), encoding="utf-8")
                with self.subTest(diagnostic=diagnostic), self.assertRaisesRegex(ConfigError, diagnostic):
                    load_stage_config(path, stage="aggregate-output")

    def test_candidate_rehash_with_stale_validation_report_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            fixture = _fixture(Path(temp) / "fixture")
            acceptance = fixture["acceptances"][0]
            receipt = json.loads(acceptance.read_text(encoding="utf-8"))
            output_path = (acceptance.parent / receipt["output"]["path"]).resolve()
            rows = [json.loads(line) for line in output_path.read_text(encoding="utf-8").splitlines()]
            rows[0]["senses"][0]["explanation_vi"] += " edited"
            output_raw = _jsonl_bytes(rows)
            output_path.write_bytes(output_raw)
            receipt["output"]["sha256"] = _sha(output_raw)
            acceptance.write_bytes(_json_bytes(receipt))
            result = _cli(fixture["root"], "aggregate-output", "--config", str(fixture["config"]))
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertIn("validation report artifact_sha256", result.stderr)
            self.assertFalse((fixture["root"] / "generated/aggregate.jsonl").exists())

    def test_candidate_rehash_with_stale_review_report_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            fixture = _fixture(Path(temp) / "fixture")
            acceptance = fixture["acceptances"][0]
            receipt = json.loads(acceptance.read_text(encoding="utf-8"))
            output_path = (acceptance.parent / receipt["output"]["path"]).resolve()
            rows = [json.loads(line) for line in output_path.read_text(encoding="utf-8").splitlines()]
            rows[0]["senses"][0]["explanation_vi"] += " reviewed bytes changed"
            output_raw = _jsonl_bytes(rows)
            output_path.write_bytes(output_raw)
            receipt["output"]["sha256"] = _sha(output_raw)
            validation_path = (acceptance.parent / receipt["validation"]["path"]).resolve()
            validation = json.loads(validation_path.read_text(encoding="utf-8"))
            validation["artifact_sha256"] = _sha(output_raw)
            validation_raw = _json_bytes(validation)
            validation_path.write_bytes(validation_raw)
            receipt["validation"]["sha256"] = _sha(validation_raw)
            acceptance.write_bytes(_json_bytes(receipt))
            review_path = (acceptance.parent / receipt["review"]["path"]).resolve()
            result = _cli(fixture["root"], "aggregate-output", "--config", str(fixture["config"]))
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            error = json.loads(result.stderr)["errors"][0]
            self.assertIn("review report artifact_sha256", error["message"])
            self.assertEqual(error["file"], str(review_path))
            self.assertFalse((fixture["root"] / "generated/aggregate.jsonl").exists())

    def test_staged_multi_file_publication_rolls_back_on_publish_error(self):
        from jp_deck.aggregation import aggregate_output
        with tempfile.TemporaryDirectory() as temp:
            fixture = _fixture(Path(temp) / "fixture")
            config = load_stage_config(fixture["config"], stage="aggregate-output")
            targets = [config.paths.input, config.aggregation.provenance_path, config.aggregation.report_path]
            original_bytes = {}
            for index, target in enumerate(targets):
                target.parent.mkdir(parents=True, exist_ok=True)
                data = f"sentinel-{index}".encode()
                target.write_bytes(data)
                original_bytes[target] = data
            original_replace = os.replace
            report_target = config.aggregation.report_path.resolve()
            failed_once = False

            def fail_report_publish(source, destination):
                nonlocal failed_once
                if Path(destination).resolve() == report_target and Path(source).name == "report.json" and not failed_once:
                    failed_once = True
                    raise OSError("synthetic publication fault")
                return original_replace(source, destination)

            with patch("jp_deck.aggregation.os.replace", side_effect=fail_report_publish):
                with self.assertRaisesRegex(OSError, "synthetic publication fault"):
                    aggregate_output(config, force=True)
            self.assertTrue(failed_once)
            self.assertEqual({target: target.read_bytes() for target in targets}, original_bytes)

    def test_synthetic_production_native_aggregation_relocates_through_all_consumers(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            original = base / "native-original"
            fixture = build_native_aggregation_fixture(original, package=True)
            aggregate = _source_cli("aggregate-output", "--config", str(fixture["config"]))
            self.assertEqual(aggregate.returncode, 0, aggregate.stdout + aggregate.stderr)
            provenance_path = original / "generated/provenance.json"
            report_path = original / "generated/report.json"
            provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertTrue(provenance["native_source_linkage"]["verified"])
            self.assertEqual(provenance["native_source_linkage"]["evidence"]["linked_records"], 3)
            self.assertEqual(provenance["native_source_linkage"]["evidence"]["source_path"], "../native/Tango_N1_MiMi_n1.apkg")
            self.assertEqual(report["native_source_linkage"]["evidence"]["source_path"], "../native/Tango_N1_MiMi_n1.apkg")
            bound_files = ("native/batches/manifest.json", "generated/aggregate.jsonl",
                           "generated/provenance.json", "generated/report.json")
            before = {name: _sha((original / name).read_bytes()) for name in bound_files}
            relocated = base / "native-relocated"
            shutil.copytree(original, relocated)
            shutil.rmtree(original)
            cwd = base / "unrelated-cwd"; cwd.mkdir()
            (cwd / "manifest.json").write_text("shadow cwd file", encoding="utf-8")
            for stage in ("validate-aggregate", "validate-output", "build"):
                result = _source_cli(stage, "--config", str(relocated / "aggregation.yaml"), cwd=cwd)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(json.loads(result.stdout)["status"], "pass")
            self.assertEqual({name: _sha((relocated / name).read_bytes()) for name in bound_files}, before)
            self.assertTrue((relocated / "generated/apkg/synthetic-native.apkg").is_file())

    def test_native_source_manifest_gates_reject_rebound_database_mapping_and_selection(self):
        mutations = (
            ("missing-database-member", lambda manifest: manifest["source"].pop("database_member"), "/source", "invalid shape"),
            ("wrong-database-member", lambda manifest: manifest["source"].__setitem__("database_member", "collection.anki2"), "/source/database_member", "database_member"),
            ("mapping-version", lambda manifest: manifest["mapping"].__setitem__("version", "synthetic/wrong"), "/mapping/version", "mapping version"),
            ("selection-order", lambda manifest: manifest["selection"].__setitem__("order", "different_order"), "/selection/order", "selection order"),
        )
        for label, mutate, expected_path, message in mutations:
            with self.subTest(mutation=label), tempfile.TemporaryDirectory() as temp:
                root = Path(temp) / "fixture"
                fixture = build_native_aggregation_fixture(root, package=False)
                manifest_path = fixture["manifest_path"]
                manifest = json.loads(manifest_path.read_text(encoding="utf-8")); mutate(manifest)
                manifest_raw = _json_bytes(manifest); manifest_path.write_bytes(manifest_raw)
                config_doc = yaml.safe_load(fixture["config"].read_text(encoding="utf-8"))
                manifest_hash = _sha(manifest_raw)
                config_doc["aggregation"]["manifest"]["sha256"] = manifest_hash
                for acceptance in fixture["acceptances"]:
                    receipt = json.loads(acceptance.read_text(encoding="utf-8"))
                    receipt["input_manifest"]["sha256"] = manifest_hash
                    acceptance.write_bytes(_json_bytes(receipt))
                fixture["config"].write_text(yaml.safe_dump(config_doc, allow_unicode=True, sort_keys=False), encoding="utf-8")
                result = _source_cli("aggregate-output", "--config", str(fixture["config"]))
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                error = json.loads(result.stderr)["errors"][0]
                self.assertEqual(error["file"], str(manifest_path.resolve()))
                self.assertEqual(error["path"], expected_path)
                self.assertIn(message, error["message"])
                self.assertFalse((root / "generated/aggregate.jsonl").exists())
                self.assertFalse((root / "generated/provenance.json").exists())
                self.assertFalse((root / "generated/report.json").exists())

    def test_synthetic_scalar_configs_remain_loadable(self):
        from jp_deck.config import load_config
        legacy = load_config(ROOT / "tests/fixtures/synthetic/legacy-build.yaml")
        stage = load_stage_config(ROOT / "configs/synthetic-demo.yaml", stage="validate-output")
        self.assertEqual(legacy.constraints.input_ids[0], "demo-001")
        self.assertEqual(legacy.constraints.revision, 1)
        self.assertEqual(stage.constraints.revision, 1)


if __name__ == "__main__":
    unittest.main()
