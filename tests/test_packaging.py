from __future__ import annotations

import copy
import hashlib
import json
import sqlite3
import tempfile
import unittest
import zipfile

import yaml
from dataclasses import replace
from pathlib import Path

from genanki import guid_for

from jp_deck.audit import AuditError, audit_apkg, snapshot_package_identity, visible_text
from jp_deck.config import load_config, load_stage_config
from jp_deck.packaging import FIELD_NAMES, TEMPLATE_BACK, TEMPLATE_FRONT, build
from jp_deck.render import render_record
from jp_deck.output_validation import validate_output
from jp_deck.validation import read_jsonl

ROOT = Path(__file__).resolve().parents[1]
SYNTHETIC_CONFIG = load_config(ROOT / "tests/fixtures/synthetic/legacy-build.yaml")


def config_for(output_dir: Path):
    return replace(SYNTHETIC_CONFIG, paths=replace(SYNTHETIC_CONFIG.paths, output_dir=output_dir))


class PackagingTests(unittest.TestCase):
    def test_synthetic_genanki_package_audit_and_stable_rebuild(self):
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory) / "apkg"
            first = build(config_for(output_dir))
            apkg = Path(first["artifacts"]["apkg"])
            first_identity = snapshot_package_identity(apkg)
            audit = json.loads(Path(first["artifacts"]["audit"]).read_text(encoding="utf-8"))
            package_audit = audit["package_audit"]
            _, records = read_jsonl(
                ROOT / "tests/fixtures/synthetic/enriched.jsonl",
                "synthetic enriched dataset",
            )
            uncertainty_texts = [
                item["issue_vi"] for record in records for item in record["uncertainties"]
            ]
            with zipfile.ZipFile(apkg, "r") as archive:
                database_path = Path(directory) / "collection.anki2"
                database_path.write_bytes(archive.read("collection.anki2"))
            connection = sqlite3.connect(database_path)
            try:
                note_fields = [row[0] for row in connection.execute("SELECT flds FROM notes")]
            finally:
                connection.close()
            preview = Path(first["artifacts"]["preview"]).read_text(encoding="utf-8")
            actual_fields = "\x1f".join(note_fields)
            visible_fields = "\n".join(visible_text(field) for field in note_fields)
            visible_preview = visible_text(preview)
            for issue in uncertainty_texts:
                with self.subTest(uncertainty=issue[:24]):
                    self.assertFalse(issue in actual_fields, "diagnostic issue text is stored literally in notes.flds")
                    self.assertFalse(issue in visible_fields, "diagnostic issue text is visible in stored note fields")
                    self.assertFalse(issue in visible_preview, "diagnostic issue text is visible in preview.html")
            self.assertEqual(len(uncertainty_texts), 2)
            self.assertEqual(audit["diagnostic_content_disposition"]["source_uncertainty_count"], 2)
            self.assertTrue(audit["diagnostic_content_disposition"]["uncertainties_retained_in_source_jsonl"])
            self.assertEqual(
                audit["diagnostic_content_disposition"]["excluded_from_learner_fields"],
                ["uncertainties[].issue_vi"],
            )
            self.assertEqual(package_audit["notes"], 5)
            self.assertEqual(package_audit["cards"], 5)
            self.assertEqual(package_audit["populated_decks"], 1)
            self.assertEqual(package_audit["deck_metadata_entries"], 2)
            self.assertTrue(package_audit["empty_genanki_default_deck_stub"])
            self.assertEqual(package_audit["note_types"], 1)
            self.assertEqual(package_audit["templates"], 1)
            self.assertEqual(package_audit["model_id"], SYNTHETIC_CONFIG.package.model_id)
            self.assertEqual(package_audit["deck_id"], SYNTHETIC_CONFIG.package.deck_id)
            self.assertTrue(package_audit["native_note_and_card_ids_stable"])
            self.assertEqual(audit["content_counts"]["senses"], 6)
            self.assertEqual(audit["content_counts"]["examples"], 6)
            self.assertEqual(audit["content_counts"]["collocations"], 7)
            self.assertEqual(audit["content_counts"]["related_terms"], 2)
            self.assertEqual(audit["content_counts"]["confusables"], 1)
            self.assertEqual(audit["content_counts"]["sources"], 5)
            self.assertEqual(audit["content_counts"]["uncertainties"], 2)

            with self.assertRaisesRegex(FileExistsError, "Refusing to overwrite"):
                build(config_for(output_dir))
            second = build(config_for(output_dir), force=True)
            second_identity = snapshot_package_identity(Path(second["artifacts"]["apkg"]))
            self.assertEqual(first_identity, second_identity)

    def test_c11_synthetic_variable_count_duplicate_expression_package_uses_guid_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            source_base = read_jsonl(SYNTHETIC_CONFIG.paths.source_input, "synthetic base input")[1][0]
            output_base = read_jsonl(SYNTHETIC_CONFIG.paths.input, "synthetic base output")[1][0]
            source_rows = []
            output_rows = []
            for index in range(6):
                source = copy.deepcopy(source_base)
                input_id = f"synthetic-package-{index + 1:03d}"
                source["id"] = input_id
                enriched = copy.deepcopy(output_base)
                enriched["input_id"] = input_id
                source_rows.append(source)
                output_rows.append(enriched)
            source_path = folder / "synthetic-input.jsonl"
            output_path = folder / "synthetic-output.jsonl"
            source_path.write_text("".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in source_rows), encoding="utf-8")
            output_bytes = "".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in output_rows).encode("utf-8")
            output_path.write_bytes(output_bytes)
            stage_yaml = folder / "synthetic-stage.yaml"
            stage_yaml.write_text(
                yaml.safe_dump({
                    "config_version": 2,
                    "paths": {
                        "input": str(output_path), "source_input": str(source_path),
                        "output_schema": str(ROOT / "schemas/output.schema.json"),
                        "input_schema": str(ROOT / "schemas/input.schema.json"),
                    },
                    "constraints": {
                        "input_ids": [row["id"] for row in source_rows],
                        "revision": 1, "schema_version": "0.1.0",
                    },
                }, allow_unicode=True, sort_keys=False),
                encoding="utf-8",
            )
            output_validation = validate_output(load_stage_config(stage_yaml, stage="validate-output"))
            self.assertEqual(output_validation["checked_counts"]["input_records"], 6)
            self.assertEqual(output_validation["checked_counts"]["output_records"], 6)
            self.assertEqual(output_validation["checked_counts"]["unique_expressions"], 1)
            constraints = replace(
                SYNTHETIC_CONFIG.constraints,
                input_sha256=hashlib.sha256(output_bytes).hexdigest(),
                input_ids=tuple(row["id"] for row in source_rows),
            )
            config = replace(
                SYNTHETIC_CONFIG,
                paths=replace(SYNTHETIC_CONFIG.paths, source_input=source_path, input=output_path, output_dir=folder / "package"),
                constraints=constraints,
            )
            result = build(config)
            apkg = Path(result["artifacts"]["apkg"])
            self.assertEqual(result["audit"]["package_audit"]["notes"], 6)
            self.assertEqual(result["audit"]["package_audit"]["cards"], 6)
            self.assertEqual(len({row["expression"] for row in source_rows}), 1)
            expected_guids = {guid_for(config.package.guid_namespace, row["id"]) for row in source_rows}
            rendered = [render_record(row) for row in output_rows]
            with zipfile.ZipFile(apkg) as archive:
                database = folder / "synthetic-collection.anki2"
                database.write_bytes(archive.read("collection.anki2"))
            connection = sqlite3.connect(database)
            try:
                stored = connection.execute("SELECT guid, flds FROM notes").fetchall()
                cards = connection.execute("SELECT nid, did, ord FROM cards").fetchall()
            finally:
                connection.close()
            self.assertEqual({guid for guid, _ in stored}, expected_guids)
            self.assertEqual(len(cards), len(source_rows))
            by_guid = {guid_for(config.package.guid_namespace, row["input_id"]): result.anki_fields
                       for row, result in zip(output_rows, rendered, strict=True)}
            self.assertEqual({guid: fields.split("\x1f") for guid, fields in stored}, by_guid)
            self.assertEqual({card[2] for card in cards}, {0})

            corrupted = folder / "corrupted.apkg"
            connection = sqlite3.connect(database)
            try:
                connection.execute("UPDATE notes SET flds=? WHERE guid=?", ("bad\x1ffields\x1fvalue", stored[0][0]))
                connection.commit()
            finally:
                connection.close()
            with zipfile.ZipFile(apkg) as original, zipfile.ZipFile(corrupted, "w", zipfile.ZIP_DEFLATED) as target:
                for name in original.namelist():
                    target.writestr(name, database.read_bytes() if name == "collection.anki2" else original.read(name))
            with self.assertRaisesRegex(AuditError, "packaged values differ"):
                audit_apkg(
                    corrupted, output_rows, rendered,
                    guid_namespace=config.package.guid_namespace,
                    model_id=config.package.model_id,
                    deck_id=config.package.deck_id,
                    deck_name=config.package.deck_name,
                    model_name=config.package.model_name,
                    field_names=FIELD_NAMES,
                    template_front=TEMPLATE_FRONT,
                    template_back=TEMPLATE_BACK,
                )


if __name__ == "__main__":
    unittest.main()
