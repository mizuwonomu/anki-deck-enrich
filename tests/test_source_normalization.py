from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from contextlib import ExitStack, contextmanager
from pathlib import Path
from unittest.mock import patch

import yaml

from jp_deck.batching import prepare_batches, validate_batches
from jp_deck.config import ConfigError, load_stage_config
from jp_deck.input_validation import InputStageError, validate_input_dataset
from jp_deck.normalization import normalize_source
from jp_deck.source_apkg import DATABASE_MEMBER, SourceError, file_sha256, read_source_snapshot
import jp_deck.source_apkg as source_apkg_module
from jp_deck.sources import get_source_adapter
import jp_deck.sources.tango_n1_mimi.adapter as tango_adapter
from jp_deck.sources.tango_n1_mimi.adapter import FIELD_SIGNATURE, MappingFailure, project_note
from jp_deck.validation import ValidationError, read_jsonl
from helpers.synthetic_source import SYNTHETIC_DECK_ID, SYNTHETIC_NOTE_TYPE_ID, write_synthetic_apkg

ROOT = Path(__file__).resolve().parents[1]
INPUT_SCHEMA = ROOT / "schemas/input.schema.json"
OUTPUT_SCHEMA = ROOT / "schemas/output.schema.json"


def _note(native_id: int, *, expression: str = "架空語甲", reading: str = "かくうごこう",
          meaning: str = "nghĩa giả lập alpha", cards: list[dict] | None = None) -> dict:
    values = {field: "" for field in FIELD_SIGNATURE}
    values.update({
        "stt": str(native_id), "kanji": expression, "furigana": reading,
        "hanviet": "GIA KHONG", "nghia": meaning,
        "vidu": "架空語甲を試す。", "nghiavidu": "Thử từ giả lập.",
    })
    return {"id": native_id, **values, **({"cards": cards} if cards is not None else {})}


DEFAULT_NOTES = [
    _note(910001, cards=[{"type": 0, "queue": 0}, {"type": 0, "queue": 0}]),
    _note(910002, expression="霧環", reading="きりわ", meaning="vòng sương giả lập",
          cards=[{"type": 2, "queue": 2}]),
    _note(910003, expression="星綴", reading="ほしつづり", meaning="dệt sao giả lập"),
]


