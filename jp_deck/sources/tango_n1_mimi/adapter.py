"""Accepted deterministic source-to-input profile for Tango N1 / MiMi n1."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, TYPE_CHECKING

from ...pathrefs import relative_reference, resolve_reference
from ...source_apkg import CARD_COLUMNS, DATABASE_MEMBER, NOTE_COLUMNS, SourceSnapshot, file_sha256, read_source_snapshot
from ...validation import InputStageError

if TYPE_CHECKING:
    from ...config import SourceSettings, StageConfig


ADAPTER_ID = "tango-n1-mimi-n1-v1"
MAPPING_VERSION = "tango-n1-mimi-n1-mapping/v1"
MAPPING_SHA256 = "bfd19fcb43c1023b1fd3f05d6b91704853953f9812ca3b22df5783d8dcadc054"
SOURCE_SHA256 = "275658b9dc9873ca90a56abea1440659f8a1aa4ab685d0b8716161f1b142ff06"
TARGET_DECK_ID = 1790560067565
SUPPORTED_NOTE_TYPE_ID = 1542253319207
FIELD_SIGNATURE = (
    "stt", "furigana", "kanji", "hanviet", "nghia", "vidu", "nghiavidu", "tudongnghia",
    "lientuong", "tutrainghia", "sound",
)
PROJECT_ID_PREFIX = "tango-n1-mimi-n1-note-"

_BR = re.compile(r"<br\s*/?>", re.IGNORECASE)
_IMAGE = re.compile(r"<img\b[^>]*>", re.IGNORECASE)
_ENTITY = re.compile(r"&(?:#[0-9]+|#x[0-9a-fA-F]+|[A-Za-z][A-Za-z0-9]+);", re.IGNORECASE)
_CJK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\U00020000-\U000323af]")


class MappingFailure(ValueError):
    def __init__(self, reason_code: str, message: str):
        super().__init__(message)
        self.reason_code = reason_code


@dataclass(frozen=True)
class Projection:
    project_id: str
    native_note_id: int
    values: dict[str, str]
    original_fields: dict[str, str]


def validate_profile_config(config: StageConfig) -> SourceSettings:
    source = config.source
    if source is None:
        raise MappingFailure("source_profile_missing", "Tango source profile is required")
    declared = {
        "adapter": (source.adapter, ADAPTER_ID),
        "source.sha256": (source.sha256.lower(), SOURCE_SHA256),
        "mapping_contract_version": (source.mapping_contract_version, MAPPING_VERSION),
        "mapping_contract_sha256": (source.mapping_contract_sha256.lower(), MAPPING_SHA256),
        "deck_ids": (source.deck_ids, (TARGET_DECK_ID,)),
        "note_type_ids": (source.note_type_ids, (SUPPORTED_NOTE_TYPE_ID,)),
        "selection.order": (source.selection_order, "note_id_ascending"),
    }
    for key, (actual, expected) in declared.items():
        if actual != expected:
            raise MappingFailure("unsupported_profile_setting", f"{key} does not match the accepted Tango profile")
    if source.apkg.name != "Tango_N1_MiMi_n1.apkg":
        raise MappingFailure("unsupported_source_path", "source.apkg must name the accepted Tango_N1_MiMi_n1.apkg snapshot")
    native_ids = configured_native_ids(config)
    if source.selection_count != len(native_ids):
        raise MappingFailure("unsupported_selection", "source.selection.count must equal the configured native-ID binding")
    return source


def _clean_source_text(value: str, *, field: str) -> str:
    text = _IMAGE.sub("", value)
    text = _BR.sub("\n", text)
    if "<" in text or ">" in text:
        raise MappingFailure("unsupported_markup", f"field {field!r} contains unsupported markup")
    if _ENTITY.search(text):
        raise MappingFailure("unsupported_entity", f"field {field!r} contains an unreviewed HTML entity")
    lines = [line.strip() for line in text.split("\n")]
    while lines and lines[0] == "":
        lines.pop(0)
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines)


def source_fields(note: dict[str, Any], fields: tuple[str, ...]) -> dict[str, str]:
    if int(note["mid"]) != SUPPORTED_NOTE_TYPE_ID:
        reason = "unsupported_combined_basic_fields" if int(note["mid"]) == 1427382454382 else "unsupported_note_type"
        raise MappingFailure(reason, f"native note {note['id']} has unsupported note type {note['mid']}")
    if fields != FIELD_SIGNATURE:
        raise MappingFailure("unsupported_field_signature", f"native note {note['id']} has an unsupported field signature")
    split_fields = str(note["flds"]).split("\x1f")
    if len(split_fields) != len(FIELD_SIGNATURE):
        raise MappingFailure(
            "malformed_field_count",
            f"native note {note['id']} has {len(split_fields)} fields; expected {len(FIELD_SIGNATURE)}",
        )
    return dict(zip(FIELD_SIGNATURE, split_fields, strict=True))


def project_note(note: dict[str, Any], fields: tuple[str, ...]) -> Projection:
    original = source_fields(note, fields)
    native_id = int(note["id"])
    expression = _clean_source_text(original["kanji"], field="kanji")
    reading = _clean_source_text(original["furigana"], field="furigana")
    meaning = _clean_source_text(original["nghia"], field="nghia")
    if "\n" in expression:
        reason = "expression_has_explanatory_annotation" if re.search(r"[A-Za-z]", expression) else "multiple_expression_reading_pairing"
        raise MappingFailure(reason, f"native note {native_id} has unsupported multiline expression text")
    if _CJK.search(reading):
        raise MappingFailure("reading_expression_field_mismatch", f"native note {native_id} has CJK text in its reading field")
    if not expression.strip() and not reading.strip():
        raise MappingFailure("missing_expression_and_reading", f"native note {native_id} has no expression or reading")
    for field, value in (("expression", expression), ("reading", reading), ("meaning_vi", meaning)):
        if not value.strip():
            raise MappingFailure(f"missing_{field}", f"native note {native_id} has no usable {field}")
    project_id = f"{PROJECT_ID_PREFIX}{native_id}"
    return Projection(
        project_id=project_id,
        native_note_id=native_id,
        values={"id": project_id, "expression": expression, "reading": reading, "meaning_vi": meaning},
        original_fields=original,
    )


def validate_map_linkage(
    config: StageConfig,
    records: list[dict[str, Any]],
    source_map: list[dict[str, Any]],
    raw_notes: list[dict[str, Any]],
    snapshot=None,
) -> None:
    source = validate_profile_config(config)
    if config.normalization is None:
        raise InputStageError("source linkage normalization paths are required", file=str(config.config_path))
    _validate_sidecar_shapes(
        records,
        source_map,
        raw_notes,
        source_map_file=str(config.normalization.source_map),
        raw_notes_file=str(config.normalization.raw_notes),
    )
    if snapshot is None:
        snapshot = read_source_snapshot(
            source.apkg,
            expected_sha256=source.sha256,
            deck_ids=source.deck_ids,
            note_type_ids=source.note_type_ids,
            selection_count=source.selection_count,
            selection_native_ids=configured_native_ids(config),
        )
    expected_native_ids = configured_native_ids(config)
    if tuple(int(note["id"]) for note in snapshot.selected_notes) != expected_native_ids:
        raise InputStageError("source linkage path /native_note_id: APKG selection differs from configured ordered identities")
    if len(source_map) != len(records) or len(raw_notes) != len(records):
        raise InputStageError(
            "source linkage path $: source-map and raw-note counts must equal the normalized input count"
        )
    seen_projects: set[str] = set()
    seen_native: set[int] = set()
    for index, (record, mapping, raw) in enumerate(zip(records, source_map, raw_notes, strict=True), start=1):
        project_id = record["id"]
        context = f"source linkage {project_id} line {index}"
        if mapping.get("project_id") != project_id:
            raise InputStageError(f"{context} path /project_id: input and source-map linkage differs")
        if project_id in seen_projects:
            raise InputStageError(f"{context} path /project_id: duplicate source-map project ID")
        seen_projects.add(project_id)
        native_id = mapping.get("native_note_id")
        if isinstance(native_id, bool) or not isinstance(native_id, int) or project_id != f"{PROJECT_ID_PREFIX}{native_id}":
            raise InputStageError(f"{context} path /native_note_id: project ID does not encode native note identity")
        if native_id in seen_native:
            raise InputStageError(f"{context} path /native_note_id: duplicate native note identity")
        seen_native.add(native_id)
        raw_native_note = raw.get("native_note")
        if not isinstance(raw_native_note, dict) or native_id != raw_native_note.get("id"):
            raise InputStageError(f"{context} path /native_note/id: map and raw note identities differ")
        if mapping.get("source_sha256") != SOURCE_SHA256 or raw.get("source_sha256") != SOURCE_SHA256:
            raise InputStageError(f"{context} path /source_sha256: source snapshot fingerprint differs")
        if mapping.get("database_member") != DATABASE_MEMBER or raw.get("source_database") != DATABASE_MEMBER:
            raise InputStageError(f"{context} path /database_member: expected modern vocabulary database")
        if raw.get("contract_version") != MAPPING_VERSION or raw.get("selection_position") != index:
            raise InputStageError(f"{context} path /selection_position: raw note provenance/version differs")
        if mapping.get("adapter") != ADAPTER_ID or mapping.get("mapping_contract_version") != MAPPING_VERSION:
            raise InputStageError(f"{context} path /adapter: mapping profile/version differs")
        if mapping.get("note_type_id") != SUPPORTED_NOTE_TYPE_ID:
            raise InputStageError(f"{context} path /note_type_id: unsupported mapped note type")
        if mapping.get("selection_position") != index:
            raise InputStageError(f"{context} path /selection_position: expected frozen position {index}")
        native_note = raw_native_note
        if native_note.get("mid") != SUPPORTED_NOTE_TYPE_ID:
            raise InputStageError(f"{context} path /native_note/mid: raw note type differs from supported type")
        if mapping.get("native_guid") != native_note.get("guid"):
            raise InputStageError(f"{context} path /native_guid: map and raw GUID differ")
        if native_note.get("flds") is None:
            raise InputStageError(f"{context} path /native_note/flds: raw source text is missing")
        signature = raw.get("field_signature")
        if signature != list(FIELD_SIGNATURE):
            raise InputStageError(f"{context} path /field_signature: raw field signature differs")
        fields = raw.get("fields_original")
        try:
            extracted_fields = source_fields(native_note, FIELD_SIGNATURE)
        except (KeyError, TypeError, ValueError) as exc:
            raise InputStageError(f"{context} path /native_note/flds: cannot verify source field text: {exc}") from exc
        if not isinstance(fields, dict) or fields != extracted_fields:
            raise InputStageError(f"{context} path /fields_original: raw fields do not match original flds text")
        raw_digest = hashlib.sha256(_canonical_json(raw)).hexdigest()
        if mapping.get("raw_note_sha256") != raw_digest:
            raise InputStageError(f"{context} path /raw_note_sha256: raw sidecar fingerprint mismatch")
        source_note = snapshot.selected_notes[index - 1]
        cards = raw.get("cards")
        if not isinstance(cards, list) or not cards:
            raise InputStageError(f"{context} path /cards: selected raw card relationships are missing")
        expected_card_ids = [card.get("id") for card in cards]
        expected_ordinals = [card.get("ord") for card in cards]
        expected_deck_ids = sorted({card.get("did") for card in cards})
        if mapping.get("card_ids") != expected_card_ids:
            raise InputStageError(f"{context} path /card_ids: card identities differ from raw rows")
        if mapping.get("card_ordinals") != expected_ordinals:
            raise InputStageError(f"{context} path /card_ordinals: card ordinals differ from raw rows")
        if mapping.get("deck_ids") != expected_deck_ids:
            raise InputStageError(f"{context} path /deck_ids: deck relationships differ from raw rows")
        if TARGET_DECK_ID not in expected_deck_ids:
            raise InputStageError(f"{context} path /deck_ids: selected note has no target deck relationship")
        expected_raw = {
            "contract_version": MAPPING_VERSION,
            "source_sha256": SOURCE_SHA256,
            "source_database": DATABASE_MEMBER,
            "selection_position": index,
            "native_note": source_note,
            "field_signature": list(FIELD_SIGNATURE),
            "fields_original": source_fields(source_note, FIELD_SIGNATURE),
            "field_count": len(FIELD_SIGNATURE),
            "cards": list(snapshot.selected_cards[native_id]),
        }
        if raw != expected_raw:
            raise InputStageError(f"{context} path /native_note: raw sidecar differs from the original APKG snapshot")
        expected_map = {
            "project_id": project_id,
            "source_apkg": str(source.apkg.resolve()),
            "source_sha256": SOURCE_SHA256,
            "database_member": DATABASE_MEMBER,
            "selection_position": index,
            "native_note_id": native_id,
            "native_guid": source_note["guid"],
            "note_type_id": SUPPORTED_NOTE_TYPE_ID,
            "card_ids": [int(card["id"]) for card in snapshot.selected_cards[native_id]],
            "card_ordinals": [int(card["ord"]) for card in snapshot.selected_cards[native_id]],
            "deck_ids": sorted({int(card["did"]) for card in snapshot.selected_cards[native_id]}),
            "adapter": ADAPTER_ID,
            "mapping_contract": str(source.mapping_contract.resolve()),
            "mapping_contract_version": MAPPING_VERSION,
            "mapping_contract_sha256": MAPPING_SHA256,
            "raw_note_sha256": raw_digest,
        }
        comparable_map = dict(mapping)
        for field, expected_path in (("source_apkg", source.apkg), ("mapping_contract", source.mapping_contract)):
            try:
                actual_path = resolve_reference(config.normalization.source_map, mapping[field])
            except (OSError, RuntimeError, ValueError) as exc:
                raise InputStageError(f"{context} path /{field}: invalid declaring-file-relative path: {exc}") from exc
            if actual_path != expected_path.resolve():
                raise InputStageError(f"{context} path /{field}: source-map path does not bind the configured artifact")
            comparable_map[field] = str(expected_path.resolve())
        if comparable_map != expected_map:
            raise InputStageError(f"{context} path $: source-map identity/relationship fields differ from the APKG")
        try:
            expected_projection = project_note(native_note, FIELD_SIGNATURE).values
        except (KeyError, TypeError, ValueError) as exc:
            raise InputStageError(f"{context} path /native_note/flds: source projection cannot be verified: {exc}") from exc
        if record != expected_projection:
            differing = next((key for key in expected_projection if record.get(key) != expected_projection[key]), "$")
            raise InputStageError(f"{context} path /{differing}: normalized value does not match original source text")


def configured_native_ids(config: StageConfig) -> tuple[int, ...]:
    """Giải mã danh tính native từ binding project-ID đã định kiểu và có thứ tự."""
    project_ids = config.constraints.input_ids
    if project_ids is None or not project_ids:
        raise MappingFailure("unsupported_selection", "constraints.input_ids must bind a nonempty ordered Tango selection")
    prefix = re.escape(PROJECT_ID_PREFIX)
    native_ids: list[int] = []
    for project_id in project_ids:
        match = re.fullmatch(prefix + r"([1-9][0-9]*)", project_id)
        if match is None:
            raise MappingFailure("unsupported_selection", "constraints.input_ids must use canonical Tango native-ID lineage")
        native_ids.append(int(match.group(1)))
    if len(set(native_ids)) != len(native_ids):
        raise MappingFailure("unsupported_selection", "constraints.input_ids must identify distinct native notes")
    if native_ids != sorted(native_ids):
        raise MappingFailure("unsupported_selection", "constraints.input_ids must be in ascending canonical native-ID order")
    return tuple(native_ids)


def validate_snapshot(config: StageConfig, snapshot: SourceSnapshot) -> tuple[str, ...]:
    """Enforce this mapping contract's actual note-type and frozen selection applicability."""
    source = validate_profile_config(config)
    supported = snapshot.note_types.get(SUPPORTED_NOTE_TYPE_ID)
    if supported is None or supported[1] != FIELD_SIGNATURE:
        raise MappingFailure("unsupported_field_signature", "main collection field signature differs from Tango contract")
    native_ids = tuple(int(note["id"]) for note in snapshot.selected_notes)
    expected_native_ids = configured_native_ids(config)
    project_ids = tuple(f"{PROJECT_ID_PREFIX}{native_id}" for native_id in native_ids)
    if native_ids != expected_native_ids or project_ids != config.constraints.input_ids:
        raise MappingFailure("unsupported_selection", "selected native notes differ from configured ordered Tango identities")
    return project_ids


