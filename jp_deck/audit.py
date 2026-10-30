"""Read-only APKG and learner-render audit helpers."""

from __future__ import annotations

import html.parser
import json
import sqlite3
import tempfile
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .render import RenderedRecord
from .validation import resolve_json_pointer


class AuditError(RuntimeError):
    pass


class _HTMLAuditParser(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.text_parts: list[str] = []
        self.hrefs: list[str] = []
        self.sense_text_parts: list[list[str]] = []
        self._section_stack: list[bool] = []
        self.articles: list[dict[str, Any]] = []
        self._article_stack: list[dict[str, Any]] = []
        self.claims: list[dict[str, Any]] = []
        self._claim_stack: list[dict[str, Any]] = []
        self._div_stack: list[bool] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "a" and attributes.get("href") is not None:
            href = attributes["href"] or ""
            self.hrefs.append(href)
            if self._article_stack:
                self._article_stack[-1]["hrefs"].append(href)
            if self._claim_stack:
                self._claim_stack[-1]["hrefs"].append(href)
        if tag == "article":
            article = {"classes": (attributes.get("class") or "").split(), "text": [], "hrefs": []}
            self.articles.append(article)
            self._article_stack.append(article)
        if tag == "div":
            is_claim = "claim" in (attributes.get("class") or "").split()
            self._div_stack.append(is_claim)
            if is_claim:
                claim = {"text": [], "hrefs": []}
                self.claims.append(claim)
                self._claim_stack.append(claim)
        if tag == "section":
            is_sense = "sense" in (attributes.get("class") or "").split()
            self._section_stack.append(is_sense)
            if is_sense:
                self.sense_text_parts.append([])

    def handle_endtag(self, tag: str) -> None:
        if tag == "article" and self._article_stack:
            self._article_stack.pop()
        if tag == "div" and self._div_stack:
            if self._div_stack.pop() and self._claim_stack:
                self._claim_stack.pop()
        if tag == "section" and self._section_stack:
            self._section_stack.pop()

    def handle_data(self, data: str) -> None:
        self.text_parts.append(data)
        if any(self._section_stack):
            self.sense_text_parts[-1].append(data)
        if self._article_stack:
            self._article_stack[-1]["text"].append(data)
        if self._claim_stack:
            self._claim_stack[-1]["text"].append(data)


def _normalize_text(value: str) -> str:
    return " ".join(value.split())


def visible_text(source: str) -> str:
    parser = _HTMLAuditParser()
    parser.feed(source)
    parser.close()
    return _normalize_text("".join(parser.text_parts))



def _all_source_ids(record: dict[str, Any]) -> set[str]:
    found: set[str] = set()

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if key == "evidence_refs":
                    found.update(ref["source_id"] for ref in item)
                elif key == "origin_source_ids":
                    found.update(item)
                else:
                    walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(record)
    return found


def _expected_visible_fields(record: dict[str, Any]) -> list[tuple[str, str]]:
    values: list[tuple[str, str]] = []
    values.extend((
        ("/headword/expression", record["headword"]["expression"]),
        ("/headword/reading", record["headword"]["reading"]),
    ))
    values.extend((f"/headword/pos/{i}", value) for i, value in enumerate(record["headword"]["pos"]))
    origin_labels = {"quoted": "Trích dẫn", "adapted": "Phỏng theo", "generated": "Tự biên soạn"}
    relationship_labels = {"synonym": "Đồng nghĩa", "near_synonym": "Gần nghĩa", "related": "Có liên quan"}
    for collection in ("senses", "examples", "collocations", "related_terms", "confusables"):
        for index, item in enumerate(record[collection]):
            base = f"/{collection}/{index}"
            keys = {
                "senses": ("meaning_vi", "explanation_vi"),
                "examples": ("sentence_ja", "reading", "translation_vi"),
                "collocations": ("expression", "reading", "meaning_vi", "usage_vi"),
                "related_terms": ("expression", "reading", "note_vi"),
                "confusables": ("expression", "reading", "distinction_vi"),
            }[collection]
            values.extend((f"{base}/{key}", item[key]) for key in keys)
            if collection == "examples":
                values.append((f"{base}/origin", origin_labels[item["origin"]]))
            elif collection == "related_terms":
                values.append((f"{base}/relationship", relationship_labels[item["relationship"]]))
            elif collection == "collocations" and item["frequency"] is None:
                values.append((f"{base}/frequency", "Tần suất corpus: chưa có số đo."))
            elif collection == "confusables":
                for contrast_index, contrast in enumerate(item["contrast_examples"]):
                    contrast_base = f"{base}/contrast_examples/{contrast_index}"
                    for key in ("sentence_ja", "reading", "translation_vi"):
                        values.append((f"{contrast_base}/{key}", contrast[key]))
                    values.append((f"{contrast_base}/origin", origin_labels[contrast["origin"]]))
    sources = {source["source_id"]: source for source in record["sources"]}
    for source_id in sorted(_all_source_ids(record)):
        source = sources[source_id]
        if source["attribution"] is not None:
            values.append((f"/sources/{source_id}/attribution", source["attribution"]))
        elif source["underlying_source"] is not None:
            values.append((f"/sources/{source_id}/underlying_source", source["underlying_source"]))
        if source["license"] is not None:
            values.append((f"/sources/{source_id}/license", source["license"]))
    return values


def _expected_link_urls(record: dict[str, Any]) -> list[str]:
    sources = {source["source_id"]: source for source in record["sources"]}
    expected: list[str] = []

    def add(source_ids: list[str]) -> None:
        seen: set[str] = set()
        for source_id in source_ids:
            if source_id not in seen:
                expected.append(sources[source_id]["url"])
                seen.add(source_id)

    add([ref["source_id"] for ref in record["headword"]["evidence_refs"]])
    for sense in record["senses"]:
        add([ref["source_id"] for ref in sense["evidence_refs"]])
    for item in record["examples"]:
        add(item["origin_source_ids"])
        add([ref["source_id"] for ref in item["evidence_refs"]])
    for item in record["collocations"]:
        add([ref["source_id"] for ref in item["evidence_refs"]])
    for item in record["related_terms"]:
        add([ref["source_id"] for ref in item["evidence_refs"]])
    for item in record["confusables"]:
        add([ref["source_id"] for ref in item["evidence_refs"]])
        for contrast in item["contrast_examples"]:
            add(contrast["origin_source_ids"])
            add([ref["source_id"] for ref in contrast["evidence_refs"]])
    return expected


def _urls_for_source_groups(source_id_groups: list[list[str]], sources: dict[str, dict[str, Any]]) -> list[str]:
    urls: list[str] = []
    for source_ids in source_id_groups:
        seen: set[str] = set()
        for source_id in source_ids:
            if source_id not in seen:
                urls.append(sources[source_id]["url"])
                seen.add(source_id)
    return urls


def _item_scope(item: dict[str, Any], collection: str) -> tuple[str, list[str], list[list[str]]]:
    origin_labels = {"quoted": "Trích dẫn", "adapted": "Phỏng theo", "generated": "Tự biên soạn"}
    relationship_labels = {"synonym": "Đồng nghĩa", "near_synonym": "Gần nghĩa", "related": "Có liên quan"}
    evidence = [ref["source_id"] for ref in item["evidence_refs"]]
    if collection == "examples":
        return "example", [item["sentence_ja"], item["reading"], item["translation_vi"], origin_labels[item["origin"]]], [item["origin_source_ids"], evidence]
    if collection == "collocations":
        return "collocation", [item["expression"], item["reading"], item["meaning_vi"], item["usage_vi"]], [evidence]
    if collection == "related_terms":
        return "related-term", [item["expression"], item["reading"], relationship_labels[item["relationship"]], item["note_vi"]], [evidence]
    required = [item["expression"], item["reading"], item["distinction_vi"]]
    source_groups = [evidence]
    for contrast in item["contrast_examples"]:
        required.extend([contrast["sentence_ja"], contrast["reading"], contrast["translation_vi"], origin_labels[contrast["origin"]]])
        source_groups.extend([contrast["origin_source_ids"], [ref["source_id"] for ref in contrast["evidence_refs"]]])
    return "confusable", required, source_groups


def _all_internal_ids(record: dict[str, Any]) -> set[str]:
    internal = {record["input_id"]}
    for collection, key in (
        ("senses", "sense_id"),
        ("examples", "example_id"),
        ("collocations", "collocation_id"),
        ("related_terms", "relation_id"),
        ("confusables", "confusable_id"),
        ("sources", "source_id"),
    ):
        internal.update(item[key] for item in record[collection])
    internal.update(ref["claim_path"] for ref in _iter_evidence_refs(record))
    return {value for value in internal if value}


def _iter_evidence_refs(value: Any):
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "evidence_refs" and isinstance(item, list):
                yield from item
            else:
                yield from _iter_evidence_refs(item)
    elif isinstance(value, list):
        for item in value:
            yield from _iter_evidence_refs(item)


def audit_rendered_record(record: dict[str, Any], rendered: RenderedRecord) -> dict[str, Any]:
    back = visible_text(rendered.back_html)
    for index, item in enumerate(record["uncertainties"]):
        if _normalize_text(item["issue_vi"]) in back:
            raise AuditError(
                f"record {record['input_id']} path /uncertainties/{index}/issue_vi: "
                "diagnostic issue text must not appear in learner content"
            )
    for path, value in _expected_visible_fields(record):
        if _normalize_text(value) not in back:
            raise AuditError(f"record {record['input_id']} path {path}: expected learner content missing from rendered back")

    parser = _HTMLAuditParser()
    parser.feed(rendered.back_html)
    parser.close()
    sources = {source["source_id"]: source for source in record["sources"]}
    headword_parser = _HTMLAuditParser()
    headword_parser.feed(rendered.headword_html)
    headword_parser.close()
    headword_urls = _urls_for_source_groups(
        [[ref["source_id"] for ref in record["headword"]["evidence_refs"]]], sources
    )
    if Counter(headword_parser.hrefs) != Counter(headword_urls):
        raise AuditError(f"record {record['input_id']} path /headword/evidence_refs: links are out of scope")
    if Counter(parser.hrefs) != Counter(_expected_link_urls(record)):
        raise AuditError(
            f"record {record['input_id']} path /sources: rendered hyperlinks do not exactly match scoped evidence/origin refs"
        )
    expected_claims: dict[str, list[str]] = defaultdict(list)
    for ref in _iter_evidence_refs(record):
        expected_claims[ref["claim_path"]].append(ref["source_id"])
    remaining_claims = list(parser.claims)
    for claim_path, source_ids in expected_claims.items():
        target = resolve_json_pointer(record, claim_path, context=f"record {record['input_id']} claim audit")
        if not isinstance(target, str):
            raise AuditError(f"record {record['input_id']} path {claim_path}: evidence target is not a rendered string")
        if claim_path.endswith("/origin"):
            target = {"quoted": "Trích dẫn", "adapted": "Phỏng theo", "generated": "Tự biên soạn"}[target]
        elif claim_path.endswith("/relationship"):
            target = {"synonym": "Đồng nghĩa", "near_synonym": "Gần nghĩa", "related": "Có liên quan"}[target]
        expected_urls = _urls_for_source_groups([source_ids], sources)
        match_index = next((index for index, claim in enumerate(remaining_claims)
                            if _normalize_text(target) in _normalize_text("".join(claim["text"]))
                            and Counter(claim["hrefs"]) == Counter(expected_urls)), None)
        if match_index is None:
            raise AuditError(f"record {record['input_id']} path {claim_path}: evidence link is not attached to its exact claim")
        remaining_claims.pop(match_index)
    if remaining_claims:
        raise AuditError(f"record {record['input_id']} path /evidence_refs: unexpected claim citation markup")

    if len(rendered.sense_sections) != len(record["senses"]):
        raise AuditError(f"record {record['input_id']} path /senses: rendered sense section count mismatch")
    grouped_counts: dict[str, dict[str, int]] = {}
    for sense in record["senses"]:
        sense_id = sense["sense_id"]
        section_html = rendered.sense_sections[sense_id]
        section_text = visible_text(section_html)
        for field in ("meaning_vi", "explanation_vi"):
            if _normalize_text(sense[field]) not in section_text:
                raise AuditError(
                    f"record {record['input_id']} path /senses/{sense_id}/{field}: "
                    "sense text is missing from its own rendered section"
                )
        section_parser = _HTMLAuditParser()
        section_parser.feed(section_html)
        section_parser.close()
        source_groups = [[ref["source_id"] for ref in sense["evidence_refs"]]]
        for collection in ("examples", "collocations", "related_terms", "confusables"):
            for item in record[collection]:
                if item["sense_id"] == sense_id:
                    _, _, item_groups = _item_scope(item, collection)
                    source_groups.extend(item_groups)
        if Counter(section_parser.hrefs) != Counter(_urls_for_source_groups(source_groups, sources)):
            raise AuditError(f"record {record['input_id']} path /senses/{sense_id}: source links crossed sense scope")
        grouped_counts[sense_id] = {}
        for collection in ("examples", "collocations", "related_terms", "confusables"):
            items = [item for item in record[collection] if item["sense_id"] == sense_id]
            grouped_counts[sense_id][collection] = len(items)
            for item in items:
                key = {"examples": "sentence_ja", "collocations": "expression",
                       "related_terms": "expression", "confusables": "expression"}[collection]
                if _normalize_text(item[key]) not in section_text:
                    raise AuditError(f"record {record['input_id']} path /{collection}: item is not under its linked sense")

    available_articles = list(parser.articles)
    for collection in ("examples", "collocations", "related_terms", "confusables"):
        for item in record[collection]:
            class_name, required_values, source_groups = _item_scope(item, collection)
            expected_urls = _urls_for_source_groups(source_groups, sources)
            match_index = next((index for index, article in enumerate(available_articles)
                                if class_name in article["classes"]
                                and all(_normalize_text(value) in _normalize_text("".join(article["text"]))
                                        for value in required_values)
                                and Counter(article["hrefs"]) == Counter(expected_urls)), None)
            if match_index is None:
                raise AuditError(
                    f"record {record['input_id']} path /{collection}: learning text or source links are paired with the wrong item"
                )
            available_articles.pop(match_index)

    leaked = sorted(token for token in _all_internal_ids(record) if token in rendered.back_html)
    if leaked:
        raise AuditError(f"record {record['input_id']} path /BackContent: internal metadata leaked: {leaked[0]!r}")

    return {
        "input_id": record["input_id"],
        "front": {"expression": rendered.expression, "collocation": rendered.front_collocation},
        "learning_content_strings_checked": len(_expected_visible_fields(record)),
        "sense_grouping": grouped_counts,
        "rendered_link_count": len(parser.hrefs),
        "source_links_scope_checked": True,
        "internal_metadata_leak_check": "passed",
        "diagnostic_issue_text_absence_checked": True,
        "empty_collections": [name for name in ("confusables",) if not record[name]],
    }


def _stable_guid(guid_namespace: str, input_id: str) -> str:
    from genanki import guid_for

    return guid_for(guid_namespace, input_id)


def audit_apkg(
    apkg_path: Path,
    records: list[dict[str, Any]],
    rendered: list[RenderedRecord],
    *,
    guid_namespace: str,
    model_id: int,
    deck_id: int,
    deck_name: str,
    model_name: str,
    field_names: list[str],
    template_front: str,
    template_back: str,
) -> dict[str, Any]:
    try:
        archive = zipfile.ZipFile(apkg_path, "r")
    except (OSError, zipfile.BadZipFile) as exc:
        raise AuditError(f"APKG is not a readable ZIP package: {exc}") from exc
    with archive:
        bad_member = archive.testzip()
        if bad_member is not None:
            raise AuditError(f"APKG member {bad_member!r} failed ZIP CRC validation")
        names = archive.namelist()
        if names.count("collection.anki2") != 1 or names.count("media") != 1:
            raise AuditError(f"Unexpected genanki archive members: {names!r}")
        media_map = json.loads(archive.read("media"))
        if media_map != {} or len(names) != 2:
            raise AuditError(f"Expected no media; got map {media_map!r} and members {names!r}")
        database = archive.read("collection.anki2")

    with tempfile.TemporaryDirectory(prefix="jp-deck-apkg-audit-") as directory:
        db_path = Path(directory) / "collection.anki2"
        db_path.write_bytes(database)
        conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        try:
            integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
            if integrity != "ok":
                raise AuditError(f"collection.anki2 integrity_check: {integrity}")
            notes = conn.execute("SELECT id, guid, mid, flds FROM notes ORDER BY id").fetchall()
            cards = conn.execute("SELECT id, nid, did, ord FROM cards ORDER BY id").fetchall()
            revlog_count = conn.execute("SELECT count(*) FROM revlog").fetchone()[0]
            models_json, decks_json = conn.execute("SELECT models, decks FROM col").fetchone()
            models = json.loads(models_json)
            decks = json.loads(decks_json)
            note_models = {int(row["mid"]) for row in notes}
            card_decks = {int(row["did"]) for row in cards}
            if len(notes) != len(records):
                raise AuditError(f"Expected {len(records)} notes; got {len(notes)}")
            if note_models != {model_id} or len(models) != 1:
                raise AuditError(f"Expected one stable note type {model_id}; got {note_models}, models {list(models)}")
            if card_decks != {deck_id}:
                raise AuditError(f"Cards do not all belong to the expected deck {deck_id}: {card_decks}")
            if len(decks) != 2 or str(deck_id) not in decks:
                raise AuditError(f"Unexpected genanki deck metadata: {list(decks)}")
            if decks[str(deck_id)]["name"] != deck_name:
                raise AuditError("Stored deck name mismatch")
            # genanki 0.13.1 seeds a newly created collection with an empty Default deck (id 1).
            default_stub = decks.get("1")
            if default_stub is None or default_stub["name"] != "Default" or 1 in card_decks:
                raise AuditError("Expected genanki's empty Default collection stub beside the one populated MVP deck")

            model = models[str(model_id)]
            actual_fields = [field["name"] for field in sorted(model["flds"], key=lambda item: item["ord"])]
            templates = sorted(model["tmpls"], key=lambda item: item["ord"])
            if actual_fields != field_names:
                raise AuditError(f"Model field order mismatch: expected {field_names!r}, got {actual_fields!r}")
            if len(templates) != 1:
                raise AuditError(f"Expected exactly one card template; got {len(templates)}")
            if len(cards) != len(notes) * len(templates):
                raise AuditError(
                    f"Expected {len(notes) * len(templates)} cards for {len(notes)} notes and {len(templates)} template; got {len(cards)}"
                )
            if templates[0]["qfmt"] != template_front or templates[0]["afmt"] != template_back:
                raise AuditError("Stored Anki template does not match approved front/back renderer")
            if int(model["id"]) != model_id or model["name"] != model_name:
                raise AuditError("Stored note type identity mismatch")
            if revlog_count != 0:
                raise AuditError(f"Expected no review history; found {revlog_count} revlog rows")

            expected_by_guid = {
                _stable_guid(guid_namespace, record["input_id"]): (record, index)
                for index, record in enumerate(records)
            }
            if len(expected_by_guid) != len(records):
                raise AuditError("Expected stable GUID identities are not unique")
            guid_by_note: dict[int, str] = {}
            note_id_by_guid: dict[str, int] = {}
            matched_input_ids: set[str] = set()
            for row in notes:
                if row["guid"] in note_id_by_guid:
                    raise AuditError(f"Duplicate note GUID {row['guid']!r}")
                note_id_by_guid[row["guid"]] = int(row["id"])
                guid_by_note[int(row["id"])] = row["guid"]
                match = expected_by_guid.get(row["guid"])
                if match is None:
                    raise AuditError(f"Note {row['id']} has foreign GUID identity {row['guid']!r}")
                record, index = match
                if record["input_id"] in matched_input_ids:
                    raise AuditError(f"Duplicate package identity for input {record['input_id']}")
                matched_input_ids.add(record["input_id"])
                values = row["flds"].split("\x1f")
                if len(values) != len(field_names):
                    raise AuditError(f"Note {row['id']} has {len(values)} fields, expected {len(field_names)}")
                if values != rendered[index].anki_fields:
                    raise AuditError(f"Note {record['input_id']} path /fields: packaged values differ from projection")
                if row["guid"] != _stable_guid(guid_namespace, record["input_id"]):
                    raise AuditError(f"Note {record['input_id']} has unstable or incorrect GUID")
            expected_guids = set(expected_by_guid)
            if set(note_id_by_guid) != expected_guids or len(matched_input_ids) != len(records):
                raise AuditError("Packaged note GUID set does not match stable input-ID namespace")

            card_ids: set[int] = set()
            for card in cards:
                if int(card["nid"]) not in guid_by_note or int(card["did"]) != deck_id or int(card["ord"]) != 0:
                    raise AuditError(f"Card {card['id']} has invalid note/deck/template association")
                card_ids.add(int(card["id"]))
            if len(card_ids) != len(records) or len({int(card["nid"]) for card in cards}) != len(records):
                raise AuditError("Card IDs or note associations are not one-to-one")
        finally:
            conn.close()

    render_audits = [audit_rendered_record(record, item) for record, item in zip(records, rendered, strict=True)]
    return {
        "package_members": names,
        "media_map": media_map,
        "notes": len(notes),
        "cards": len(cards),
        "populated_decks": 1,
        "deck_metadata_entries": len(decks),
        "empty_genanki_default_deck_stub": True,
        "note_types": len(models),
        "templates": len(templates),
        "model_id": model_id,
        "deck_id": deck_id,
        "note_guids_stable": True,
        "native_note_and_card_ids_stable": False,
        "ordered_fields": field_names,
        "revlog_rows": revlog_count,
        "html_audits": render_audits,
    }


def snapshot_package_identity(apkg_path: Path) -> dict[str, Any]:
    """Return only structural identity tuples, opening the bundled collection read-only."""
    with zipfile.ZipFile(apkg_path, "r") as archive:
        database = archive.read("collection.anki2")
    with tempfile.TemporaryDirectory(prefix="jp-deck-identity-audit-") as directory:
        db_path = Path(directory) / "collection.anki2"
        db_path.write_bytes(database)
        conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
        try:
            notes = conn.execute("SELECT id, guid, mid FROM notes ORDER BY guid").fetchall()
            cards = conn.execute("SELECT id, nid, did, ord FROM cards ORDER BY id").fetchall()
            models_json, decks_json = conn.execute("SELECT models, decks FROM col").fetchone()
            models, decks = json.loads(models_json), json.loads(decks_json)
            return {
                "models": sorted((str(key), int(value["id"])) for key, value in models.items()),
                "decks": sorted((str(key), int(value["id"])) for key, value in decks.items()),
                "notes": sorted((int(row[0]), str(row[1]), int(row[2])) for row in notes),
                "cards": sorted((int(row[0]), int(row[1]), int(row[2]), int(row[3])) for row in cards),
            }
        finally:
            conn.close()
