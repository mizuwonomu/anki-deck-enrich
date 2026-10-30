from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from jp_deck.config import DatasetConstraints
from jp_deck.validation import (
    ValidationError,
    load_and_validate_dataset,
    read_jsonl,
    validate_records as _validate_records,
)

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "tests/fixtures/synthetic/enriched.jsonl"
SOURCE = ROOT / "tests/fixtures/synthetic/source.jsonl"
OUTPUT_SCHEMA_PATH = ROOT / "schemas/output.schema.json"
INPUT_SCHEMA_PATH = ROOT / "schemas/input.schema.json"
EXPECTED_INPUT_SHA256 = "aad65ee344f1a21bb65561245e931068684c62f5577ff26aaea23681f93fbecd"
EXPECTED_IDS = tuple(f"demo-{index:03d}" for index in range(1, 6))
CONSTRAINTS = DatasetConstraints(
    input_sha256=EXPECTED_INPUT_SHA256,
    input_ids=EXPECTED_IDS,
    revision=1,
    schema_version="0.1.0",
)


def validate_records(records, source_records, output_schema, input_schema):
    return _validate_records(
        records,
        source_records,
        output_schema,
        input_schema,
        output_schema_path=OUTPUT_SCHEMA_PATH,
        input_schema_path=INPUT_SCHEMA_PATH,
        expected_ids=EXPECTED_IDS,
        expected_revision=1,
        expected_schema_version="0.1.0",
    )


def fixtures():
    _, records = read_jsonl(DATA, "synthetic test dataset")
    _, source_records = read_jsonl(SOURCE, "synthetic test source")
    return records, source_records, json.loads(OUTPUT_SCHEMA_PATH.read_text()), json.loads(INPUT_SCHEMA_PATH.read_text())


class ValidationTests(unittest.TestCase):
    def test_synthetic_frozen_fingerprint_and_ordered_records(self):
        records, digest, sources = load_and_validate_dataset(
            DATA, SOURCE, OUTPUT_SCHEMA_PATH, INPUT_SCHEMA_PATH, CONSTRAINTS
        )
        self.assertEqual(digest, EXPECTED_INPUT_SHA256)
        self.assertEqual([row["input_id"] for row in records], list(EXPECTED_IDS))
        self.assertEqual(len(sources), 5)

    def test_schema_and_dataset_semantics_pass_synthetic_baseline(self):
        records, sources, output_schema, input_schema = fixtures()
        validate_records(records, sources, output_schema, input_schema)

    def test_schema_required_property_and_type_errors_are_reported(self):
        records, sources, output_schema, input_schema = fixtures()
        del records[0]["headword"]["reading"]
        with self.assertRaisesRegex(ValidationError, r"record '?demo-001'? path /headword: 'reading' is a required property"):
            validate_records(records, sources, output_schema, input_schema)
        records, sources, output_schema, input_schema = fixtures()
        records[0]["revision"] = "1"
        with self.assertRaisesRegex(ValidationError, r"record '?demo-001'? path /revision: '1' is not of type 'integer'"):
            validate_records(records, sources, output_schema, input_schema)

    def test_unknown_source_reference_fails_with_record_and_json_path(self):
        records, sources, output_schema, input_schema = fixtures()
        records[0]["headword"]["evidence_refs"][0]["source_id"] = "not-in-sources"
        with self.assertRaisesRegex(ValidationError, r"record demo-001 path /headword/evidence_refs/0/source_id"):
            validate_records(records, sources, output_schema, input_schema)

    def test_missing_json_pointer_target_fails(self):
        records, sources, output_schema, input_schema = fixtures()
        records[0]["headword"]["evidence_refs"][0]["claim_path"] = "/not/a/claim"
        with self.assertRaisesRegex(ValidationError, r"record demo-001.*claim_path.*target does not exist"):
            validate_records(records, sources, output_schema, input_schema)

    def test_unknown_sense_link_fails(self):
        records, sources, output_schema, input_schema = fixtures()
        records[1]["examples"][0]["sense_id"] = "sense-missing"
        with self.assertRaisesRegex(ValidationError, r"record demo-002 path /examples/0/sense_id"):
            validate_records(records, sources, output_schema, input_schema)

    def test_duplicate_collection_id_fails(self):
        records, sources, output_schema, input_schema = fixtures()
        records[0]["collocations"][1]["collocation_id"] = records[0]["collocations"][0]["collocation_id"]
        with self.assertRaisesRegex(ValidationError, r"record demo-001 path /collocations/1/collocation_id: duplicate ID"):
            validate_records(records, sources, output_schema, input_schema)

    def test_source_expression_linkage_is_exact(self):
        records, sources, output_schema, input_schema = fixtures()
        records[0]["headword"]["expression"] = "違う架空語"
        with self.assertRaisesRegex(ValidationError, r"record demo-001 path /headword/expression"):
            validate_records(records, sources, output_schema, input_schema)

    def test_wrong_revision_and_input_order_fail(self):
        records, sources, output_schema, input_schema = fixtures()
        changed = copy.deepcopy(records)
        changed[0]["revision"] = 2
        with self.assertRaisesRegex(ValidationError, r"record demo-001 path /revision"):
            validate_records(changed, sources, output_schema, input_schema)
        with self.assertRaisesRegex(ValidationError, r"dataset path /input_id: expected ordered IDs"):
            validate_records(list(reversed(records)), sources, output_schema, input_schema)

    def test_anki_field_separator_is_rejected_with_path(self):
        records, sources, output_schema, input_schema = fixtures()
        records[0]["senses"][0]["explanation_vi"] += "\x1fextra"
        with self.assertRaisesRegex(ValidationError, r"record demo-001 path /senses/0/explanation_vi: contains Anki's field separator"):
            validate_records(records, sources, output_schema, input_schema)

    def test_frozen_hash_mismatch_fails_without_modifying_source(self):
        with tempfile.TemporaryDirectory() as directory:
            changed = Path(directory) / "synthetic-revision.jsonl"
            raw = DATA.read_bytes()
            changed.write_bytes(raw.replace(b"\n", b" \n", 1))
            with self.assertRaisesRegex(ValidationError, "SHA-256 mismatch for frozen revision-1 input"):
                load_and_validate_dataset(
                    changed, SOURCE, OUTPUT_SCHEMA_PATH, INPUT_SCHEMA_PATH, CONSTRAINTS
                )
            self.assertEqual(DATA.read_bytes(), raw)


if __name__ == "__main__":
    unittest.main()