def raw_note(snapshot: SourceSnapshot, note: dict[str, Any], position: int) -> dict[str, Any]:
    signature = snapshot.note_types[int(note["mid"])][1]
    fields = source_fields(note, signature)
    return {
        "contract_version": MAPPING_VERSION,
        "source_sha256": snapshot.sha256,
        "source_database": snapshot.database_member,
        "selection_position": position,
        "native_note": note,
        "field_signature": list(signature),
        "fields_original": fields,
        "field_count": len(signature),
        "cards": list(snapshot.selected_cards[int(note["id"])]),
    }


def source_map(config: StageConfig, snapshot: SourceSnapshot, note: dict[str, Any], raw: dict[str, Any], position: int) -> dict[str, Any]:
    native_id = int(note["id"])
    cards = list(snapshot.selected_cards[native_id])
    return {
        "project_id": f"{PROJECT_ID_PREFIX}{native_id}",
        "source_apkg": relative_reference(config.normalization.source_map, snapshot.path),
        "source_sha256": snapshot.sha256,
        "database_member": snapshot.database_member,
        "selection_position": position,
        "native_note_id": native_id,
        "native_guid": note["guid"],
        "note_type_id": int(note["mid"]),
        "card_ids": [int(card["id"]) for card in cards],
        "card_ordinals": [int(card["ord"]) for card in cards],
        "deck_ids": sorted({int(card["did"]) for card in cards}),
        "adapter": ADAPTER_ID,
        "mapping_contract": relative_reference(config.normalization.source_map, config.source.mapping_contract) if config.source else None,
        "mapping_contract_version": MAPPING_VERSION,
        "mapping_contract_sha256": MAPPING_SHA256,
        "raw_note_sha256": hashlib.sha256(_canonical_json(raw)).hexdigest(),
    }


