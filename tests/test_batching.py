"""Standalone batching regressions over fabricated, self-contained input rows."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from unittest.mock import patch
from pathlib import Path

import yaml

import jp_deck.batching as batching_module
from jp_deck.batching import _chunks, prepare_batches, validate_batches
from jp_deck.config import BatchSettings, ConfigError, load_config, load_stage_config
from jp_deck.input_validation import InputStageError
from jp_deck.output_validation import apply_stage_path_overrides
from jp_deck.validation import ValidationError, read_jsonl
from helpers.synthetic_batching import validate_master

ROOT = Path(__file__).resolve().parents[1]
INPUT_SCHEMA = ROOT / "schemas/input.schema.json"
SYNTHETIC_IDS = tuple(f"synthetic-note-{index:03d}" for index in range(1, 46))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _jsonl_bytes(rows: list[dict]) -> bytes:
    return b"".join((json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8") for row in rows)


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _master_rows(count: int = 45, *, input_ids: tuple[str, ...] | None = None,
                 duplicate_expression: bool = False) -> list[dict]:
    ids = input_ids or SYNTHETIC_IDS[:count]
    rows = [
        {"id": input_id, "expression": f"試作語{index:03d}", "reading": f"しさくご{index:03d}",
         "meaning_vi": f"nghĩa kiểm thử {index:03d}"}
        for index, input_id in enumerate(ids, start=1)
    ]
    if duplicate_expression and len(rows) > 1:
        rows[1]["expression"] = rows[0]["expression"]
    return rows


# Batching's real adapter remains strict outside each test-scoped synthetic batch case.


def _config_in(directory: Path, *, batch_size: int = 25, output_dir: Path | None = None,
               rows: list[dict] | None = None, input_ids: tuple[str, ...] | None = None):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    normalized = directory / "normalized"
    normalized.mkdir(parents=True, exist_ok=True)
    records = copy.deepcopy(rows if rows is not None else _master_rows(input_ids=input_ids))
    ids = tuple(row["id"] for row in records)
    master_path = normalized / "input.jsonl"
    master_path.write_bytes(_jsonl_bytes(records))
    source_path = directory / "synthetic-source.apkg"
    source_path.write_bytes(b"fabricated source binding; not an APKG or real deck\n")
    contract_path = directory / "synthetic-mapping-contract.md"
    contract_path.write_text("Synthetic batching test contract; no source mapping is asserted.\n", encoding="utf-8")
    source_map = normalized / "source-map.jsonl"
    source_map.write_bytes(_jsonl_bytes([
        {"project_id": input_id, "synthetic_native_id": index + 70000}
        for index, input_id in enumerate(ids)
    ]))
    raw_notes = normalized / "raw-notes.jsonl"
    raw_notes.write_bytes(_jsonl_bytes([
        {"synthetic_native_id": index + 70000, "fabricated": True}
        for index, _ in enumerate(ids)
    ]))
    (normalized / "exceptions.json").write_text("{\"exceptions\":[]}\n", encoding="utf-8")
    (normalized / "normalization-report.json").write_text("{\"synthetic\":true}\n", encoding="utf-8")
    output = (output_dir or directory / "batches").resolve()
    document = {
        "config_version": 2,
        "paths": {
            "source_input": "normalized/input.jsonl",
            "input_schema": str(INPUT_SCHEMA.resolve()),
            "output_dir": str((directory / "build").resolve()),
        },
        "source": {
            "apkg": str(source_path.resolve()), "sha256": _sha(source_path),
            "adapter": "tango-n1-mimi-n1-v1",
            "mapping_contract": str(contract_path.resolve()),
            "mapping_contract_version": "synthetic-test-contract/v1",
            "mapping_contract_sha256": _sha(contract_path),
            "deck_ids": [70001], "note_type_ids": [70002],
            "selection": {"order": "note_id_ascending", "count": len(ids)},
        },
        "normalization": {
            "source_map": "normalized/source-map.jsonl", "raw_notes": "normalized/raw-notes.jsonl",
            "exceptions": "normalized/exceptions.json", "report": "normalized/normalization-report.json",
        },
        "constraints": {"input_ids": list(ids), "source_input_sha256": _sha(master_path)},
        "batching": {"batch_size": batch_size, "output_dir": str(output)},
    }
    config_path = directory / "batch-test.yaml"
    config_path.write_text(yaml.safe_dump(document, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return load_stage_config(config_path, stage="prepare-batches")


def _manifest(folder: Path) -> dict:
    return json.loads((folder / "manifest.json").read_text(encoding="utf-8"))


def _batch_rows(folder: Path, index: int = 1) -> list[dict]:
    return [json.loads(line) for line in (folder / f"batch-{index:03d}/input.jsonl").read_text(encoding="utf-8").splitlines()]


def _cli(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    wrapper = ROOT / "tests/helpers/run_synthetic_batch_cli.py"
    return subprocess.run([sys.executable, str(wrapper), *args], cwd=cwd or ROOT,
                          env=env, text=True, capture_output=True)


class BatchingTests(unittest.TestCase):
    def setUp(self):
        production_preflight = batching_module.validate_input_dataset
        self.addCleanup(self.assertIs, batching_module.validate_input_dataset, production_preflight)
        patcher = patch.object(batching_module, "validate_input_dataset", new=validate_master)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_config_types_keys_duplicates_yaml_relative_paths_and_legacy_reader(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            config = _config_in(folder)
            self.assertEqual(config.constraints.input_ids, SYNTHETIC_IDS)
            self.assertEqual(config.batching, BatchSettings(25, (folder / "batches").resolve()))
            self.assertIsNone(config.package)
            self.assertIsNone(config.constraints.input_sha256)
            self.assertEqual(load_config(ROOT / "tests/fixtures/synthetic/legacy-build.yaml").constraints.input_ids[0], "demo-001")

            document = yaml.safe_load(config.config_path.read_text(encoding="utf-8"))
            document["paths"]["source_input"] = str(config.paths.source_input.resolve())
            document["paths"]["input_schema"] = str(INPUT_SCHEMA.resolve())
            document["source"]["apkg"] = str(config.source.apkg.resolve())
            document["source"]["mapping_contract"] = str(config.source.mapping_contract.resolve())
            document["normalization"] = {key: str(getattr(config.normalization, key).resolve())
                                         for key in ("source_map", "raw_notes", "exceptions", "report")}
            document["batching"]["output_dir"] = "relative-batches"
            nested = folder / "nested/config.yaml"
            nested.parent.mkdir(parents=True)
            nested.write_text(yaml.safe_dump(document, allow_unicode=True, sort_keys=False), encoding="utf-8")
            resolved = load_stage_config(nested, stage="validate-batches")
            self.assertEqual(resolved.batching.output_dir, (nested.parent / "relative-batches").resolve())

            for value in (True, 0, -1, 25.0, "25", None):
                invalid = copy.deepcopy(document); invalid["batching"]["batch_size"] = value
                nested.write_text(yaml.safe_dump(invalid, allow_unicode=True, sort_keys=False), encoding="utf-8")
                with self.subTest(batch_size=value), self.assertRaisesRegex(ConfigError, "batching.batch_size"):
                    load_stage_config(nested, stage="validate-batches")
            invalidations = (
                (lambda item: item["batching"].__setitem__("unknown", 1), "unknown key"),
                (lambda item: item["batching"].__setitem__("output_dir", " "), "batching.output_dir"),
                (lambda item: item["source"]["selection"].__setitem__("count", 44), "selection.count"),
                (lambda item: item["constraints"]["input_ids"].__setitem__(1, item["constraints"]["input_ids"][0]), "duplicate"),
            )
            for mutate, diagnostic in invalidations:
                invalid = copy.deepcopy(document); mutate(invalid)
                nested.write_text(yaml.safe_dump(invalid, allow_unicode=True, sort_keys=False), encoding="utf-8")
                with self.subTest(diagnostic=diagnostic), self.assertRaisesRegex(ConfigError, diagnostic):
                    load_stage_config(nested, stage="validate-batches")
            duplicate_yaml = nested.read_text(encoding="utf-8") + "batching:\n  batch_size: 2\n  output_dir: x\n"
            nested.write_text(duplicate_yaml, encoding="utf-8")
            with self.assertRaisesRegex(ConfigError, "duplicate key"):
                load_stage_config(nested, stage="validate-batches")

    def test_count_independent_partition_and_short_final_batch(self):
        self.assertEqual(_chunks(tuple(f"n-{i}" for i in range(5)), 25), [tuple(f"n-{i}" for i in range(5))])
        self.assertEqual([len(items) for items in _chunks(SYNTHETIC_IDS, 25)], [25, 20])
        self.assertEqual([len(items) for items in _chunks(tuple(f"n-{i}" for i in range(100)), 25)], [25, 25, 25, 25])
        self.assertEqual([len(items) for items in _chunks(tuple(f"n-{i}" for i in range(6)), 5)], [5, 1])
        self.assertEqual(_chunks(("n-0",), 25), [("n-0",)])

    def test_new_manifest_persists_owner_relative_bindings_and_replays_from_unrelated_cwd(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            config = _config_in(folder)
            prepared = prepare_batches(config)
            manifest_path = config.batching.output_dir / "manifest.json"
            manifest = _manifest(config.batching.output_dir)
            self.assertEqual(manifest["schema"], "jp-deck-batch-manifest/v2")
            self.assertEqual(prepared["batch_sizes"], [25, 20])
            for reference in (
                manifest["config"]["config_path"], manifest["config"]["source_input"],
                manifest["config"]["input_schema"], manifest["config"]["source_apkg"],
                manifest["config"]["mapping_contract"], manifest["config"]["output_dir"],
                manifest["config"]["source_map"], manifest["config"]["raw_notes"],
                manifest["source"]["path"], manifest["mapping"]["path"],
                manifest["master"]["path"], manifest["provenance"]["source_map"]["path"],
                manifest["provenance"]["raw_notes"]["path"], manifest["batches"][0]["path"],
            ):
                self.assertFalse(Path(reference).is_absolute(), reference)
            self.assertEqual((manifest_path.parent / manifest["master"]["path"]).resolve(), config.paths.source_input.resolve())
            cwd = folder / "unrelated"; cwd.mkdir()
            (cwd / "manifest.json").write_text("wrong owner", encoding="utf-8")
            result = _cli("validate-batches", "--config", str(config.config_path), cwd=cwd)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["checked_counts"]["master_records"], 45)

    def test_invalid_selected_master_member_fails_without_replacement_or_publication(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            rows = _master_rows(3, input_ids=SYNTHETIC_IDS[:3])
            del rows[0]["reading"]
            config = _config_in(folder, rows=rows)
            with self.assertRaisesRegex(InputStageError, "'reading' is a required property"):
                prepare_batches(config)
            self.assertFalse(config.batching.output_dir.joinpath("manifest.json").exists())
            self.assertFalse(config.batching.output_dir.joinpath("batch-001/input.jsonl").exists())

    def test_duplicate_expressions_keep_distinct_ids_and_partition_membership(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            ids = SYNTHETIC_IDS[:2]
            rows = _master_rows(2, input_ids=ids, duplicate_expression=True)
            config = _config_in(folder, batch_size=1, rows=rows)
            prepared = prepare_batches(config)
            checked = validate_batches(config)
            self.assertEqual(prepared["batch_sizes"], [1, 1])
            self.assertEqual(checked["checked_counts"]["unique_ids"], 2)
            self.assertEqual(checked["checked_counts"]["unique_expressions"], 1)
            self.assertEqual([_batch_rows(config.batching.output_dir, index)[0]["id"] for index in (1, 2)], list(ids))

    def test_45_synthetic_rows_have_exact_ordered_membership_and_full_content(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            config = _config_in(folder)
            result = validate_batches(config) if (config.batching.output_dir / "manifest.json").exists() else None
            self.assertIsNone(result)
            prepared = prepare_batches(config)
            checked = validate_batches(config)
            self.assertEqual(prepared["batch_sizes"], [25, 20])
            self.assertEqual(checked["checked_counts"], {
                "master_records": 45, "batch_records": 45, "batches": 2, "unique_ids": 45, "unique_expressions": 45,
            })
            manifest = _manifest(config.batching.output_dir)
            self.assertEqual([row["input_ids"] for row in manifest["batches"]],
                             [list(SYNTHETIC_IDS[:25]), list(SYNTHETIC_IDS[25:])])
            master = read_jsonl(config.paths.source_input, "fabricated master")[1]
            for index, expected_ids in enumerate((SYNTHETIC_IDS[:25], SYNTHETIC_IDS[25:]), start=1):
                rows = _batch_rows(config.batching.output_dir, index)
                start, stop = (index - 1) * 25, index * 25
                self.assertEqual(tuple(row["id"] for row in rows), expected_ids)
                self.assertEqual(rows, master[start:stop])

    def test_stale_hash_and_rebound_field_mutations_fail_independently_of_id(self):
        for field in ("expression", "reading", "meaning_vi"):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as temp:
                folder = Path(temp)
                config = _config_in(folder)
                prepare_batches(config)
                artifact_dir = config.batching.output_dir
                batch_path = artifact_dir / "batch-001/input.jsonl"
                rows = _batch_rows(artifact_dir)
                rows[0][field] += " altered"
                batch_path.write_bytes(_jsonl_bytes(rows))
                with self.assertRaisesRegex(InputStageError, "SHA-256 mismatch"):
                    validate_batches(config)
                manifest = _manifest(artifact_dir)
                manifest["batches"][0]["sha256"] = _sha(batch_path)
                _write_json(artifact_dir / "manifest.json", manifest)
                with self.assertRaisesRegex(InputStageError, rf"path /{field} differs from validated master"):
                    validate_batches(config)

    def test_batch_jsonl_utf8_schema_and_json_errors_are_controlled(self):
        for payload, diagnostic in ((b"{bad\n", "invalid JSON"), (b"\xff\n", "not valid UTF-8")):
            with self.subTest(payload=payload), tempfile.TemporaryDirectory() as temp:
                folder = Path(temp); config = _config_in(folder); prepare_batches(config)
                path = config.batching.output_dir / "batch-001/input.jsonl"; path.write_bytes(payload)
                manifest = _manifest(config.batching.output_dir); manifest["batches"][0]["sha256"] = _sha(path)
                _write_json(config.batching.output_dir / "manifest.json", manifest)
                with self.assertRaisesRegex(ValidationError, diagnostic):
                    validate_batches(config)
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp); config = _config_in(folder); prepare_batches(config)
            path = config.batching.output_dir / "batch-001/input.jsonl"
            rows = _batch_rows(config.batching.output_dir); rows[0]["unexpected"] = True
            path.write_bytes(_jsonl_bytes(rows))
            manifest = _manifest(config.batching.output_dir); manifest["batches"][0]["sha256"] = _sha(path)
            _write_json(config.batching.output_dir / "manifest.json", manifest)
            with self.assertRaisesRegex(InputStageError, "Additional properties"):
                validate_batches(config)

    def test_duplicate_local_membership_overlap_and_manifest_relations_fail(self):
        mutations = (
            (lambda m: m["batches"][0].__setitem__("input_ids", [SYNTHETIC_IDS[0], SYNTHETIC_IDS[0], *SYNTHETIC_IDS[2:25]]), "input_ids"),
            (lambda m: m["batches"][1].__setitem__("input_ids", [SYNTHETIC_IDS[24], *SYNTHETIC_IDS[25:]]), "input_ids"),
            (lambda m: m["batches"][1].__setitem__("batch_id", m["batches"][0]["batch_id"]), "batch_id"),
            (lambda m: m["batches"][1].__setitem__("path", m["batches"][0]["path"]), "path"),
            (lambda m: m["batches"][0].__setitem__("count", 24), "count"),
            (lambda m: m["batches"][1].__setitem__("input_ids", list(SYNTHETIC_IDS[25:-1])), "input_ids"),
            (lambda m: m["selection"].__setitem__("input_ids", list(reversed(m["selection"]["input_ids"]))), "/selection"),
        )
        for mutate, diagnostic in mutations:
            with self.subTest(diagnostic=diagnostic), tempfile.TemporaryDirectory() as temp:
                folder = Path(temp); config = _config_in(folder); prepare_batches(config)
                manifest = _manifest(config.batching.output_dir); mutate(manifest)
                _write_json(config.batching.output_dir / "manifest.json", manifest)
                with self.assertRaises(InputStageError) as caught:
                    validate_batches(config)
                self.assertIn("duplicate batch ID" if diagnostic == "batch_id" else diagnostic, str(caught.exception))

    def test_duplicate_batch_records_cross_batch_overlap_and_foreign_ids_fail(self):
        cases = (
            (1, lambda rows, master: rows.__setitem__(1, copy.deepcopy(rows[0])), "duplicate input ID"),
            (2, lambda rows, master: rows.__setitem__(0, copy.deepcopy(master[24])), "expected ordered IDs"),
            (1, lambda rows, master: rows[0].__setitem__("id", "foreign-synthetic-id"), "expected ordered IDs"),
            (1, lambda rows, master: rows.reverse(), "expected ordered IDs"),
        )
        for batch_index, mutate, diagnostic in cases:
            with self.subTest(batch=batch_index, diagnostic=diagnostic), tempfile.TemporaryDirectory() as temp:
                folder = Path(temp); config = _config_in(folder); prepare_batches(config)
                master = read_jsonl(config.paths.source_input, "synthetic master")[1]
                rows = _batch_rows(config.batching.output_dir, batch_index); mutate(rows, master)
                batch_path = config.batching.output_dir / f"batch-{batch_index:03d}/input.jsonl"
                batch_path.write_bytes(_jsonl_bytes(rows))
                manifest = _manifest(config.batching.output_dir)
                manifest["batches"][batch_index - 1]["sha256"] = _sha(batch_path)
                _write_json(config.batching.output_dir / "manifest.json", manifest)
                with self.assertRaisesRegex(ValidationError, diagnostic):
                    validate_batches(config)

    def test_manifest_config_source_mapping_schema_sidecar_and_master_bindings_fail(self):
        for binding in ("config", "source", "mapping", "schemas", "source_map", "raw_notes"):
            with self.subTest(binding=binding), tempfile.TemporaryDirectory() as temp:
                folder = Path(temp); config = _config_in(folder); prepare_batches(config)
                manifest = _manifest(config.batching.output_dir)
                if binding == "config": manifest["config"]["config_sha256"] = "0" * 64
                elif binding == "source": manifest["source"]["sha256"] = "0" * 64
                elif binding == "mapping": manifest["mapping"]["sha256"] = "0" * 64
                elif binding == "schemas": manifest["schemas"]["input_sha256"] = "0" * 64
                elif binding == "source_map": manifest["provenance"]["source_map"]["sha256"] = "0" * 64
                else: manifest["provenance"]["raw_notes"]["sha256"] = "0" * 64
                _write_json(config.batching.output_dir / "manifest.json", manifest)
                expected = {"config": "manifest /config", "source": "manifest /source", "mapping": "manifest /mapping",
                            "schemas": "manifest /schemas", "source_map": "manifest /provenance", "raw_notes": "manifest /provenance"}[binding]
                with self.assertRaisesRegex(InputStageError, expected):
                    validate_batches(config)
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp); config = _config_in(folder); prepare_batches(config)
            altered_master = folder / "altered-master.jsonl"
            altered_master.write_bytes(config.paths.source_input.read_bytes().replace(b'"id":', b'"id" :', 1))
            changed = replace(
                config,
                paths=replace(config.paths, source_input=altered_master),
                constraints=replace(config.constraints, source_input_sha256=_sha(altered_master)),
            )
            manifest = _manifest(config.batching.output_dir)
            manifest["config"]["source_input"] = str(altered_master.resolve())
            manifest["master"]["path"] = str(altered_master.resolve())
            _write_json(config.batching.output_dir / "manifest.json", manifest)
            with self.assertRaisesRegex(InputStageError, "manifest /config"):
                validate_batches(changed)

    def test_collision_force_symlink_and_failed_validation_preserve_sentinels(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp); output = folder / "existing"; output.mkdir()
            config = _config_in(folder, output_dir=output)
            sentinel = output / "manifest.json"; sentinel.write_text("protected", encoding="utf-8")
            with self.assertRaises(FileExistsError): prepare_batches(config)
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "protected")
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp); output = folder / "linked"; alias = output / "batch-001/input.jsonl"
            alias.parent.mkdir(parents=True); config = _config_in(folder, output_dir=output)
            alias.symlink_to(config.paths.source_input)
            before = config.paths.source_input.read_bytes()
            with self.assertRaisesRegex(InputStageError, "aliases a protected configured path"):
                prepare_batches(config, force=True)
            self.assertEqual(config.paths.source_input.read_bytes(), before)
            self.assertTrue(alias.is_symlink())
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp); output = folder / "sentinels"; config = _config_in(folder, output_dir=output)
            output.mkdir(); manifest = output / "manifest.json"; audit = output / "audit.json"
            manifest.write_text("manifest sentinel", encoding="utf-8"); audit.write_text("audit sentinel", encoding="utf-8")
            broken_master = folder / "broken-master.jsonl"; broken_master.write_bytes(b"{bad\n")
            broken = replace(config, paths=replace(config.paths, source_input=broken_master))
            with self.assertRaises(ValidationError): prepare_batches(broken, force=True)
            self.assertEqual(manifest.read_text(encoding="utf-8"), "manifest sentinel")
            self.assertEqual(audit.read_text(encoding="utf-8"), "audit sentinel")
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp); output = folder / "repeat"; config = _config_in(folder, output_dir=output)
            prepare_batches(config); first = {p.relative_to(output).as_posix(): _sha(p) for p in output.rglob("*") if p.is_file()}
            keep = output / "keep.txt"; keep.write_text("unrelated", encoding="utf-8")
            prepare_batches(config, force=True)
            second = {p.relative_to(output).as_posix(): _sha(p) for p in output.rglob("*") if p.is_file() and p != keep}
            self.assertEqual(first, second); self.assertEqual(keep.read_text(encoding="utf-8"), "unrelated")

    def test_stage_cli_honors_explicit_custom_config_and_rejects_bad_args(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp); config = _config_in(folder, output_dir=folder / "custom-batches")
            unrelated = folder / "unrelated"; unrelated.mkdir()
            prepared = _cli("prepare-batches", "--config", str(config.config_path), cwd=unrelated)
            self.assertEqual(prepared.returncode, 0, prepared.stderr)
            self.assertEqual(json.loads(prepared.stdout)["batch_sizes"], [25, 20])
            validated = _cli("validate-batches", "--config", str(config.config_path), cwd=unrelated)
            self.assertEqual(validated.returncode, 0, validated.stderr)
            self.assertEqual(json.loads(validated.stdout)["checked_counts"]["master_records"], 45)
            missing = _cli("validate-batches", "--config", str(folder / "missing.yaml"), cwd=unrelated)
            self.assertEqual(missing.returncode, 2); self.assertEqual(json.loads(missing.stderr)["status"], "fail")
            unknown = _cli("validate-batches", "--config", str(config.config_path), "--unknown-option", cwd=unrelated)
            self.assertEqual(unknown.returncode, 2); self.assertIn("unrecognized arguments", unknown.stderr)
            bad_stage = _cli("validate-batch", "--config", str(config.config_path), cwd=unrelated)
            self.assertEqual(bad_stage.returncode, 2); self.assertIn("invalid choice", bad_stage.stderr)

    def test_build_deliverables_are_protected_from_batch_output_symlinks(self):
        package = load_config(ROOT / "tests/fixtures/synthetic/legacy-build.yaml").package
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp); batches = folder / "batches"; build = folder / "build"; build.mkdir()
            config = _config_in(folder, output_dir=batches)
            config = replace(config, package=package, paths=replace(config.paths, output_dir=build),
                             declared_paths=replace(config.declared_paths, output_dir=build))
            sentinel = build / "audit.json"; sentinel.write_text("preserve", encoding="utf-8")
            alias = batches / "batch-001/input.jsonl"; alias.parent.mkdir(parents=True); alias.symlink_to(sentinel)
            with self.assertRaisesRegex(InputStageError, "aliases a protected configured path"):
                prepare_batches(config, force=True)
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "preserve")
            self.assertTrue(alias.is_symlink()); self.assertFalse((batches / "manifest.json").exists())

    def test_input_only_configs_protect_preview_audit_and_effective_output_aliases(self):
        for target in ("preview.html", "audit.json"):
            with self.subTest(target=target), tempfile.TemporaryDirectory() as temp:
                folder = Path(temp); batches = folder / "batches"; build = folder / "build"; build.mkdir()
                config = _config_in(folder, output_dir=batches)
                declared = replace(config, paths=replace(config.paths, output_dir=build),
                                   declared_paths=replace(config.declared_paths, output_dir=build))
                sentinel = build / target; sentinel.write_text("protected partial build", encoding="utf-8")
                alias = batches / "batch-001/input.jsonl"; alias.parent.mkdir(parents=True); alias.symlink_to(sentinel)
                before = sentinel.read_bytes()
                with self.assertRaisesRegex(InputStageError, "aliases a protected configured path"):
                    prepare_batches(declared, force=True)
                self.assertEqual(sentinel.read_bytes(), before); self.assertTrue(alias.is_symlink())
                self.assertFalse((batches / "manifest.json").exists())
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp); batches = folder / "batches"; declared_dir = folder / "declared"; effective_dir = folder / "effective"
            config = _config_in(folder, output_dir=batches)
            changed = replace(config, paths=replace(config.paths, output_dir=declared_dir),
                              declared_paths=replace(config.declared_paths, output_dir=declared_dir))
            changed = apply_stage_path_overrides(changed, {"output_dir": effective_dir})
            for owner in (declared_dir, effective_dir):
                owner.mkdir(); sentinel = owner / "audit.json"; sentinel.write_text(owner.name, encoding="utf-8")
                alias = batches / "batch-001/input.jsonl"
                alias.parent.mkdir(parents=True, exist_ok=True)
                if alias.exists() or alias.is_symlink(): alias.unlink()
                alias.symlink_to(sentinel)
                with self.assertRaisesRegex(InputStageError, "aliases a protected configured path"):
                    prepare_batches(changed, force=True)
                self.assertEqual(sentinel.read_text(encoding="utf-8"), owner.name)
                alias.unlink()

    def test_cli_schema_and_membership_errors_keep_effective_file_record_path(self):
        for case in ("schema", "duplicate", "missing", "foreign", "order"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temp:
                folder = Path(temp); config = _config_in(folder); prepare_batches(config)
                output_dir = config.batching.output_dir; batch_file = output_dir / "batch-001/input.jsonl"
                audit_before = (output_dir / "audit.json").read_bytes()
                rows = copy.deepcopy(_batch_rows(output_dir))
                if case == "schema": rows[0]["unexpected"] = True
                elif case == "duplicate": rows[1] = copy.deepcopy(rows[0])
                elif case == "missing": rows.pop()
                elif case == "foreign": rows[0]["id"] = "foreign-synthetic-id"
                else: rows[0], rows[1] = rows[1], rows[0]
                batch_file.write_bytes(_jsonl_bytes(rows))
                manifest = _manifest(output_dir); manifest["batches"][0]["sha256"] = _sha(batch_file)
                _write_json(output_dir / "manifest.json", manifest)
                unrelated = folder / "unrelated"; unrelated.mkdir()
                result = _cli("validate-batches", "--config", str(config.config_path), cwd=unrelated)
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                error = json.loads(result.stderr)["errors"][0]
                self.assertEqual(error["code"], "validation_error")
                self.assertEqual(error["file"], str(batch_file))
                self.assertEqual(error["path"], "/" if case == "schema" else "/id")
                self.assertIn("batch batch-001 line", error["message"])
                self.assertEqual((output_dir / "audit.json").read_bytes(), audit_before)
                self.assertNotIn("Traceback", result.stderr)

    def test_readonly_validation_does_not_rewrite_audit_or_master(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp); config = _config_in(folder); prepare_batches(config)
            audit_path = config.batching.output_dir / "audit.json"
            audit_path.write_text("sentinel", encoding="utf-8")
            batch_path = config.batching.output_dir / "batch-001/input.jsonl"
            batch_path.write_text("invalid\n", encoding="utf-8")
            master_before = _sha(config.paths.source_input); audit_before = audit_path.read_bytes()
            with self.assertRaises(ValidationError): validate_batches(config)
            self.assertEqual(audit_path.read_bytes(), audit_before)
            self.assertEqual(_sha(config.paths.source_input), master_before)


if __name__ == "__main__":
    unittest.main()
