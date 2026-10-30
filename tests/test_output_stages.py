from __future__ import annotations

import copy
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

import yaml
from genanki import guid_for

from jp_deck.audit import AuditError, audit_apkg
from jp_deck.config import ConfigError, load_stage_config
from jp_deck.packaging import FIELD_NAMES, TEMPLATE_BACK, TEMPLATE_FRONT
from jp_deck.render import render_record
from jp_deck.validation import ValidationError

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/fixtures/synthetic"
OUTPUT_FIXTURE = FIXTURES / "enriched.jsonl"
INPUT_FIXTURE = FIXTURES / "source.jsonl"
EXPECTED_IDS = [f"demo-{index:03d}" for index in range(1, 6)]
BINDING = {
    "expected_ids": EXPECTED_IDS,
    "input_sha256": "aad65ee344f1a21bb65561245e931068684c62f5577ff26aaea23681f93fbecd",
    "source_input_sha256": "e84d6f7f0322fa310c61592ac5f1742e08bada2afcaafeeabe8582d2185f12d1",
    "files_sha256": {
        "tests/fixtures/synthetic/enriched.jsonl": "aad65ee344f1a21bb65561245e931068684c62f5577ff26aaea23681f93fbecd",
        "tests/fixtures/synthetic/source.jsonl": "e84d6f7f0322fa310c61592ac5f1742e08bada2afcaafeeabe8582d2185f12d1",
        "schemas/output.schema.json": "07b023a5082700dbd89ab9c7c66cc9340054d9946ab64d250337be37c2ecb0d4",
        "schemas/input.schema.json": "a4e52bacad51eca456e87adbdc69501234258fde45f6ec920238f7da6dbddbd0",
    },
}
EXPECTED_FRONTS = [
    ("試作重複語", "試作重複語を試す"),
    ("霧環", "霧環を試す"),
    ("星綴", "星綴を試す"),
    ("試作重複語", "試作重複語を試す"),
    ("波標", "波標を試す"),
]


