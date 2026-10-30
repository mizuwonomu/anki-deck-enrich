from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
import zipfile
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import yaml
from genanki import guid_for

from jp_deck.audit import AuditError, audit_apkg
from jp_deck.config import ConfigError, load_config
from jp_deck.packaging import FIELD_NAMES, TEMPLATE_BACK, TEMPLATE_FRONT, build
import jp_deck.packaging as packaging_module
from jp_deck.render import render_record
from jp_deck.validation import ValidationError, read_jsonl

ROOT = Path(__file__).resolve().parents[1]
LEGACY_CONFIG = ROOT / "tests/fixtures/synthetic/legacy-build.yaml"
SOURCE_FIXTURE = ROOT / "tests/fixtures/synthetic/source.jsonl"
OUTPUT_FIXTURE = ROOT / "tests/fixtures/synthetic/enriched.jsonl"
INPUT_SCHEMA = ROOT / "schemas/input.schema.json"
OUTPUT_SCHEMA = ROOT / "schemas/output.schema.json"


def _stage_document() -> dict:
    return yaml.safe_load((ROOT / "configs/synthetic-demo.yaml").read_text(encoding="utf-8"))


def _write_yaml(directory: Path, document: dict, name: str = "custom.yaml") -> Path:
    path = directory / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(document, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return path


def _absolute_legacy_document(output_dir: Path) -> dict:
    document = yaml.safe_load(LEGACY_CONFIG.read_text(encoding="utf-8"))
    document["paths"].update({
        "input": str(OUTPUT_FIXTURE.resolve()),
        "source_input": str(SOURCE_FIXTURE.resolve()),
        "output_schema": str(OUTPUT_SCHEMA.resolve()),
        "input_schema": str(INPUT_SCHEMA.resolve()),
        "output_dir": str(output_dir.resolve()),
    })
    return document


class ConfigTests(unittest.TestCase):
    def _config_text(self) -> str:
        return LEGACY_CONFIG.read_text(encoding="utf-8")

    def _write_config(self, directory: Path, document: dict | str, name: str = "custom.yaml") -> Path:
        if isinstance(document, str):
            path = directory / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(document, encoding="utf-8")
            return path
        return _write_yaml(directory, document, name)

    def test_paths_resolve_relative_to_config_and_preserve_absolute_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            config_dir = Path(directory) / "nested"
            config_dir.mkdir()
            document = yaml.safe_load(self._config_text())
            document["paths"]["input"] = "/var/tmp/frozen.jsonl"
            config_path = self._write_config(config_dir, document)
            config = load_config(config_path)
            self.assertEqual(config.paths.input, Path("/var/tmp/frozen.jsonl"))
            self.assertEqual(config.paths.source_input, (config_dir / "source.jsonl").resolve())
            self.assertEqual(config.paths.output_schema, (config_dir / "../../../schemas/output.schema.json").resolve())

    def test_required_unknown_duplicate_and_invalid_values_are_rejected(self):
        original = yaml.safe_load(self._config_text())
        cases = []
        missing = json.loads(json.dumps(original))
        del missing["paths"]["input"]
        cases.append((missing, "paths.input"))
        unknown = json.loads(json.dumps(original)); unknown["unexpected"] = True
        cases.append((unknown, "unknown key"))
        for key, value, diagnostic in (
            ("model_id", True, "package.model_id"),
            ("deck_id", original["package"]["model_id"], "package.deck_id"),
            ("model_name", "  ", "package.model_name"),
            ("stable_id_epoch_seconds", float("nan"), "stable_id_epoch_seconds"),
            ("apkg_filename", "../unsafe.apkg", "apkg_filename"),
        ):
            invalid = json.loads(json.dumps(original)); invalid["package"][key] = value
            cases.append((invalid, diagnostic))
        invalid = json.loads(json.dumps(original)); invalid["constraints"]["revision"] = True
        cases.append((invalid, "constraints.revision"))
        invalid = json.loads(json.dumps(original)); invalid["config_version"] = 2
        cases.append((invalid, "config_version"))
        invalid = json.loads(json.dumps(original)); invalid["constraints"]["input_ids"] = ["demo-001", "demo-001"]
        cases.append((invalid, "input_ids"))
        invalid = json.loads(json.dumps(original)); invalid["constraints"]["input_ids"] = []
        cases.append((invalid, "input_ids"))
        invalid = json.loads(json.dumps(original)); invalid["package"]["stable_id_epoch_seconds"] = 0
        cases.append((invalid, "stable_id_epoch_seconds"))
        invalid = json.loads(json.dumps(original)); invalid["package"]["deck_id"] = 1
        cases.append((invalid, "deck_id"))
        invalid = json.loads(json.dumps(original)); invalid["package"]["model_name"] = None
        cases.append((invalid, "package.model_name"))
        invalid = json.loads(json.dumps(original)); invalid["constraints"]["input_sha256"] = "nope"
        cases.append((invalid, "input_sha256"))
        with tempfile.TemporaryDirectory() as directory:
            for index, (document, diagnostic) in enumerate(cases):
                with self.subTest(diagnostic=diagnostic):
                    path = self._write_config(Path(directory), document, f"invalid-{index}.yaml")
                    with self.assertRaisesRegex(ConfigError, diagnostic):
                        load_config(path)
            duplicate = Path(directory) / "duplicate.yaml"
            duplicate.write_text(self._config_text().replace(
                "config_version: 1\n", "config_version: 1\nconfig_version: 1\n", 1
            ), encoding="utf-8")
            with self.assertRaisesRegex(ConfigError, "duplicate key"):
                load_config(duplicate)

    def test_malformed_yaml_and_missing_config_have_file_diagnostics(self):
        with tempfile.TemporaryDirectory() as directory:
            malformed = Path(directory) / "broken.yaml"
            malformed.write_text("paths: [\n", encoding="utf-8")
            with self.assertRaisesRegex(ConfigError, r"broken.yaml:.*YAML"):
                load_config(malformed)
            with self.assertRaisesRegex(ConfigError, "Cannot read configuration"):
                load_config(Path(directory) / "missing.yaml")

    def test_invalid_stage_config_fails_before_output_directory_is_created(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            document = _stage_document()
            output_dir = folder / "must-not-exist"
            document["paths"]["output_dir"] = str(output_dir)
            document["unexpected"] = True
            config_path = _write_yaml(folder, document)
            result = subprocess.run(
                [sys.executable, "-m", "jp_deck", "build", "--config", str(config_path)],
                cwd=ROOT, text=True, capture_output=True,
            )
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertEqual(result.stdout, "")
            self.assertIn("unknown key", result.stderr)
            self.assertNotIn("Traceback", result.stderr)
            self.assertFalse(output_dir.exists())

    def test_root_and_stage_help_do_not_load_a_missing_config(self):
        root_help = subprocess.run([sys.executable, "-m", "jp_deck", "--help"], cwd=ROOT,
                                   text=True, capture_output=True)
        self.assertEqual(root_help.returncode, 0, root_help.stderr)
        self.assertIn("build", root_help.stdout)
        stage_help = subprocess.run([sys.executable, "-m", "jp_deck", "build", "--help"], cwd=ROOT,
                                    text=True, capture_output=True)
        self.assertEqual(stage_help.returncode, 0, stage_help.stderr)
        self.assertIn("--config", stage_help.stdout)

    def test_no_subcommand_and_missing_explicit_config_are_rejected(self):
        for arguments in ([], ["build"], ["not-a-stage"]):
            with self.subTest(arguments=arguments):
                result = subprocess.run([sys.executable, "-m", "jp_deck", *arguments], cwd=ROOT,
                                        text=True, capture_output=True)
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertIn("usage:", result.stderr.lower())
                self.assertNotIn("Traceback", result.stderr)
        missing_config = subprocess.run([sys.executable, "-m", "jp_deck", "build", "--config", "/missing/demo.yaml"],
                                        cwd=ROOT, text=True, capture_output=True)
        self.assertEqual(missing_config.returncode, 2)
        failure = json.loads(missing_config.stderr)
        self.assertEqual(failure["stage"], "build")
        self.assertIn("/missing/demo.yaml", failure["errors"][0]["message"])

    def test_cli_path_overrides_are_cwd_relative_and_bind_effective_hashes(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            cwd = folder / "invocation"
            cwd.mkdir()
            output_copy = cwd / "copy-output.jsonl"; output_copy.write_bytes(OUTPUT_FIXTURE.read_bytes())
            source_copy = cwd / "copy-source.jsonl"; source_copy.write_bytes(SOURCE_FIXTURE.read_bytes())
            output_schema_copy = cwd / "copy-output-schema.json"; output_schema_copy.write_bytes(OUTPUT_SCHEMA.read_bytes())
            input_schema_copy = cwd / "copy-input-schema.json"; input_schema_copy.write_bytes(INPUT_SCHEMA.read_bytes())
            document = _stage_document()
            document["paths"].update({
                "input": "absent/output.jsonl", "source_input": "absent/source.jsonl",
                "output_schema": "absent/output.schema.json", "input_schema": "absent/input.schema.json",
                "output_dir": "absent/build",
            })
            config_path = _write_yaml(folder, document)
            result = subprocess.run([
                sys.executable, "-m", "jp_deck", "build", "--config", str(config_path),
                "--input", output_copy.name, "--source-input", source_copy.name,
                "--output-schema", output_schema_copy.name, "--input-schema", input_schema_copy.name,
                "--output-dir", "override-artifacts",
            ], cwd=cwd, env={**os.environ, "PYTHONPATH": str(ROOT)}, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            audit_path = Path(payload["artifacts"]["audit"])
            audit = json.loads(audit_path.read_text(encoding="utf-8"))
            effective = audit["build"]["configuration"]
            self.assertEqual(audit["audit_version"], 3)
            self.assertEqual((audit_path.parent / effective["effective_settings"]["paths"]["input"]).resolve(), output_copy.resolve())
            self.assertEqual((audit_path.parent / effective["effective_settings"]["paths"]["output_dir"]).resolve(), (cwd / "override-artifacts").resolve())
            self.assertEqual(set(effective["overrides"]), {"input", "source_input", "output_schema", "input_schema", "output_dir"})

    def test_nondefault_package_settings_reach_the_written_anki_collection(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            document = _absolute_legacy_document(folder / "custom-output")
            document["package"].update({
                "model_name": "Custom vocabulary model", "model_id": 1848570014,
                "deck_name": "Custom vocabulary deck", "deck_id": 1848570015,
                "guid_namespace": "jp-deck/test/non-default-guid-namespace/v1",
            })
            config = load_config(_write_yaml(folder, document))
            result = build(config)
            audit = result["audit"]
            self.assertEqual(audit["package_audit"]["model_id"], 1848570014)
            self.assertEqual(audit["package_audit"]["deck_id"], 1848570015)
            with zipfile.ZipFile(result["artifacts"]["apkg"]) as archive:
                db_path = folder / "collection.anki2"
                db_path.write_bytes(archive.read("collection.anki2"))
            connection = sqlite3.connect(db_path)
            try:
                models_json, decks_json = connection.execute("SELECT models, decks FROM col").fetchone()
                actual_guids = {row[0] for row in connection.execute("SELECT guid FROM notes")}
            finally:
                connection.close()
            models, decks = json.loads(models_json), json.loads(decks_json)
            self.assertEqual(models["1848570014"]["name"], "Custom vocabulary model")
            self.assertEqual(decks["1848570015"]["name"], "Custom vocabulary deck")
            _, records = read_jsonl(config.paths.input, "synthetic enriched dataset")
            namespace = config.package.guid_namespace
            self.assertEqual(actual_guids, {guid_for(namespace, record["input_id"]) for record in records})
            rendered = [render_record(record) for record in records]
            with self.assertRaisesRegex(AuditError, "foreign GUID identity|unstable or incorrect GUID"):
                audit_apkg(
                    Path(result["artifacts"]["apkg"]), records, rendered,
                    guid_namespace="wrong/namespace", model_id=config.package.model_id,
                    deck_id=config.package.deck_id, deck_name=config.package.deck_name,
                    model_name=config.package.model_name, field_names=FIELD_NAMES,
                    template_front=TEMPLATE_FRONT, template_back=TEMPLATE_BACK,
                )

    def test_repeat_check_filename_builds_and_uses_two_distinct_packages(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            document = _absolute_legacy_document(folder / "repeat-filename-output")
            document["package"]["apkg_filename"] = "repeat-check.apkg"
            config = load_config(_write_yaml(folder, document))
            original_snapshot = packaging_module.snapshot_package_identity
            observed_paths = []

            def observe_snapshot(path):
                path = Path(path)
                self.assertTrue(path.is_file())
                observed_paths.append(path)
                return original_snapshot(path)

            with patch("jp_deck.packaging.snapshot_package_identity", side_effect=observe_snapshot):
                result = build(config)
            self.assertEqual(len(observed_paths), 2)
            self.assertNotEqual(observed_paths[0], observed_paths[1])
            self.assertNotEqual(observed_paths[0].parent, observed_paths[1].parent)
            apkg_path = Path(result["artifacts"]["apkg"])
            self.assertEqual(apkg_path.name, "repeat-check.apkg")
            self.assertTrue(apkg_path.is_file())
            with zipfile.ZipFile(apkg_path) as archive:
                self.assertIsNone(archive.testzip())
                self.assertIn("collection.anki2", archive.namelist())
            self.assertEqual(result["audit"]["package_audit"]["notes"], 5)
            self.assertEqual(result["audit"]["package_audit"]["cards"], 5)
            self.assertTrue(result["audit"]["repeat_build_identity_audit"]["model_deck_note_card_ids_and_guids_identical"])

    def test_huge_finite_epoch_cli_error_precedes_output_directory_creation(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            output_dir = folder / "must-not-exist"
            document = _stage_document()
            document["paths"]["output_dir"] = str(output_dir)
            document["package"]["stable_id_epoch_seconds"] = 1.0e16
            config_path = _write_yaml(folder, document)
            result = subprocess.run([sys.executable, "-m", "jp_deck", "build", "--config", str(config_path)],
                                    cwd=ROOT, text=True, capture_output=True)
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertIn(str(config_path), result.stderr)
            self.assertIn("package.stable_id_epoch_seconds", result.stderr)
            self.assertNotIn("Traceback", result.stderr)
            self.assertFalse(output_dir.exists())

    def test_epoch_safe_edge_fits_configured_note_and_card_native_ids(self):
        sqlite_max = (1 << 63) - 1
        safe_epoch = sqlite_max // 1000
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            document = _absolute_legacy_document(folder / "safe-boundary-output")
            document["package"]["stable_id_epoch_seconds"] = safe_epoch
            config = load_config(_write_yaml(folder, document))
            first_native_id = int(config.package.stable_id_epoch_seconds * 1000)
            self.assertLessEqual(first_native_id + 2 * len(config.constraints.input_ids) - 1, sqlite_max)
            result = build(config)
            with zipfile.ZipFile(result["artifacts"]["apkg"]) as archive:
                database_path = folder / "safe-boundary.anki2"
                database_path.write_bytes(archive.read("collection.anki2"))
            connection = sqlite3.connect(database_path)
            try:
                native_ids = [row[0] for row in connection.execute(
                    "SELECT id FROM notes UNION ALL SELECT id FROM cards ORDER BY id"
                )]
            finally:
                connection.close()
            self.assertEqual(native_ids, list(range(first_native_id, first_native_id + 10)))
            self.assertLessEqual(native_ids[-1], sqlite_max)

    def test_epoch_native_id_overflow_accounts_for_configured_cardinality(self):
        sqlite_max = (1 << 63) - 1
        safe_epoch = sqlite_max // 1000
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            document = _absolute_legacy_document(folder / "overflow-output")
            document["constraints"]["input_ids"] = [f"synthetic-{index:03d}" for index in range(500)]
            document["package"]["stable_id_epoch_seconds"] = safe_epoch
            with self.assertRaisesRegex(ConfigError, "500-note/500-card.*signed 64-bit"):
                load_config(_write_yaml(folder, document))

    def test_nondefault_dataset_constraint_reaches_validation_before_publication(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            output_dir = folder / "must-not-exist"
            document = _absolute_legacy_document(output_dir)
            document["constraints"]["revision"] = 2
            config = load_config(_write_yaml(folder, document))
            with self.assertRaisesRegex(ValidationError, r"expected revision 2"):
                build(config)
            self.assertFalse(output_dir.exists())


if __name__ == "__main__":
    unittest.main()