def _compact_jsonl(rows: list[dict]) -> bytes:
    return b"".join((json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8") for row in rows)


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _projected_rows(notes: list[dict], selection_count: int | None = None) -> list[dict]:
    selected = sorted(notes, key=lambda note: int(note["id"]))[:selection_count]
    projected = []
    for note in selected:
        native = {"id": note["id"], "mid": tango_adapter.SUPPORTED_NOTE_TYPE_ID,
                  "flds": "\x1f".join(str(note.get(field, "")) for field in FIELD_SIGNATURE)}
        projected.append(project_note(native, FIELD_SIGNATURE).values)
    return projected


def _output_rows(inputs: list[dict]) -> list[dict]:
    rows = []
    for index, source in enumerate(inputs, start=1):
        sense_id = f"synthetic-sense-{index:03d}"
        rows.append({
            "schema_version": "0.1.0", "input_id": source["id"], "revision": 1,
            "headword": {"expression": source["expression"], "reading": source["reading"],
                         "pos": ["danh từ giả lập"], "evidence_refs": []},
            "senses": [{"sense_id": sense_id, "meaning_vi": f"Nghĩa giả lập {index}.",
                        "explanation_vi": f"Giải thích kiểm thử {index}.", "evidence_refs": []}],
            "examples": [],
            "collocations": [{"collocation_id": f"synthetic-collocation-{index:03d}", "sense_id": sense_id,
                               "expression": source["expression"] + "を試す", "reading": source["reading"] + "をためす",
                               "meaning_vi": "cụm kiểm thử", "usage_vi": "ngữ cảnh giả lập",
                               "frequency": None, "evidence_refs": []}],
            "related_terms": [], "confusables": [], "sources": [], "uncertainties": [],
        })
    return rows


def _write_config(directory: Path, *, notes: list[dict] | None = None, selection_count: int | None = None,
                  signature: tuple[str, ...] = FIELD_SIGNATURE, full_output: bool = False,
                  source_input_sha256: str | None = None) -> Path:
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    source_notes = copy.deepcopy(notes if notes is not None else DEFAULT_NOTES)
    source_notes.sort(key=lambda note: int(note["id"]))
    count = len(source_notes) if selection_count is None else selection_count
    selected = source_notes[:count]
    project_ids = [f"{tango_adapter.PROJECT_ID_PREFIX}{int(note['id'])}" for note in selected]
    source_path = directory / "Tango_N1_MiMi_n1.apkg"
    write_synthetic_apkg(source_path, source_notes, signature=signature)
    contract = directory / "mapping-contract.md"
    contract.write_text("Fabricated source contract for production-adapter regression only.\n", encoding="utf-8")
    output_dir = directory / "output"
    document = {
        "config_version": 2,
        "paths": {
            "input": "output/enriched.jsonl", "source_input": "output/input.jsonl",
            "output_schema": str(OUTPUT_SCHEMA.resolve()), "input_schema": str(INPUT_SCHEMA.resolve()),
            "output_dir": "output/build",
        },
        "source": {
            "apkg": source_path.name, "sha256": file_sha256(source_path),
            "adapter": tango_adapter.ADAPTER_ID, "mapping_contract": contract.name,
            "mapping_contract_version": tango_adapter.MAPPING_VERSION,
            "mapping_contract_sha256": hashlib.sha256(contract.read_bytes()).hexdigest(),
            "deck_ids": [SYNTHETIC_DECK_ID], "note_type_ids": [SYNTHETIC_NOTE_TYPE_ID],
            "selection": {"order": "note_id_ascending", "count": count},
        },
        "normalization": {
            "source_map": "output/source-map.jsonl", "raw_notes": "output/raw-notes.jsonl",
            "exceptions": "output/exceptions.json", "report": "output/normalization-report.json",
        },
        "constraints": {"input_ids": project_ids},
    }
    if full_output:
        inputs = _projected_rows(source_notes, count)
        enriched = _output_rows(inputs)
        (output_dir).mkdir(parents=True, exist_ok=True)
        input_bytes, output_bytes = _compact_jsonl(inputs), _compact_jsonl(enriched)
        (output_dir / "enriched.jsonl").write_bytes(output_bytes)
        document["constraints"].update({
            "source_input_sha256": source_input_sha256 or hashlib.sha256(input_bytes).hexdigest(),
            "input_sha256": hashlib.sha256(output_bytes).hexdigest(),
            "revision": 1, "schema_version": "0.1.0",
        })
        document["package"] = {
            "apkg_filename": "synthetic-source.apkg", "model_name": "Synthetic source test model",
            "model_id": 1848570013, "deck_name": "Synthetic source test deck", "deck_id": 1848570012,
            "guid_namespace": "jp-deck/synthetic-source-tests/v1", "stable_id_epoch_seconds": 1800000000.0,
        }
    if source_input_sha256 is not None and not full_output:
        document["constraints"]["source_input_sha256"] = source_input_sha256
    path = directory / "synthetic-source.yaml"
    path.write_text(yaml.safe_dump(document, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return path


@contextmanager
def _synthetic_profile(config):
    """Rebind immutable profile fingerprints only for this synthetic fixture scope."""
    assert config.source is not None
    with ExitStack() as stack:
        for name, value in (
            ("SOURCE_SHA256", config.source.sha256),
            ("MAPPING_SHA256", config.source.mapping_contract_sha256),
            ("TARGET_DECK_ID", config.source.deck_ids[0]),
            ("SUPPORTED_NOTE_TYPE_ID", config.source.note_type_ids[0]),
        ):
            stack.enter_context(patch.object(tango_adapter, name, value))
        yield


def _cli(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(ROOT) + (os.pathsep + environment["PYTHONPATH"] if environment.get("PYTHONPATH") else "")
    wrapper = ROOT / "tests/helpers/run_synthetic_source_cli.py"
    return subprocess.run([sys.executable, str(wrapper), *args], cwd=cwd or ROOT,
                          env=environment, text=True, capture_output=True)


def _snapshot(config_path: Path):
    config = load_stage_config(config_path, stage="normalize")
    assert config.source is not None
    native_ids = tuple(int(input_id.removeprefix(tango_adapter.PROJECT_ID_PREFIX))
                       for input_id in (config.constraints.input_ids or ()))
    return read_source_snapshot(
        config.source.apkg, expected_sha256=config.source.sha256, deck_ids=config.source.deck_ids,
        note_type_ids=config.source.note_type_ids, selection_count=config.source.selection_count,
        selection_native_ids=native_ids,
    )


class SourceNormalizationTests(unittest.TestCase):
    def test_batching_tests_do_not_leak_the_synthetic_preflight_patch(self):
        import jp_deck.batching as batching
        from jp_deck.input_validation import validate_input_dataset as production_preflight
        self.assertIs(batching.validate_input_dataset, production_preflight)

    def test_reader_selects_modern_fabricated_collection_and_preserves_archive(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "synthetic.apkg"
            write_synthetic_apkg(path, DEFAULT_NOTES)
            before = file_sha256(path)
            snapshot = read_source_snapshot(path, expected_sha256=before, deck_ids=(SYNTHETIC_DECK_ID,),
                                            note_type_ids=(SYNTHETIC_NOTE_TYPE_ID,), selection_count=2)
            self.assertEqual(snapshot.database_member, DATABASE_MEMBER)
            self.assertEqual(tuple(int(note["id"]) for note in snapshot.selected_notes), (910001, 910002))
            self.assertEqual(snapshot.selected_cards[910002][0]["type"], 2)
            self.assertEqual(snapshot.selected_cards[910002][0]["queue"], 2)
            self.assertEqual(len(snapshot.selected_cards[910001]), 2)
            self.assertEqual(file_sha256(path), before)

    def test_reader_enforces_a_patched_small_decompressed_size_cap(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "bounded.apkg"
            write_synthetic_apkg(path, DEFAULT_NOTES)
            with zipfile.ZipFile(path, "r") as archive:
                compressed_frame_size = archive.getinfo(DATABASE_MEMBER).file_size
            patched_limit = compressed_frame_size + 1
            with patch.object(source_apkg_module, "MAX_DATABASE_BYTES", patched_limit):
                with self.assertRaisesRegex(SourceError, "decompressed size bound .* exceeds the safe limit"):
                    read_source_snapshot(path, expected_sha256=file_sha256(path), deck_ids=(SYNTHETIC_DECK_ID,),
                                         note_type_ids=(SYNTHETIC_NOTE_TYPE_ID,), selection_count=2)

    def test_reader_rejects_wrong_hash_schema_bad_frame_and_legacy_only_archive(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            path = folder / "source.apkg"; write_synthetic_apkg(path, DEFAULT_NOTES)
            with self.assertRaisesRegex(SourceError, "SHA-256 mismatch"):
                read_source_snapshot(path, expected_sha256="0" * 64, deck_ids=(SYNTHETIC_DECK_ID,),
                                     note_type_ids=(SYNTHETIC_NOTE_TYPE_ID,), selection_count=2)
            wrong_version = folder / "version.apkg"; write_synthetic_apkg(wrong_version, DEFAULT_NOTES, version=17)
            with self.assertRaisesRegex(SourceError, "schema version"):
                read_source_snapshot(wrong_version, expected_sha256=file_sha256(wrong_version),
                                     deck_ids=(SYNTHETIC_DECK_ID,), note_type_ids=(SYNTHETIC_NOTE_TYPE_ID,), selection_count=2)
            bad_frame = folder / "bad-frame.apkg"; write_synthetic_apkg(bad_frame, DEFAULT_NOTES, malformed_frame=True)
            with self.assertRaisesRegex(SourceError, "Zstandard"):
                read_source_snapshot(bad_frame, expected_sha256=file_sha256(bad_frame),
                                     deck_ids=(SYNTHETIC_DECK_ID,), note_type_ids=(SYNTHETIC_NOTE_TYPE_ID,), selection_count=2)
            legacy = folder / "legacy-only.apkg"; write_synthetic_apkg(legacy, DEFAULT_NOTES, only_legacy_stub=True)
            with self.assertRaisesRegex(SourceError, "exactly one collection.anki21b"):
                read_source_snapshot(legacy, expected_sha256=file_sha256(legacy),
                                     deck_ids=(SYNTHETIC_DECK_ID,), note_type_ids=(SYNTHETIC_NOTE_TYPE_ID,), selection_count=2)

    def test_explicit_native_selection_rejects_duplicates_order_scope_and_count(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "selection.apkg"; write_synthetic_apkg(path, DEFAULT_NOTES)
            fingerprint = file_sha256(path)
            for selected, count, diagnostic in (
                ((910001, 910001), 2, "duplicate"), ((910002, 910001), 2, "ascending"),
                ((910001, 999999), 2, "out-of-scope"), ((910001,), 2, "count"),
            ):
                with self.subTest(diagnostic=diagnostic), self.assertRaisesRegex(SourceError, diagnostic):
                    read_source_snapshot(path, expected_sha256=fingerprint, deck_ids=(SYNTHETIC_DECK_ID,),
                                         note_type_ids=(SYNTHETIC_NOTE_TYPE_ID,), selection_count=count,
                                         selection_native_ids=selected)

    def test_reviewed_card_and_note_id_order_are_independent_of_new_card_state(self):
        notes = [copy.deepcopy(note) for note in DEFAULT_NOTES]
        notes[0]["cards"] = [{"type": 0, "queue": 0}, {"type": 2, "queue": 2}]
        notes[1]["cards"] = [{"type": 2, "queue": 2}]
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "cards.apkg"; write_synthetic_apkg(path, notes)
            snapshot = read_source_snapshot(path, expected_sha256=file_sha256(path), deck_ids=(SYNTHETIC_DECK_ID,),
                                            note_type_ids=(SYNTHETIC_NOTE_TYPE_ID,), selection_count=2)
            self.assertEqual([note["id"] for note in snapshot.selected_notes], [910001, 910002])
            self.assertEqual([(card["type"], card["queue"]) for card in snapshot.selected_cards[910002]], [(2, 2)])
            self.assertEqual([(card["type"], card["queue"]) for card in snapshot.selected_cards[910001]], [(0, 0), (2, 2)])

    def test_production_projector_positive_cleanup_and_independent_literal_oracles(self):
        def project(native_id: int, **changes):
            fields = {name: "" for name in FIELD_SIGNATURE}
            fields.update({"stt": str(native_id), "kanji": "架空語甲", "furigana": "かくうごこう", "nghia": "nghĩa giả lập"})
            fields.update(changes)
            note = {"id": native_id, "mid": tango_adapter.SUPPORTED_NOTE_TYPE_ID,
                    "flds": "\x1f".join(fields[name] for name in FIELD_SIGNATURE)}
            return project_note(note, FIELD_SIGNATURE)

        positive_cases = [
            (project(8800001, kanji="  架空語甲  ", furigana="  かくうごこう  "),
             {"id": "tango-n1-mimi-n1-note-8800001", "expression": "架空語甲", "reading": "かくうごこう", "meaning_vi": "nghĩa giả lập"}),
            (project(8800002, kanji='<img src="synthetic">架空語乙'),
             {"id": "tango-n1-mimi-n1-note-8800002", "expression": "架空語乙", "reading": "かくうごこう", "meaning_vi": "nghĩa giả lập"}),
            (project(8800003, nghia="  nghĩa một<br>  nghĩa hai  "),
             {"id": "tango-n1-mimi-n1-note-8800003", "expression": "架空語甲", "reading": "かくうごこう", "meaning_vi": "nghĩa một\nnghĩa hai"}),
            (project(8800004, nghia="1. nghĩa một\n2. nghĩa hai"),
             {"id": "tango-n1-mimi-n1-note-8800004", "expression": "架空語甲", "reading": "かくうごこう", "meaning_vi": "1. nghĩa một\n2. nghĩa hai"}),
            (project(8800005, furigana="かくうごこう<br>かくうご"),
             {"id": "tango-n1-mimi-n1-note-8800005", "expression": "架空語甲", "reading": "かくうごこう\nかくうご", "meaning_vi": "nghĩa giả lập"}),
            (project(8800006, kanji="架空語甲／架空語乙"),
             {"id": "tango-n1-mimi-n1-note-8800006", "expression": "架空語甲／架空語乙", "reading": "かくうごこう", "meaning_vi": "nghĩa giả lập"}),
            (project(8800007, nghia=" dòng một<br/>dòng hai "),
             {"id": "tango-n1-mimi-n1-note-8800007", "expression": "架空語甲", "reading": "かくうごこう", "meaning_vi": "dòng một\ndòng hai"}),
        ]
        for actual, expected in positive_cases:
            with self.subTest(native_id=actual.native_note_id):
                self.assertEqual(actual.values, expected)

    def test_production_projector_blocker_reason_codes_and_bad_signatures(self):
        def native_note(native_id: int, *, mid: int | None = None, signature=FIELD_SIGNATURE, **changes):
            fields = {name: "" for name in FIELD_SIGNATURE}
            fields.update({"stt": str(native_id), "kanji": "架空語", "furigana": "かくうご", "nghia": "nghĩa"})
            fields.update(changes)
            return ({"id": native_id, "mid": tango_adapter.SUPPORTED_NOTE_TYPE_ID if mid is None else mid,
                     "flds": "\x1f".join(fields.get(name, "") for name in signature)}, signature)
        blockers = (
            (native_note(8810001, mid=1427382454382), "unsupported_combined_basic_fields"),
            (native_note(8810002, kanji="", furigana=""), "missing_expression_and_reading"),
            (native_note(8810003, nghia=""), "missing_meaning_vi"),
            (native_note(8810004, furigana="かな漢字"), "reading_expression_field_mismatch"),
            (native_note(8810005, kanji="架空語\nannotation"), "expression_has_explanatory_annotation"),
            (native_note(8810006, kanji="架空語\n別の語"), "multiple_expression_reading_pairing"),
            (native_note(8810007, kanji=""), "missing_expression"),
            (native_note(8810008, furigana=""), "missing_reading"),
            (native_note(8810009, mid=99999), "unsupported_note_type"),
            (native_note(8810010, signature=("wrong", *FIELD_SIGNATURE[1:])), "unsupported_field_signature"),
        )
        for (note, signature), reason_code in blockers:
            with self.subTest(reason_code=reason_code), self.assertRaises(MappingFailure) as caught:
                project_note(note, signature)
            self.assertEqual(caught.exception.reason_code, reason_code)
        malformed, signature = native_note(8810011)
        malformed["flds"] = "only-one-field"
        with self.assertRaises(MappingFailure) as caught:
            project_note(malformed, signature)
        self.assertEqual(caught.exception.reason_code, "malformed_field_count")

    def test_production_profile_constants_stay_strict_and_adapter_registry_is_finite(self):
        with self.assertRaisesRegex(ValueError, "Unsupported source adapter profile"):
            get_source_adapter("untrusted.synthetic.module")
        with tempfile.TemporaryDirectory() as temp:
            config = load_stage_config(_write_config(Path(temp)), stage="normalize")
            with self.assertRaisesRegex(MappingFailure, "source.sha256 does not match the accepted Tango profile"):
                tango_adapter.validate_profile_config(config)

    def test_source_stage_config_rejects_types_duplicate_native_ids_and_invalid_profile(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp); base_path = _write_config(folder)
            base = yaml.safe_load(base_path.read_text(encoding="utf-8"))
            mutations = (
                (lambda d: d["source"]["selection"].__setitem__("count", True), "selection.count"),
                (lambda d: d["source"].__setitem__("deck_ids", [SYNTHETIC_DECK_ID] * 2), "duplicate IDs"),
                (lambda d: d["source"].__setitem__("sha256", "bad"), "source.sha256"),
                (lambda d: d["source"]["selection"].__setitem__("order", "random"), "selection.order"),
                (lambda d: d["source"].__setitem__("adapter", "untrusted.module"), "unsupported source adapter"),
                (lambda d: d.__setitem__("config_version", True), "config_version"),
            )
            for index, (mutate, diagnostic) in enumerate(mutations):
                candidate = copy.deepcopy(base); mutate(candidate)
                path = folder / f"invalid-profile-{index}.yaml"
                path.write_text(yaml.safe_dump(candidate, allow_unicode=True, sort_keys=False), encoding="utf-8")
                with self.subTest(diagnostic=diagnostic), self.assertRaisesRegex(ConfigError, diagnostic):
                    load_stage_config(path, stage="normalize")

    def test_normalize_emits_literal_projection_raw_map_and_owner_relative_reports(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp); config_path = _write_config(folder, full_output=True)
            with _synthetic_profile(load_stage_config(config_path, stage="normalize")):
                config = load_stage_config(config_path, stage="normalize")
                result = normalize_source(config)
                checked = validate_input_dataset(config)
            expected = [
                {"id": "tango-n1-mimi-n1-note-910001", "expression": "架空語甲", "reading": "かくうごこう", "meaning_vi": "nghĩa giả lập alpha"},
                {"id": "tango-n1-mimi-n1-note-910002", "expression": "霧環", "reading": "きりわ", "meaning_vi": "vòng sương giả lập"},
                {"id": "tango-n1-mimi-n1-note-910003", "expression": "星綴", "reading": "ほしつづり", "meaning_vi": "dệt sao giả lập"},
            ]
            self.assertEqual(_jsonl(config.paths.source_input), expected)
            self.assertEqual(result["checked_counts"]["normalized_inputs"], 3)
            self.assertEqual(checked["checked_counts"]["input_records"], 3)
            mappings = _jsonl(config.normalization.source_map); raw = _jsonl(config.normalization.raw_notes)
            self.assertEqual([row["native_note_id"] for row in mappings], [910001, 910002, 910003])
            self.assertEqual(mappings[0]["source_apkg"], "../Tango_N1_MiMi_n1.apkg")
            self.assertEqual(mappings[0]["mapping_contract"], "../mapping-contract.md")
            self.assertEqual(raw[0]["native_note"]["guid"], "synthetic-guid-910001")
            persisted = json.loads(config.normalization.report.read_text(encoding="utf-8"))
            self.assertEqual(persisted["source"]["path"], "../Tango_N1_MiMi_n1.apkg")
            self.assertEqual(persisted["artifacts"]["source_map"], "source-map.jsonl")
            self.assertFalse(Path(checked["input_path"]).is_absolute())
            self.assertFalse(Path(checked["input_schema"]).is_absolute())

    def test_two_independent_normalizations_have_identical_input_raw_map_and_exception_bytes(self):
        results = []
        shared_source_bytes = None
        for suffix in ("first", "second"):
            with tempfile.TemporaryDirectory() as temp:
                folder = Path(temp) / suffix
                config_path = _write_config(folder)
                source_path = folder / "Tango_N1_MiMi_n1.apkg"
                document = yaml.safe_load(config_path.read_text(encoding="utf-8"))
                if shared_source_bytes is None:
                    shared_source_bytes = source_path.read_bytes()
                else:
                    source_path.write_bytes(shared_source_bytes)
                    document["source"]["sha256"] = hashlib.sha256(shared_source_bytes).hexdigest()
                    config_path.write_text(yaml.safe_dump(document, allow_unicode=True, sort_keys=False), encoding="utf-8")
                with _synthetic_profile(load_stage_config(config_path, stage="normalize")):
                    config = load_stage_config(config_path, stage="normalize"); normalize_source(config)
                results.append(tuple(path.read_bytes() for path in (
                    config.paths.source_input, config.normalization.source_map,
                    config.normalization.raw_notes, config.normalization.exceptions,
                )))
        self.assertEqual(results[0], results[1])

    def test_source_map_relative_and_legacy_absolute_paths_resolve_from_map_owner_after_relocation(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp); original = base / "original"; config_path = _write_config(original)
            with _synthetic_profile(load_stage_config(config_path, stage="normalize")):
                config = load_stage_config(config_path, stage="normalize"); normalize_source(config)
                map_path = config.normalization.source_map; map_original = map_path.read_bytes(); mappings = _jsonl(map_path)
                mappings[0]["source_apkg"] = str(config.source.apkg.resolve())
                mappings[0]["mapping_contract"] = str(config.source.mapping_contract.resolve())
                map_path.write_bytes(_compact_jsonl(mappings))
                validate_input_dataset(config)
                map_path.write_bytes(map_original)
                portable_copy = base / "relocated"; shutil.copytree(original, portable_copy); shutil.rmtree(original)
                moved_config = load_stage_config(portable_copy / config_path.name, stage="normalize")
                moved_report = validate_input_dataset(moved_config)
            self.assertEqual(moved_report["checked_counts"]["input_records"], 3)

    def test_production_map_raw_snapshot_mutations_reject_even_after_outer_rehash(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp); config_path = _write_config(folder)
            with _synthetic_profile(load_stage_config(config_path, stage="normalize")):
                config = load_stage_config(config_path, stage="normalize"); normalize_source(config)
                map_path, raw_path = config.normalization.source_map, config.normalization.raw_notes
                map_original, raw_original = map_path.read_bytes(), raw_path.read_bytes()

                maps = _jsonl(map_path); maps[0]["native_note_id"] += 1
                map_path.write_bytes(_compact_jsonl(maps))
                with self.assertRaisesRegex(InputStageError, "project ID does not encode native note identity"):
                    validate_input_dataset(config)
                map_path.write_bytes(map_original)

                maps, raw = _jsonl(map_path), _jsonl(raw_path)
                raw[0]["cards"][0]["id"] += 100
                maps[0]["card_ids"] = [card["id"] for card in raw[0]["cards"]]
                maps[0]["raw_note_sha256"] = hashlib.sha256(json.dumps(raw[0], ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
                map_path.write_bytes(_compact_jsonl(maps)); raw_path.write_bytes(_compact_jsonl(raw))
                with self.assertRaisesRegex(InputStageError, "raw sidecar differs from the original APKG snapshot"):
                    validate_input_dataset(config)
                map_path.write_bytes(map_original); raw_path.write_bytes(raw_original)
                validate_input_dataset(config)

    def test_minimal_source_free_validate_input_accepts_variable_counts_and_rejects_empty(self):
        for count in (0, 1, 4, 5, 6):
            with self.subTest(count=count), tempfile.TemporaryDirectory() as temp:
                folder = Path(temp); case = folder / f"case-{count}"; case.mkdir()
                rows = [
                    {"id": f"minimal-{count}-{index}", "expression": f"架空語{index}",
                     "reading": f"かくうご{index}", "meaning_vi": f"nghĩa giả lập {index}"}
                    for index in range(count)
                ]
                input_path = case / "input.jsonl"; input_path.write_bytes(_compact_jsonl(rows))
                config_path = case / "minimal.yaml"
                config_path.write_text(yaml.safe_dump({"config_version": 2, "paths": {
                    "source_input": str(input_path), "input_schema": str(INPUT_SCHEMA.resolve()),
                }}, sort_keys=False), encoding="utf-8")
                result = subprocess.run([sys.executable, "-m", "jp_deck", "validate-input", "--config", str(config_path)],
                                        cwd=ROOT, text=True, capture_output=True)
                report_path = input_path.with_name("input-validation-report.json")
                if count:
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(json.loads(result.stdout)["checked_counts"]["input_records"], count)
                    self.assertTrue(report_path.is_file())
                else:
                    self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                    self.assertIn("at least one", json.loads(result.stderr)["errors"][0]["message"])
                    self.assertFalse(report_path.exists())

    def test_validate_input_report_alias_guards_preserve_all_declared_path_sentinels(self):
        for alias in ("source_input", "input_schema", "input", "output_schema"):
            with self.subTest(alias=alias), tempfile.TemporaryDirectory() as temp:
                folder = Path(temp); case = folder / alias; case.mkdir()
                input_path = case / "input.jsonl"
                input_path.write_bytes(_compact_jsonl([{"id": "report-alias", "expression": "架空語",
                                                       "reading": "かくうご", "meaning_vi": "nghĩa thử"}]))
                report_path = case / "input-validation-report.json"
                paths = {"source_input": str(input_path), "input_schema": str(INPUT_SCHEMA.resolve())}
                if alias == "source_input":
                    input_path = report_path
                    input_path.write_bytes(_compact_jsonl([{"id": "report-alias", "expression": "架空語",
                                                             "reading": "かくうご", "meaning_vi": "nghĩa thử"}]))
                    paths["source_input"] = str(input_path)
                elif alias == "input_schema":
                    report_path.write_bytes(INPUT_SCHEMA.read_bytes())
                    paths["input_schema"] = str(report_path)
                else:
                    report_path.write_bytes(f"DECLARED_{alias}_SENTINEL".encode("ascii"))
                    paths[alias] = str(report_path)
                sentinel = report_path.read_bytes()
                config_path = case / "minimal.yaml"
                config_path.write_text(yaml.safe_dump({"config_version": 2, "paths": paths}, sort_keys=False),
                                       encoding="utf-8")
                result = subprocess.run([sys.executable, "-m", "jp_deck", "validate-input", "--config", str(config_path)],
                                        cwd=ROOT, text=True, capture_output=True)
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertIn("aliases a protected input", result.stderr)
                self.assertEqual(report_path.read_bytes(), sentinel)

    def test_normalize_force_collision_protected_and_symlink_boundaries(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            config_path = _write_config(folder / "force")
            config = load_stage_config(config_path, stage="normalize")
            with _synthetic_profile(config):
                normalize_source(config)
                outputs = (config.paths.source_input, config.normalization.source_map, config.normalization.raw_notes,
                           config.normalization.exceptions, config.normalization.report)
                original_bytes = {path: path.read_bytes() for path in outputs}
                unrelated = folder / "unrelated-sentinel.bin"
                unrelated.write_bytes(b"UNRELATED_SENTINEL_MUST_SURVIVE_FORCE\n")
                unrelated_before = unrelated.read_bytes()
                with self.assertRaisesRegex(FileExistsError, "use --force"):
                    normalize_source(config)
                self.assertEqual({path: path.read_bytes() for path in outputs}, original_bytes)
                normalize_source(config, force=True)
                self.assertEqual({path: path.read_bytes() for path in outputs}, original_bytes)
                self.assertEqual(unrelated.read_bytes(), unrelated_before)

        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            config_path = _write_config(folder / "collision")
            document = yaml.safe_load(config_path.read_text(encoding="utf-8"))
            document["normalization"]["raw_notes"] = document["normalization"]["source_map"]
            config_path.write_text(yaml.safe_dump(document, allow_unicode=True, sort_keys=False), encoding="utf-8")
            config = load_stage_config(config_path, stage="normalize")
            collision_path = config.normalization.source_map
            collision_path.parent.mkdir(parents=True, exist_ok=True)
            collision_path.write_bytes(b"COLLISION_SENTINEL_MUST_SURVIVE_FORCE\n")
            collision_before = collision_path.read_bytes()
            with _synthetic_profile(config), self.assertRaisesRegex(SourceError, "path collision"):
                normalize_source(config, force=True)
            self.assertEqual(collision_path.read_bytes(), collision_before)
            for path in (config.paths.source_input, config.normalization.exceptions, config.normalization.report):
                self.assertFalse(path.exists(), path)

        cases = (
            ("protected-apkg", "apkg", False),
            ("protected-contract", "contract", False),
            ("symlink-apkg", "apkg", True),
            ("symlink-contract", "contract", True),
        )
        for case_name, victim_kind, use_symlink in cases:
            with self.subTest(case=case_name), tempfile.TemporaryDirectory() as temp:
                folder = Path(temp)
                config_path = _write_config(folder)
                document = yaml.safe_load(config_path.read_text(encoding="utf-8"))
                source_path = folder / "Tango_N1_MiMi_n1.apkg"
                contract_path = folder / "mapping-contract.md"
                victim = source_path if victim_kind == "apkg" else contract_path
                victim_before = victim.read_bytes()
                alias_path = None
                if use_symlink:
                    alias_path = folder / "output/protected-output.jsonl"
                    alias_path.parent.mkdir(parents=True, exist_ok=True)
                    alias_path.symlink_to(victim.resolve())
                    document["normalization"]["raw_notes"] = "output/protected-output.jsonl"
                else:
                    document["normalization"]["raw_notes"] = str(victim.resolve())
                config_path.write_text(yaml.safe_dump(document, allow_unicode=True, sort_keys=False), encoding="utf-8")
                config = load_stage_config(config_path, stage="normalize")
                with _synthetic_profile(config), self.assertRaisesRegex(SourceError, "protected input"):
                    normalize_source(config, force=True)
                self.assertEqual(victim.read_bytes(), victim_before)
                if alias_path is not None:
                    self.assertTrue(alias_path.is_symlink())
                    self.assertEqual(alias_path.resolve(), victim.resolve())
                for path in (config.paths.source_input, config.normalization.source_map,
                             config.normalization.exceptions, config.normalization.report):
                    self.assertFalse(path.exists(), path)

    def test_production_map_paths_reject_wrong_targets_for_each_reference_and_owner(self):
        cases = ("missing_target", "different_target", "absolute_other_target", "moved_owner_same_basename")
        for field in ("source_apkg", "mapping_contract"):
            for case_name in cases:
                with self.subTest(field=field, case=case_name), tempfile.TemporaryDirectory() as temp:
                    folder = Path(temp)
                    config_path = _write_config(folder)
                    config = load_stage_config(config_path, stage="normalize")
                    with _synthetic_profile(config):
                        normalize_source(config)
                        target = config.source.apkg if field == "source_apkg" else config.source.mapping_contract
                        map_path = config.normalization.source_map
                        mappings = _jsonl(map_path)
                        if case_name == "missing_target":
                            alternate = folder / f"missing-{target.name}"
                            mappings[0][field] = os.path.relpath(alternate, map_path.parent)
                        elif case_name in ("different_target", "absolute_other_target"):
                            alternate = folder / f"alternate-{target.name}"
                            shutil.copyfile(target, alternate)
                            if case_name == "absolute_other_target":
                                mappings[0][field] = str(alternate.resolve())
                            else:
                                mappings[0][field] = os.path.relpath(alternate, map_path.parent)
                        else:
                            moved_map = folder / "moved/normalized/source-map.jsonl"
                            moved_map.parent.mkdir(parents=True)
                            moved_same_name = folder / "moved" / target.name
                            shutil.copyfile(target, moved_same_name)
                            other_field = "mapping_contract" if field == "source_apkg" else "source_apkg"
                            other_target = (config.source.mapping_contract if other_field == "mapping_contract"
                                            else config.source.apkg)
                            mappings[0][field] = f"../{target.name}"
                            mappings[0][other_field] = os.path.relpath(other_target, moved_map.parent)
                            document = yaml.safe_load(config_path.read_text(encoding="utf-8"))
                            document["normalization"]["source_map"] = str(moved_map)
                            config_path.write_text(yaml.safe_dump(document, allow_unicode=True, sort_keys=False),
                                                   encoding="utf-8")
                            map_path = moved_map
                            config = load_stage_config(config_path, stage="validate-input")
                        map_path.write_bytes(_compact_jsonl(mappings))
                        with self.assertRaisesRegex(InputStageError,
                                                    "source-map path does not bind the configured artifact"):
                            validate_input_dataset(config)
                        report_path = config.normalization.report.with_name("input-validation-report.json")
                        self.assertFalse(report_path.exists())

    def test_blocked_nonprefix_selected_native_note_is_not_replaced_or_published(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            notes = [
                _note(910001, expression="架空語甲", reading="かくうごこう"),
                _note(910002, expression="", reading=""),
                _note(910003, expression="架空語丙", reading="かくうごへい"),
            ]
            config_path = _write_config(folder, notes=notes, selection_count=2)
            document = yaml.safe_load(config_path.read_text(encoding="utf-8"))
            document["constraints"]["input_ids"] = [
                "tango-n1-mimi-n1-note-910002", "tango-n1-mimi-n1-note-910003",
            ]
            config_path.write_text(yaml.safe_dump(document, allow_unicode=True, sort_keys=False), encoding="utf-8")
            config = load_stage_config(config_path, stage="normalize")
            with _synthetic_profile(config), self.assertRaisesRegex(SourceError,
                                                                     "910002.*no replacement is permitted"):
                normalize_source(config)
            self.assertEqual(config.constraints.input_ids,
                             ("tango-n1-mimi-n1-note-910002", "tango-n1-mimi-n1-note-910003"))
            self.assertNotIn("tango-n1-mimi-n1-note-910001", config.constraints.input_ids)
            for path in (config.paths.source_input, config.normalization.source_map, config.normalization.raw_notes,
                         config.normalization.exceptions, config.normalization.report):
                self.assertFalse(path.exists(), path)
            self.assertFalse(config.paths.source_input.parent.exists())

    def test_nonprefix_native_selection_accounts_selected_and_unselected_eligibility(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            notes = [
                _note(910001, expression="架空語甲", reading="かくうごこう"),
                _note(910002, expression="", reading=""),
                _note(910003, expression="架空語丙", reading="かくうごへい"),
                _note(910004, expression="架空語丁", reading="かくうごてい"),
            ]
            config_path = _write_config(folder, notes=notes, selection_count=2)
            document = yaml.safe_load(config_path.read_text(encoding="utf-8"))
            document["constraints"]["input_ids"] = [
                "tango-n1-mimi-n1-note-910001", "tango-n1-mimi-n1-note-910003",
            ]
            config_path.write_text(yaml.safe_dump(document, allow_unicode=True, sort_keys=False), encoding="utf-8")
            config = load_stage_config(config_path, stage="normalize")
            with _synthetic_profile(config):
                normalized = normalize_source(config)
                validated = validate_input_dataset(load_stage_config(config_path, stage="validate-input"))
            exceptions = json.loads(config.normalization.exceptions.read_text(encoding="utf-8"))
            self.assertEqual([row["id"] for row in _jsonl(config.paths.source_input)], [
                "tango-n1-mimi-n1-note-910001", "tango-n1-mimi-n1-note-910003",
            ])
            self.assertEqual(normalized["checked_counts"]["normalized_inputs"], 2)
            self.assertEqual(normalized["checked_counts"]["unselected_note_count"], 2)
            self.assertEqual(normalized["checked_counts"]["eligible_unselected"], 1)
            self.assertEqual(normalized["checked_counts"]["ineligible_unselected"], 1)
            self.assertEqual(validated["checked_counts"]["input_records"], 2)
            self.assertEqual(exceptions["selected_native_note_ids"], [910001, 910003])
            self.assertEqual(exceptions["unselected_note_ids"], [910002, 910004])
            self.assertEqual(exceptions["eligible_unselected_count"], 1)
            self.assertEqual(exceptions["ineligible_unselected_count"], 1)
            self.assertEqual(exceptions["exceptions"][0]["native_note_id"], 910002)
            self.assertEqual(exceptions["exceptions"][0]["selection_status"], "unselected")
            self.assertEqual(exceptions["exceptions"][0]["reason_code"], "missing_expression_and_reading")

    def test_duplicate_native_expressions_keep_distinct_identity_through_production_batching(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            notes = [
                _note(910001, expression="架空重複語", reading="かくうちょうふく"),
                _note(910002, expression="架空重複語", reading="かくうちょうふく", meaning="別の架空訳"),
            ]
            config_path = _write_config(folder, notes=notes, selection_count=2)
            document = yaml.safe_load(config_path.read_text(encoding="utf-8"))
            document["batching"] = {"batch_size": 2, "output_dir": "output/batches"}
            config_path.write_text(yaml.safe_dump(document, allow_unicode=True, sort_keys=False), encoding="utf-8")
            config = load_stage_config(config_path, stage="normalize")
            with _synthetic_profile(config):
                normalize_source(config)
                input_result = _cli("validate-input", "--config", str(config_path))
                self.assertEqual(input_result.returncode, 0, input_result.stderr)
                self.assertEqual(json.loads(input_result.stdout)["checked_counts"]["input_records"], 2)
                batch_config = load_stage_config(config_path, stage="prepare-batches")
                prepared = prepare_batches(batch_config)
                validated = validate_batches(load_stage_config(config_path, stage="validate-batches"))
            master = _jsonl(config.paths.source_input)
            batch_rows = _jsonl(batch_config.batching.output_dir / "batch-001/input.jsonl")
            self.assertEqual(prepared["batch_sizes"], [2])
            self.assertEqual(validated["checked_counts"]["master_records"], 2)
            self.assertEqual([row["id"] for row in master],
                             ["tango-n1-mimi-n1-note-910001", "tango-n1-mimi-n1-note-910002"])
            self.assertEqual([row["expression"] for row in master], ["架空重複語", "架空重複語"])
            self.assertEqual([row["id"] for row in batch_rows], [row["id"] for row in master])
            self.assertEqual([row["native_note_id"] for row in _jsonl(config.normalization.source_map)], [910001, 910002])

    def test_production_malformed_map_and_raw_shapes_keep_error_file_record_path_across_stages(self):
        mutations = (
            ("map-card-ids", "source_map", "/source_map/0/card_ids"),
            ("raw-card-element", "raw_notes", "/raw_notes/0/cards/0"),
        )
        for label, sidecar_key, expected_path in mutations:
            for stage in ("validate-input", "validate-output", "build"):
                with self.subTest(mutation=label, stage=stage), tempfile.TemporaryDirectory() as temp:
                    folder = Path(temp); config_path = _write_config(folder, full_output=True)
                    with _synthetic_profile(load_stage_config(config_path, stage="normalize")):
                        config = load_stage_config(config_path, stage="normalize"); normalize_source(config)
                    document = yaml.safe_load(config_path.read_text(encoding="utf-8"))
                    sidecar = folder / f"effective-{sidecar_key}.jsonl"
                    source_sidecar_value = Path(document["normalization"][sidecar_key])
                    source_sidecar = source_sidecar_value if source_sidecar_value.is_absolute() else (config_path.parent / source_sidecar_value).resolve()
                    rows = _jsonl(source_sidecar)
                    if sidecar_key == "source_map": rows[0]["card_ids"] = "not-a-list"
                    else: rows[0]["cards"][0] = 7
                    sidecar.write_bytes(_compact_jsonl(rows))
                    document["normalization"][sidecar_key] = str(sidecar.resolve())
                    config_path.write_text(yaml.safe_dump(document, allow_unicode=True, sort_keys=False), encoding="utf-8")
                    result = _cli(stage, "--config", str(config_path))
                    self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                    error = json.loads(result.stderr)["errors"][0]
                    self.assertEqual(error["file"], str(sidecar.resolve()))
                    self.assertEqual(error["record_id"], "tango-n1-mimi-n1-note-910001")
                    self.assertEqual(error["path"], expected_path)
                    self.assertFalse(Path(document["paths"]["output_dir"]).exists())

    def test_production_adapter_selection_and_normalization_work_from_unrelated_cwd(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp); config_path = _write_config(folder); unrelated = folder / "unrelated"; unrelated.mkdir()
            normalized = _cli("normalize", "--config", str(config_path), cwd=unrelated)
            self.assertEqual(normalized.returncode, 0, normalized.stderr)
            result = json.loads(normalized.stdout)
            self.assertEqual(result["selection"]["selected_native_note_ids"], [910001, 910002, 910003])
            validated = _cli("validate-input", "--config", str(config_path), cwd=unrelated)
            self.assertEqual(validated.returncode, 0, validated.stderr)
            self.assertEqual(json.loads(validated.stdout)["checked_counts"]["input_records"], 3)


if __name__ == "__main__":
    unittest.main()