def _jsonl_bytes(records: list[dict]) -> bytes:
    return b"".join((json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8") for row in records)


def _fixture_config_document() -> dict:
    return yaml.safe_load((ROOT / "configs/synthetic-demo.yaml").read_text(encoding="utf-8"))


def _write_config(directory: Path, *, full: bool = False, stage: str = "validate-output") -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    document = _fixture_config_document()
    document["paths"].update({
        "input": str(OUTPUT_FIXTURE.resolve()),
        "source_input": str(INPUT_FIXTURE.resolve()),
        "output_schema": str((ROOT / "schemas/output.schema.json").resolve()),
        "input_schema": str((ROOT / "schemas/input.schema.json").resolve()),
    })
    if full or stage == "build":
        document["paths"]["output_dir"] = str(directory / "artifacts")
    else:
        document.pop("package", None)
        document["paths"].pop("output_dir", None)
    path = directory / f"{stage}.yaml"
    path.write_text(yaml.safe_dump(document, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return path


def _cli(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(ROOT) + (os.pathsep + environment["PYTHONPATH"] if environment.get("PYTHONPATH") else "")
    return subprocess.run(
        [sys.executable, "-m", "jp_deck", *args],
        cwd=cwd or ROOT,
        env=environment,
        text=True,
        capture_output=True,
    )


def _records(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


class OutputStageTests(unittest.TestCase):
    def test_synthetic_fixture_and_schema_fingerprints_match_literal_binding(self):
        for relative_path, expected in BINDING["files_sha256"].items():
            with self.subTest(path=relative_path):
                self.assertEqual(hashlib.sha256((ROOT / relative_path).read_bytes()).hexdigest(), expected)

    def test_p2_01_validate_output_minimal_v2_is_read_only_and_binds_actual_hashes(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            config_path = _write_config(folder)
            cwd = folder / "unrelated-cwd"
            cwd.mkdir()
            result = _cli("validate-output", "--config", str(config_path), cwd=cwd)
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual((payload["stage"], payload["status"]), ("validate-output", "pass"))
            self.assertEqual(payload["checked_counts"]["input_records"], 5)
            self.assertEqual(payload["checked_counts"]["output_records"], 5)
            self.assertEqual(payload["input_sha256"], hashlib.sha256(OUTPUT_FIXTURE.read_bytes()).hexdigest())
            self.assertEqual(payload["source_input_sha256"], hashlib.sha256(INPUT_FIXTURE.read_bytes()).hexdigest())
            self.assertFalse((folder / "artifacts").exists())
            self.assertEqual(set(path.name for path in folder.iterdir()), {"unrelated-cwd", "validate-output.yaml"})

    def test_p2_02_v2_stage_specific_requirements_and_declared_values_are_strict(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            original = {
                "config_version": 2,
                "paths": {"input": str(OUTPUT_FIXTURE), "source_input": str(INPUT_FIXTURE),
                          "output_schema": str(ROOT / "schemas/output.schema.json"),
                          "input_schema": str(ROOT / "schemas/input.schema.json")},
                "constraints": {"input_ids": BINDING["expected_ids"], "revision": 1,
                                "schema_version": "0.1.0", "source_input_sha256": BINDING["source_input_sha256"]},
            }
            for mutation, diagnostic in (
                (lambda d: d["constraints"].pop("input_ids"), "input_ids"),
                (lambda d: d["constraints"].__setitem__("revision", True), "revision"),
                (lambda d: d["constraints"].__setitem__("source_input_sha256", "bad"), "source_input_sha256"),
                (lambda d: d["unexpected"] if False else d.__setitem__("unexpected", True), "unknown key"),
            ):
                document = copy.deepcopy(original)
                mutation(document)
                path = folder / f"invalid-{len(list(folder.glob('*.yaml')))}.yaml"
                path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
                with self.subTest(diagnostic=diagnostic), self.assertRaisesRegex(ConfigError, diagnostic):
                    load_stage_config(path, stage="validate-output")
            short_selection = copy.deepcopy(original)
            short_selection["constraints"]["input_ids"] = BINDING["expected_ids"][:4]
            short_path = folder / "short-selection.yaml"
            short_path.write_text(yaml.safe_dump(short_selection, sort_keys=False), encoding="utf-8")
            self.assertEqual(len(load_stage_config(short_path, stage="validate-output").constraints.input_ids), 4)
            expanded_selection = copy.deepcopy(original)
            expanded_selection["constraints"]["input_ids"] = BINDING["expected_ids"] + ["sixth"]
            expanded_path = folder / "expanded-selection.yaml"
            expanded_path.write_text(yaml.safe_dump(expanded_selection, sort_keys=False), encoding="utf-8")
            self.assertEqual(len(load_stage_config(expanded_path, stage="validate-output").constraints.input_ids), 6)
            incomplete = copy.deepcopy(original)
            incomplete["paths"].pop("source_input")
            path = folder / "missing-source.yaml"
            path.write_text(yaml.safe_dump(incomplete), encoding="utf-8")
            with self.assertRaisesRegex(ConfigError, "source_input"):
                load_stage_config(path, stage="validate-output")
            build_config = _write_config(folder / "build", stage="build")
            build_doc = yaml.safe_load(build_config.read_text(encoding="utf-8"))
            del build_doc["constraints"]["input_sha256"]
            build_config.write_text(yaml.safe_dump(build_doc, allow_unicode=True), encoding="utf-8")
            with self.assertRaisesRegex(ConfigError, "input_sha256"):
                load_stage_config(build_config, stage="build")
            build_doc["constraints"]["input_sha256"] = BINDING["input_sha256"]
            build_doc.pop("package")
            build_config.write_text(yaml.safe_dump(build_doc, allow_unicode=True), encoding="utf-8")
            with self.assertRaisesRegex(ConfigError, "package"):
                load_stage_config(build_config, stage="build")
            build_doc["package"] = {
                "apkg_filename": "valid.apkg", "model_name": "M", "model_id": 1848570013,
                "deck_name": "D", "deck_id": 1848570012, "guid_namespace": "test/ns",
                "stable_id_epoch_seconds": 1800000000.0,
            }
            build_doc["constraints"].pop("source_input_sha256")
            build_config.write_text(yaml.safe_dump(build_doc, allow_unicode=True), encoding="utf-8")
            with self.assertRaisesRegex(ConfigError, "source_input_sha256"):
                load_stage_config(build_config, stage="build")
            build_doc["constraints"]["source_input_sha256"] = BINDING["source_input_sha256"]
            build_doc["paths"].pop("output_dir")
            build_config.write_text(yaml.safe_dump(build_doc, allow_unicode=True), encoding="utf-8")
            with self.assertRaisesRegex(ConfigError, "output_dir"):
                load_stage_config(build_config, stage="build")

    def test_p2_03_04_schema_jsonl_count_identity_and_order_mutations_fail(self):
        from jp_deck.output_validation import validate_output
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            config_path = _write_config(folder)
            config = load_stage_config(config_path, stage="validate-output")
            good = _records(OUTPUT_FIXTURE)
            for label, rows, message in (
                ("missing", good[:-1], "exactly 5"),
                ("extra", good + [dict(good[-1], input_id="extra-id")], "exactly 5"),
                ("duplicate", good[:-1] + [copy.deepcopy(good[0])], "duplicate"),
                ("reordered", [good[1], good[0], *good[2:]], "ordered IDs"),
                ("bad-schema", [{**good[0], "unexpected": 1}, *good[1:]], "Additional properties"),
                ("bad-headword", [{**good[0], "headword": {**good[0]["headword"], "expression": "別"}}, *good[1:]], "headword/expression"),
            ):
                with self.subTest(case=label):
                    temp_input = folder / f"{label}.jsonl"
                    temp_input.write_bytes(_jsonl_bytes(rows))
                    from dataclasses import replace
                    changed = replace(
                        config,
                        paths=replace(config.paths, input=temp_input),
                        constraints=replace(config.constraints, input_sha256=hashlib.sha256(temp_input.read_bytes()).hexdigest()),
                    )
                    try:
                        validate_output(changed)
                    except (ValidationError, ValueError) as exc:
                        self.assertRegex(str(exc), message)
                    else:
                        self.fail(f"{label} mutation unexpectedly passed")
            reversed_source = folder / "reversed-source.jsonl"
            source_rows = _records(INPUT_FIXTURE)
            reversed_source.write_bytes(_jsonl_bytes(list(reversed(source_rows))))
            reordered_source = replace(
                config,
                paths=replace(config.paths, source_input=reversed_source),
                constraints=replace(config.constraints, source_input_sha256=hashlib.sha256(reversed_source.read_bytes()).hexdigest()),
            )
            self.assertEqual(validate_output(reordered_source)["status"], "pass")
            changed_set = copy.deepcopy(source_rows)
            changed_set[0]["id"] = "not-an-assigned-input"
            changed_source = folder / "changed-source-set.jsonl"
            changed_source.write_bytes(_jsonl_bytes(changed_set))
            mismatched = replace(
                config,
                paths=replace(config.paths, source_input=changed_source),
                constraints=replace(config.constraints, source_input_sha256=hashlib.sha256(changed_source.read_bytes()).hexdigest()),
            )
            with self.assertRaisesRegex(ValidationError, "ID set"):
                validate_output(mismatched)
            for schema_name in ("output_schema", "input_schema"):
                malformed_schema = folder / f"{schema_name}-invalid.json"
                malformed_schema.write_bytes(b"{invalid schema\n")
                document = yaml.safe_load(config_path.read_text(encoding="utf-8"))
                document["paths"][schema_name] = str(malformed_schema)
                broken_config = folder / f"broken-{schema_name}.yaml"
                broken_config.write_text(yaml.safe_dump(document, allow_unicode=True), encoding="utf-8")
                cli = _cli("validate-output", "--config", str(broken_config))
                self.assertEqual(cli.returncode, 2, cli.stdout + cli.stderr)
                failure = json.loads(cli.stderr)
                self.assertEqual(failure["stage"], "validate-output")
                self.assertEqual(failure["status"], "fail")
                self.assertEqual(failure["errors"][0]["file"], str(malformed_schema))
                self.assertNotIn("Traceback", cli.stderr)
            for bad_bytes, expected in ((b"\n", "blank lines"), (b"{bad\n", "invalid JSON"), (b"[]\n", "must be an object"), (b"\xff", "UTF-8")):
                temp_input = folder / "malformed.jsonl"
                temp_input.write_bytes(bad_bytes)
                from dataclasses import replace
                changed = replace(config, paths=replace(config.paths, input=temp_input))
                with self.subTest(expected=expected), self.assertRaisesRegex(ValidationError, expected):
                    validate_output(changed)

    def test_p2_05_06_existing_semantic_references_duplicate_ids_and_separator_are_enforced(self):
        from jp_deck.output_validation import validate_output
        from jp_deck.validation import resolve_json_pointer
        self.assertEqual(resolve_json_pointer({"a/b": {"~key": "literal target"}}, "/a~1b/~0key", context="test"), "literal target")
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            config = load_stage_config(_write_config(folder), stage="validate-output")
            good = _records(OUTPUT_FIXTURE)
            mutations = []
            bad = copy.deepcopy(good); bad[0]["headword"]["reading"] += "x"; mutations.append((bad, "headword/reading"))
            bad = copy.deepcopy(good); bad[0]["revision"] = 4; mutations.append((bad, "revision"))
            bad = copy.deepcopy(good); bad[0]["schema_version"] = "0.2.0"; mutations.append((bad, "schema_version"))
            bad = copy.deepcopy(good); bad[0]["sources"].append(copy.deepcopy(bad[0]["sources"][0])); mutations.append((bad, "duplicate ID"))
            bad = copy.deepcopy(good); bad[0]["senses"][0]["evidence_refs"].append({"source_id": "missing", "claim_path": "/senses/0/meaning_vi"}); mutations.append((bad, "unknown source_id"))
            bad = copy.deepcopy(good); bad[0]["senses"][0]["evidence_refs"].append({"source_id": bad[0]["sources"][0]["source_id"], "claim_path": "/does/not/exist"}); mutations.append((bad, "target does not exist"))
            bad = copy.deepcopy(good); bad[0]["uncertainties"][0]["path"] = "/missing"; mutations.append((bad, "target does not exist"))
            bad = copy.deepcopy(good); bad[0]["examples"][0]["origin_source_ids"] = ["missing"]; mutations.append((bad, "unknown source_id"))
            bad = copy.deepcopy(good); bad[0]["collocations"][0]["frequency"] = {"count": 1, "corpus": "x", "query": "x", "source_id": "missing"}; mutations.append((bad, "unknown source_id"))
            bad = copy.deepcopy(good); bad[0]["senses"][0]["meaning_vi"] += "\x1f"; mutations.append((bad, "field separator"))
            for rows, message in mutations:
                temp_input = folder / "mutation.jsonl"
                temp_input.write_bytes(_jsonl_bytes(rows))
                from dataclasses import replace
                changed = replace(
                    config,
                    paths=replace(config.paths, input=temp_input),
                    constraints=replace(config.constraints, input_sha256=hashlib.sha256(temp_input.read_bytes()).hexdigest()),
                )
                with self.subTest(message=message), self.assertRaisesRegex(ValidationError, message):
                    validate_output(changed)

    def test_p2_07_frozen_hashes_and_normalized_only_linkage_are_checked_before_build(self):
        from jp_deck.output_validation import validate_output
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            config_path = _write_config(folder, full=True, stage="validate-output")
            config = load_stage_config(config_path, stage="validate-output")
            report = validate_output(config)
            self.assertEqual(report["checked_counts"]["source_linked_records"], 0)
            doc = yaml.safe_load(config_path.read_text(encoding="utf-8"))
            doc["constraints"]["input_sha256"] = "0" * 64
            bad_hash = folder / "bad-enriched-hash.yaml"
            bad_hash.write_text(yaml.safe_dump(doc, allow_unicode=True), encoding="utf-8")
            with self.assertRaisesRegex(ValidationError, "input_sha256"):
                validate_output(load_stage_config(bad_hash, stage="validate-output"))
            doc["constraints"]["input_sha256"] = BINDING["input_sha256"]
            doc["constraints"]["source_input_sha256"] = "0" * 64
            bad_source_hash = folder / "bad-source-hash.yaml"
            bad_source_hash.write_text(yaml.safe_dump(doc, allow_unicode=True), encoding="utf-8")
            with self.assertRaisesRegex(ValidationError, "source_input_sha256"):
                validate_output(load_stage_config(bad_source_hash, stage="validate-output"))

    def test_fix1_f1_original_yaml_inputs_stay_protected_after_path_overrides(self):
        # Each original path aliases the preview destination while the override is a byte-identical copy.
        for key, flag in (
            ("input", "--input"),
            ("source_input", "--source-input"),
            ("output_schema", "--output-schema"),
            ("input_schema", "--input-schema"),
        ):
            with self.subTest(declared_path=key), tempfile.TemporaryDirectory() as directory:
                folder = Path(directory)
                config_path = _write_config(folder, full=True, stage="build")
                document = yaml.safe_load(config_path.read_text(encoding="utf-8"))
                output_dir = folder / "out"
                output_dir.mkdir()
                declared = output_dir / "preview.html"
                declared.write_bytes(Path(document["paths"][key]).read_bytes())
                override = folder / f"effective-{key}.copy"
                override.write_bytes(declared.read_bytes())
                document["paths"][key] = str(declared)
                document["paths"]["output_dir"] = str(output_dir)
                config_path.write_text(yaml.safe_dump(document, allow_unicode=True, sort_keys=False), encoding="utf-8")
                before = hashlib.sha256(declared.read_bytes()).hexdigest()
                result = _cli("build", "--config", str(config_path), flag, str(override), "--force")
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                failure = json.loads(result.stderr)
                self.assertEqual(failure["stage"], "build")
                self.assertEqual(failure["status"], "fail")
                self.assertIn("protected", failure["errors"][0]["message"])
                self.assertEqual(failure["errors"][0]["file"], str(declared))
                self.assertEqual(hashlib.sha256(declared.read_bytes()).hexdigest(), before)
                self.assertFalse((output_dir / "synthetic-vocabulary.apkg").exists())
                self.assertFalse((output_dir / "audit.json").exists())
                self.assertNotIn("Traceback", result.stderr)

    def test_fix1_f2_schema_decode_and_renderer_errors_name_effective_files(self):
        for key in ("output_schema", "input_schema"):
            with self.subTest(schema=key), tempfile.TemporaryDirectory() as directory:
                folder = Path(directory)
                config_path = _write_config(folder, full=True, stage="validate-output")
                document = yaml.safe_load(config_path.read_text(encoding="utf-8"))
                bad_schema = folder / f"invalid-{key}.json"
                bad_schema.write_bytes(b"\xff")
                document["paths"][key] = str(bad_schema)
                config_path.write_text(yaml.safe_dump(document, allow_unicode=True, sort_keys=False), encoding="utf-8")
                result = _cli("validate-output", "--config", str(config_path))
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                failure = json.loads(result.stderr)
                error = failure["errors"][0]
                self.assertEqual(failure["stage"], "validate-output")
                self.assertEqual(failure["status"], "fail")
                self.assertEqual(error["file"], str(bad_schema))
                self.assertIn("decode byte 0xff", error["message"])
                self.assertNotIn("Traceback", result.stderr)

        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            records = _records(OUTPUT_FIXTURE)
            records[0]["collocations"] = []
            records[0]["uncertainties"] = [item for item in records[0]["uncertainties"] if not item["path"].startswith("/collocations/")]
            enriched = folder / "empty-collocation.jsonl"
            enriched.write_bytes(_jsonl_bytes(records))
            config_path = _write_config(folder, full=True, stage="build")
            document = yaml.safe_load(config_path.read_text(encoding="utf-8"))
            document["paths"]["input"] = str(enriched)
            document["paths"]["output_dir"] = str(folder / "unpublished")
            document["constraints"]["input_sha256"] = hashlib.sha256(enriched.read_bytes()).hexdigest()
            config_path.write_text(yaml.safe_dump(document, allow_unicode=True, sort_keys=False), encoding="utf-8")
            result = _cli("build", "--config", str(config_path))
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            failure = json.loads(result.stderr)
            error = failure["errors"][0]
            self.assertEqual(failure["stage"], "build")
            self.assertEqual(failure["status"], "fail")
            self.assertEqual(error["file"], str(enriched))
            self.assertEqual(error["record_id"], BINDING["expected_ids"][0])
            self.assertEqual(error["path"], "/collocations/0/expression")
            self.assertFalse((folder / "unpublished").exists())
            self.assertNotIn("Traceback", result.stderr)

    def test_synthetic_source_file_errors_keep_effective_filename_across_stages(self):
        for stage in ("validate-input", "validate-output", "build"):
            with self.subTest(stage=stage), tempfile.TemporaryDirectory() as directory:
                folder = Path(directory)
                config_path = _write_config(folder, full=True, stage="build")
                document = yaml.safe_load(config_path.read_text(encoding="utf-8"))
                bad_source = folder / "effective-synthetic-source.jsonl"
                bad_source.write_bytes(b"{bad synthetic JSONL\\n")
                document["paths"]["source_input"] = str(bad_source.resolve())
                config_path.write_text(yaml.safe_dump(document, allow_unicode=True, sort_keys=False), encoding="utf-8")
                result = _cli(stage, "--config", str(config_path))
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertEqual(result.stdout, "")
                error = json.loads(result.stderr)["errors"][0]
                self.assertEqual(error["code"], "validation_error")
                self.assertEqual(error["file"], str(bad_source.resolve()))
                self.assertIn("invalid JSON", error["message"])
                self.assertNotIn("Traceback", result.stderr)
                self.assertFalse(Path(document["paths"]["output_dir"]).exists())

    def test_fix1_f1_invalid_utf8_input_schema_names_effective_file(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            config_path = _write_config(folder)
            document = yaml.safe_load(config_path.read_text(encoding="utf-8"))
            source_input = folder / "effective-input.jsonl"
            source_input.write_bytes(INPUT_FIXTURE.read_bytes())
            bad_schema = folder / "effective-input-schema.json"
            bad_schema.write_bytes(b"\xff")
            document["paths"]["source_input"] = str(source_input.resolve())
            document["paths"]["input_schema"] = str(bad_schema.resolve())
            config_path.write_text(yaml.safe_dump(document, allow_unicode=True, sort_keys=False), encoding="utf-8")

            result = _cli("validate-input", "--config", str(config_path))
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertEqual(result.stdout, "")
            failure = json.loads(result.stderr)
            error = failure["errors"][0]
            self.assertEqual((failure["stage"], failure["status"]), ("validate-input", "fail"))
            self.assertEqual(error["code"], "validation_error")
            self.assertEqual(error["file"], str(bad_schema.resolve()))
            self.assertIn(str(bad_schema.resolve()), error["message"])
            self.assertNotIn("Traceback", result.stderr)
            self.assertFalse((folder / "input-validation-report.json").exists())

    def test_synthetic_build_cli_sqlite_projection_and_repeat_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            outputs = []
            fixture_records = _records(OUTPUT_FIXTURE)
            expected_model_id = 1848570013
            expected_deck_id = 1848570012
            expected_namespace = "jp-deck/public-synthetic-demo/v1"
            expected_fields = ["Expression", "FrontCollocation", "BackContent"]
            expected_front_template = (
                '<div class="card front"><div class="front-expression">{{Expression}}</div>'
                '<div class="front-collocation">{{FrontCollocation}}</div></div>'
            )
            expected_back_template = "{{FrontSide}}<hr id=\"answer\">{{BackContent}}"
            first_native_id = 1800000000000
            for label in ("first", "second"):
                config_path = _write_config(folder / label, stage="build")
                cwd = folder / f"cwd-{label}"; cwd.mkdir()
                result = _cli("build", "--config", str(config_path), cwd=cwd)
                self.assertEqual(result.returncode, 0, result.stderr)
                payload = json.loads(result.stdout)
                self.assertEqual(payload["stage"], "build")
                self.assertEqual(payload["status"], "pass")
                apkg = Path(payload["artifacts"]["apkg"])
                self.assertTrue(apkg.is_file())
                with zipfile.ZipFile(apkg) as archive:
                    self.assertIsNone(archive.testzip())
                    self.assertEqual(set(archive.namelist()), {"collection.anki2", "media"})
                    self.assertEqual(json.loads(archive.read("media")), {})
                    db = folder / f"{label}.anki2"
                    db.write_bytes(archive.read("collection.anki2"))
                connection = sqlite3.connect(db)
                try:
                    self.assertEqual(connection.execute("PRAGMA integrity_check").fetchone()[0], "ok")
                    self.assertEqual(connection.execute("SELECT count(*) FROM notes").fetchone()[0], 5)
                    self.assertEqual(connection.execute("SELECT count(*) FROM cards").fetchone()[0], 5)
                    self.assertEqual(connection.execute("SELECT count(*) FROM revlog").fetchone()[0], 0)
                    note_rows = connection.execute("SELECT id, guid, mid, flds FROM notes ORDER BY id").fetchall()
                    card_rows = connection.execute("SELECT id, nid, did, ord FROM cards ORDER BY id").fetchall()
                    models_json, decks_json = connection.execute("SELECT models,decks FROM col").fetchone()
                    models, decks = json.loads(models_json), json.loads(decks_json)

                    # Independent literal/native-row oracle, including per-note GUID linkage.
                    expected_note_ids = [first_native_id + index * 2 for index in range(5)]
                    expected_card_rows = [
                        (first_native_id + index * 2 + 1, first_native_id + index * 2, expected_deck_id, 0)
                        for index in range(5)
                    ]
                    self.assertEqual([row[0] for row in note_rows], expected_note_ids)
                    self.assertEqual([row[0] for row in card_rows], [row[0] for row in expected_card_rows])
                    self.assertEqual(card_rows, expected_card_rows)
                    expected_front_pairs = EXPECTED_FRONTS
                    actual_front_pairs = []
                    for index, (record, note_row, card_row) in enumerate(zip(fixture_records, note_rows, card_rows, strict=True)):
                        native_note_id, actual_guid, actual_model_id, field_text = note_row
                        fields = field_text.split("\x1f")
                        self.assertEqual(len(fields), 3)
                        self.assertEqual(actual_model_id, expected_model_id)
                        self.assertEqual(fields[0], record["headword"]["expression"])
                        self.assertEqual(actual_guid, guid_for(expected_namespace, BINDING["expected_ids"][index]))
                        self.assertEqual(record["input_id"], BINDING["expected_ids"][index])
                        self.assertEqual(card_row[1:], (native_note_id, expected_deck_id, 0))
                        actual_front_pairs.append((fields[0], fields[1]))
                    self.assertEqual(actual_front_pairs, expected_front_pairs)
                    self.assertEqual(set(models), {str(expected_model_id)})
                    model = models[str(expected_model_id)]
                    self.assertEqual(model["id"], str(expected_model_id))
                    self.assertEqual(model["name"], "Synthetic Japanese-Vietnamese Test Model")
                    self.assertEqual([field["name"] for field in sorted(model["flds"], key=lambda field: field["ord"])], expected_fields)
                    templates = sorted(model["tmpls"], key=lambda template: template["ord"])
                    self.assertEqual(len(templates), 1)
                    self.assertEqual(templates[0]["qfmt"], expected_front_template)
                    self.assertEqual(templates[0]["afmt"], expected_back_template)
                    self.assertEqual(set(decks), {"1", str(expected_deck_id)})
                    self.assertEqual(decks[str(expected_deck_id)]["id"], expected_deck_id)
                    self.assertEqual(decks[str(expected_deck_id)]["name"], "Synthetic Vocabulary Demo")
                    native_identity = (tuple(note_rows), tuple(card_rows), models_json, decks_json)
                finally:
                    connection.close()
                audit = json.loads(Path(payload["artifacts"]["audit"]).read_text(encoding="utf-8"))
                self.assertEqual(audit["build"]["input_sha256"], BINDING["input_sha256"])
                self.assertEqual(audit["build"]["source_input_sha256"], BINDING["source_input_sha256"])
                self.assertEqual(audit["build"]["input_ids_in_order"], BINDING["expected_ids"])
                preview = Path(payload["artifacts"]["preview"]).read_text(encoding="utf-8")
                self.assertNotIn("issue_vi", preview)
                back_html = "\n".join(row[3].split("\x1f")[2] for row in note_rows)
                self.assertIn("chưa có số đo", back_html)
                for record in fixture_records:
                    for issue in (item["issue_vi"] for item in record["uncertainties"]):
                        self.assertNotIn(issue, back_html)
                        self.assertNotIn(issue, preview)
                    for example in record["examples"]:
                        for text in (example["sentence_ja"], example["reading"], example["translation_vi"]):
                            self.assertIn(text, back_html)
                outputs.append((native_identity, actual_front_pairs, preview))
            self.assertEqual(outputs[0], outputs[1])

    def test_p2_11_12_empty_first_collocation_passes_validation_but_fails_build(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            records = _records(OUTPUT_FIXTURE)
            records[0]["collocations"] = []
            records[0]["uncertainties"] = [item for item in records[0]["uncertainties"] if not item["path"].startswith("/collocations/")]
            mutated = folder / "empty-collocation.jsonl"
            mutated.write_bytes(_jsonl_bytes(records))
            config_path = _write_config(folder, full=True, stage="build")
            document = yaml.safe_load(config_path.read_text(encoding="utf-8"))
            document["paths"]["input"] = str(mutated)
            document["paths"]["output_dir"] = str(folder / "empty-output")
            document["constraints"]["input_sha256"] = hashlib.sha256(mutated.read_bytes()).hexdigest()
            config_path = folder / "empty.yaml"
            config_path.write_text(yaml.safe_dump(document, allow_unicode=True, sort_keys=False), encoding="utf-8")
            checked = _cli("validate-output", "--config", str(config_path))
            self.assertEqual(checked.returncode, 0, checked.stderr)
            built = _cli("build", "--config", str(config_path))
            self.assertEqual(built.returncode, 2)
            failure = json.loads(built.stderr)
            self.assertEqual(failure["stage"], "build")
            self.assertEqual(failure["status"], "fail")
            self.assertNotIn("Traceback", built.stderr)
            self.assertFalse((folder / "empty-output").exists())

    def test_p2_13_14_force_only_replaces_named_outputs_and_protects_resolved_symlink_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            config_path = _write_config(folder, stage="build")
            config_doc = yaml.safe_load(config_path.read_text(encoding="utf-8"))
            output_dir = Path(config_doc["paths"]["output_dir"])
            output_dir.mkdir()
            sentinels = {name: output_dir / name for name in ("synthetic-vocabulary.apkg", "preview.html", "audit.json", "keep.txt")}
            for name, path in sentinels.items(): path.write_text("sentinel:" + name, encoding="utf-8")
            no_force = _cli("build", "--config", str(config_path))
            self.assertEqual(no_force.returncode, 2)
            self.assertEqual(json.loads(no_force.stderr)["errors"][0]["code"], "artifact_exists")
            self.assertTrue(all(path.read_text(encoding="utf-8") == "sentinel:" + name for name, path in sentinels.items()))
            forced = _cli("build", "--config", str(config_path), "--force")
            self.assertEqual(forced.returncode, 0, forced.stderr)
            for name in ("synthetic-vocabulary.apkg", "preview.html", "audit.json"):
                self.assertNotEqual(sentinels[name].read_bytes(), ("sentinel:" + name).encode("utf-8"))
            self.assertEqual(sentinels["keep.txt"].read_text(encoding="utf-8"), "sentinel:keep.txt")

            base_doc = yaml.safe_load(config_path.read_text(encoding="utf-8"))
            protected_candidates = {
                "config": None,
                "input": Path(base_doc["paths"]["input"]),
                "source_input": Path(base_doc["paths"]["source_input"]),
                "output_schema": Path(base_doc["paths"]["output_schema"]),
                "input_schema": Path(base_doc["paths"]["input_schema"]),
            }
            for label, protected in protected_candidates.items():
                with self.subTest(protected=label):
                    collision_dir = folder / f"collision-{label}"
                    collision_dir.mkdir()
                    case_doc = copy.deepcopy(base_doc)
                    case_doc["paths"]["output_dir"] = str(collision_dir)
                    collision = folder / f"collision-{label}.yaml"
                    collision.write_text(yaml.safe_dump(case_doc, allow_unicode=True), encoding="utf-8")
                    actual_protected = collision if label == "config" else protected
                    self.assertIsNotNone(actual_protected)
                    protected_bytes = actual_protected.read_bytes()
                    target = collision_dir / case_doc["package"]["apkg_filename"]
                    target.symlink_to(actual_protected)
                    blocked = _cli("build", "--config", str(collision), "--force")
                    self.assertEqual(blocked.returncode, 2, blocked.stderr)
                    failure = json.loads(blocked.stderr)
                    self.assertEqual(failure["status"], "fail")
                    self.assertIn("protected", failure["errors"][0]["message"])
                    self.assertTrue(target.is_symlink())
                    self.assertEqual(actual_protected.read_bytes(), protected_bytes)
                    self.assertNotIn("Traceback", blocked.stderr)

    def test_p2_16_17_help_legacy_and_effective_overrides_use_effective_hashes(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            missing = _cli("validate-output", "--help", cwd=folder)
            self.assertEqual(missing.returncode, 0, missing.stderr)
            self.assertIn("--config", missing.stdout)
            build_help = _cli("build", "--help", cwd=folder)
            self.assertEqual(build_help.returncode, 0, build_help.stderr)
            self.assertIn("--force", build_help.stdout)
            bad = _cli("build", "--unknown", cwd=folder)
            self.assertEqual(bad.returncode, 2)
            self.assertIn("usage:", bad.stderr)
            input_copy = folder / "copy-output.jsonl"; input_copy.write_bytes(OUTPUT_FIXTURE.read_bytes())
            source_copy = folder / "copy-source.jsonl"; source_copy.write_bytes(INPUT_FIXTURE.read_bytes())
            output_schema_copy = folder / "copy-output-schema.json"; output_schema_copy.write_bytes((ROOT / "schemas/output.schema.json").read_bytes())
            input_schema_copy = folder / "copy-input-schema.json"; input_schema_copy.write_bytes((ROOT / "schemas/input.schema.json").read_bytes())
            config_path = _write_config(folder, stage="build")
            cwd = folder / "invocation"; cwd.mkdir()
            relative_out = "override-artifacts"
            result = _cli("build", "--config", str(config_path), "--input", str(input_copy), "--source-input", str(source_copy),
                          "--output-schema", str(output_schema_copy), "--input-schema", str(input_schema_copy),
                          "--output-dir", relative_out, cwd=cwd)
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            audit = json.loads(Path(payload["artifacts"]["audit"]).read_text(encoding="utf-8"))
            provenance = audit["build"]["configuration"]
            self.assertEqual((Path(payload["artifacts"]["audit"]).parent / provenance["effective_settings"]["paths"]["input"]).resolve(), input_copy.resolve())
            self.assertEqual((Path(payload["artifacts"]["audit"]).parent / provenance["effective_settings"]["paths"]["source_input"]).resolve(), source_copy.resolve())
            self.assertEqual((Path(payload["artifacts"]["audit"]).parent / provenance["effective_settings"]["paths"]["output_schema"]).resolve(), output_schema_copy.resolve())
            self.assertEqual((Path(payload["artifacts"]["audit"]).parent / provenance["effective_settings"]["paths"]["input_schema"]).resolve(), input_schema_copy.resolve())
            self.assertEqual((Path(payload["artifacts"]["audit"]).parent / provenance["effective_settings"]["paths"]["output_dir"]).resolve(), (cwd / relative_out).resolve())
            self.assertEqual(set(provenance["overrides"]), {"input", "source_input", "output_schema", "input_schema", "output_dir"})

            changed_source = _records(source_copy)
            changed_source[0]["meaning_vi"] += " gloss-only change"
            gloss_copy = folder / "gloss-only.jsonl"; gloss_copy.write_bytes(_jsonl_bytes(changed_source))
            negative = _cli("build", "--config", str(config_path), "--source-input", str(gloss_copy), "--output-dir", "must-not-publish", cwd=cwd)
            self.assertEqual(negative.returncode, 2)
            self.assertIn("source_input_sha256", negative.stderr)
            self.assertFalse((cwd / "must-not-publish").exists())

    def test_legacy_no_subcommand_is_retired_and_explicit_build_still_works(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            legacy = _cli("--config", str(ROOT / "configs/synthetic-demo.yaml"), "--output-dir", str(folder / "legacy"))
            self.assertEqual(legacy.returncode, 2)
            self.assertIn("usage:", legacy.stderr.lower())
            missing_config = _cli("validate-output", "--config", str(folder / "missing.yaml"))
            self.assertEqual(missing_config.returncode, 2)
            self.assertEqual(json.loads(missing_config.stderr)["stage"], "validate-output")
            self.assertNotIn("Traceback", missing_config.stderr)
            explicit = _cli("build", "--config", str(ROOT / "configs/synthetic-demo.yaml"),
                            "--output-dir", str(folder / "explicit-build"))
            self.assertEqual(explicit.returncode, 0, explicit.stderr)
            self.assertTrue((folder / "explicit-build/audit.json").is_file())

    def test_p2_15_readable_sqlite_html_projection_corruption_is_rejected_by_audit(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            config_path = _write_config(folder, full=True, stage="build")
            result = _cli("build", "--config", str(config_path))
            self.assertEqual(result.returncode, 0, result.stderr)
            artifact = Path(json.loads(result.stdout)["artifacts"]["apkg"])
            records = _records(OUTPUT_FIXTURE)
            rendered = [render_record(record) for record in records]
            document = yaml.safe_load(config_path.read_text(encoding="utf-8"))
            package = document["package"]
            kwargs = {
                "guid_namespace": package["guid_namespace"],
                "model_id": package["model_id"],
                "deck_id": package["deck_id"],
                "deck_name": package["deck_name"],
                "model_name": package["model_name"],
                "field_names": FIELD_NAMES,
                "template_front": TEMPLATE_FRONT,
                "template_back": TEMPLATE_BACK,
            }
            valid = audit_apkg(artifact, records, rendered, **kwargs)
            self.assertEqual((valid["notes"], valid["cards"], valid["revlog_rows"]), (5, 5, 0))

            with zipfile.ZipFile(artifact) as archive:
                members = {name: archive.read(name) for name in archive.namelist()}
            database = folder / "mutated.anki2"
            database.write_bytes(members["collection.anki2"])
            connection = sqlite3.connect(database)
            try:
                self.assertEqual(connection.execute("PRAGMA integrity_check").fetchone()[0], "ok")
                note_id, field_text = connection.execute("SELECT id,flds FROM notes ORDER BY id LIMIT 1").fetchone()
                values = field_text.split("\x1f")
                original_translation = records[0]["examples"][0]["translation_vi"]
                swapped_translation = records[1]["examples"][0]["translation_vi"]
                self.assertNotEqual(original_translation, swapped_translation)
                self.assertIn(original_translation, values[2])
                values[2] = values[2].replace(original_translation, swapped_translation, 1)
                connection.execute("UPDATE notes SET flds=? WHERE id=?", ("\x1f".join(values), note_id))
                connection.commit()
                self.assertEqual(connection.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            finally:
                connection.close()
            members["collection.anki2"] = database.read_bytes()
            corrupted = folder / "corrupted-readable.apkg"
            with zipfile.ZipFile(corrupted, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for name, data in members.items():
                    archive.writestr(name, data)
            with self.assertRaisesRegex(AuditError, "packaged values differ from projection"):
                audit_apkg(corrupted, records, rendered, **kwargs)


if __name__ == "__main__":
    unittest.main()