def exception_for(note: dict[str, Any], signature: tuple[str, ...], exc: MappingFailure, *, selected: bool) -> dict[str, Any]:
    native_id = int(note["id"])
    try:
        original_fields: Any = source_fields(note, signature)
    except (MappingFailure, KeyError, TypeError, ValueError):
        original_fields = {"raw_flds": note.get("flds")}
    return {
        "native_note_id": native_id,
        "project_id": f"{PROJECT_ID_PREFIX}{native_id}" if int(note["mid"]) == SUPPORTED_NOTE_TYPE_ID else None,
        "note_type_id": int(note["mid"]),
        "selection_status": "selected" if selected else "unselected",
        "reason_code": exc.reason_code,
        "message": str(exc),
        "original_fields": original_fields,
    }




def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _sidecar_error(record_id: str, path: str, message: str, *, file: str) -> InputStageError:
    return InputStageError(
        f"source linkage {record_id} path {path}: {message}", record_id=record_id, file=file, path=path
    )


def _require_sidecar_object(value: Any, *, record_id: str, path: str, file: str) -> dict[str, Any]:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise _sidecar_error(record_id, path, "must be an object with string keys", file=file)
    return value


def _require_sidecar_string(value: Any, *, record_id: str, path: str, file: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise _sidecar_error(record_id, path, "must be a non-blank string", file=file)


def _require_sidecar_text(value: Any, *, record_id: str, path: str, file: str) -> None:
    if not isinstance(value, str):
        raise _sidecar_error(record_id, path, "must be a string", file=file)


def _require_sidecar_integer(
    value: Any, *, record_id: str, path: str, file: str, minimum: int | None = None
) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or (minimum is not None and value < minimum):
        suffix = f" >= {minimum}" if minimum is not None else ""
        raise _sidecar_error(record_id, path, f"must be an integer{suffix}", file=file)


def _require_sidecar_list(
    value: Any, *, record_id: str, path: str, file: str, nonempty: bool = False
) -> list[Any]:
    if not isinstance(value, list) or (nonempty and not value):
        requirement = "a nonempty list" if nonempty else "a list"
        raise _sidecar_error(record_id, path, f"must be {requirement}", file=file)
    return value


def _validate_sidecar_shapes(
    records: list[dict[str, Any]],
    source_map: list[dict[str, Any]],
    raw_notes: list[dict[str, Any]],
    *,
    source_map_file: str,
    raw_notes_file: str,
) -> None:
    if len(source_map) != len(records):
        raise InputStageError(
            "source linkage path $: source-map and raw-note counts must equal the normalized input count",
            file=source_map_file,
        )
    if len(raw_notes) != len(records):
        raise InputStageError(
            "source linkage path $: source-map and raw-note counts must equal the normalized input count",
            file=raw_notes_file,
        )
    map_string_fields = (
        "project_id", "source_apkg", "source_sha256", "database_member", "native_guid", "adapter",
        "mapping_contract", "mapping_contract_version", "mapping_contract_sha256", "raw_note_sha256",
    )
    map_integer_fields = {"selection_position": 1, "native_note_id": 1, "note_type_id": 1}
    map_list_fields = {"card_ids": 1, "card_ordinals": 0, "deck_ids": 1}
    for index, (record, mapping_value, raw_value) in enumerate(zip(records, source_map, raw_notes, strict=True)):
        record_id = str(record.get("id", f"line-{index + 1}"))
        mapping = _require_sidecar_object(
            mapping_value, record_id=record_id, path=f"/source_map/{index}", file=source_map_file
        )
        raw = _require_sidecar_object(
            raw_value, record_id=record_id, path=f"/raw_notes/{index}", file=raw_notes_file
        )
        for name in map_string_fields:
            _require_sidecar_string(
                mapping.get(name), record_id=record_id, path=f"/source_map/{index}/{name}", file=source_map_file
            )
        for name, minimum in map_integer_fields.items():
            _require_sidecar_integer(
                mapping.get(name), record_id=record_id, path=f"/source_map/{index}/{name}",
                file=source_map_file, minimum=minimum,
            )
        for name, minimum in map_list_fields.items():
            values = _require_sidecar_list(
                mapping.get(name), record_id=record_id, path=f"/source_map/{index}/{name}",
                file=source_map_file, nonempty=True,
            )
            for child_index, value in enumerate(values):
                _require_sidecar_integer(
                    value, record_id=record_id, path=f"/source_map/{index}/{name}/{child_index}",
                    file=source_map_file, minimum=minimum,
                )

        for name in ("contract_version", "source_sha256", "source_database"):
            _require_sidecar_string(
                raw.get(name), record_id=record_id, path=f"/raw_notes/{index}/{name}", file=raw_notes_file
            )
        _require_sidecar_integer(
            raw.get("selection_position"), record_id=record_id, path=f"/raw_notes/{index}/selection_position",
            file=raw_notes_file, minimum=1,
        )
        _require_sidecar_integer(
            raw.get("field_count"), record_id=record_id, path=f"/raw_notes/{index}/field_count",
            file=raw_notes_file, minimum=1,
        )
        native_note = _require_sidecar_object(
            raw.get("native_note"), record_id=record_id, path=f"/raw_notes/{index}/native_note",
            file=raw_notes_file,
        )
        note_integer_fields = {"id", "mid", "mod", "usn", "csum", "flags"}
        note_string_fields = set(NOTE_COLUMNS) - note_integer_fields - {"sfld"}
        sort_field = native_note.get("sfld")
        if isinstance(sort_field, bool) or not isinstance(sort_field, (int, str)):
            raise _sidecar_error(record_id, f"/raw_notes/{index}/native_note/sfld", "must preserve its SQLite integer or text value", file=raw_notes_file)
        for name in note_integer_fields:
            _require_sidecar_integer(
                native_note.get(name), record_id=record_id, path=f"/raw_notes/{index}/native_note/{name}",
                file=raw_notes_file,
            )
        for name in note_string_fields:
            require_string = _require_sidecar_string if name == "guid" else _require_sidecar_text
            require_string(
                native_note.get(name), record_id=record_id, path=f"/raw_notes/{index}/native_note/{name}",
                file=raw_notes_file,
            )
        signature = _require_sidecar_list(
            raw.get("field_signature"), record_id=record_id, path=f"/raw_notes/{index}/field_signature",
            file=raw_notes_file, nonempty=True,
        )
        for child_index, value in enumerate(signature):
            _require_sidecar_string(
                value, record_id=record_id, path=f"/raw_notes/{index}/field_signature/{child_index}",
                file=raw_notes_file,
            )
        original_fields = _require_sidecar_object(
            raw.get("fields_original"), record_id=record_id, path=f"/raw_notes/{index}/fields_original",
            file=raw_notes_file,
        )
        for name, value in original_fields.items():
            _require_sidecar_string(
                name, record_id=record_id, path=f"/raw_notes/{index}/fields_original/{name}",
                file=raw_notes_file,
            )
            _require_sidecar_text(
                value, record_id=record_id, path=f"/raw_notes/{index}/fields_original/{name}",
                file=raw_notes_file,
            )
        cards = _require_sidecar_list(
            raw.get("cards"), record_id=record_id, path=f"/raw_notes/{index}/cards",
            file=raw_notes_file, nonempty=True,
        )
        card_integer_fields = set(CARD_COLUMNS) - {"data"}
        for card_index, card_value in enumerate(cards):
            card_path = f"/raw_notes/{index}/cards/{card_index}"
            card = _require_sidecar_object(
                card_value, record_id=record_id, path=card_path, file=raw_notes_file
            )
            for name in card_integer_fields:
                _require_sidecar_integer(
                    card.get(name), record_id=record_id, path=f"{card_path}/{name}", file=raw_notes_file
                )
            _require_sidecar_text(
                card.get("data"), record_id=record_id, path=f"{card_path}/data", file=raw_notes_file
            )


