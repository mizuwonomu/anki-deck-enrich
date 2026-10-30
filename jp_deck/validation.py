"""Strict validation for the frozen APKG M1 JSONL input."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from .config import DatasetConstraints

ANKI_FIELD_SEPARATOR = "\x1f"


class ValidationError(ValueError):
    """Input error with a stable, actionable file/record/path diagnostic."""

    def __init__(
        self,
        message: str,
        *,
        record_id: str | None = None,
        file: str | None = None,
        path: str | None = None,
    ):
        super().__init__(message)
        self.record_id = record_id
        self.file = file
        self.path = path


class InputStageError(ValidationError):
    """Controlled input-stage failure with structured CLI context."""

    def __init__(self, message: str, *, record_id: str | None = None, file: str | None = None, path: str | None = None):
        super().__init__(message, record_id=record_id, file=file, path=path)


def _pointer(parts: Any) -> str:
    escaped = [str(part).replace("~", "~0").replace("/", "~1") for part in parts]
    return "" if not escaped else "/" + "/".join(escaped)


def _load_json(path: Path, what: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValidationError(f"Cannot read {what} at {path}: {exc}", file=str(path)) from exc
    except UnicodeDecodeError as exc:
        raise ValidationError(f"Invalid UTF-8 in {what} at {path}: {exc}", file=str(path)) from exc
    except json.JSONDecodeError as exc:
        raise ValidationError(
            f"Invalid JSON in {what} at {path}:{exc.lineno}:{exc.colno}: {exc.msg}", file=str(path)
        ) from exc


def read_jsonl(path: Path, what: str) -> tuple[bytes, list[dict[str, Any]]]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ValidationError(f"Cannot read {what} at {path}: {exc}", file=str(path)) from exc
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValidationError(
            f"{what} at {path} is not valid UTF-8 at byte {exc.start}", file=str(path)
        ) from exc

    records: list[dict[str, Any]] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            raise ValidationError(f"{what} line {line_no} path $: blank lines are not allowed", file=str(path))
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValidationError(
                f"{what} line {line_no} path $: invalid JSON at column {exc.colno}: {exc.msg}", file=str(path)
            ) from exc
        if not isinstance(record, dict):
            raise ValidationError(
                f"{what} line {line_no} path $: each JSONL value must be an object", file=str(path)
            )
        records.append(record)
    return raw, records


def _validator(schema: dict[str, Any], schema_path: Path, label: str) -> Draft202012Validator:
    try:
        Draft202012Validator.check_schema(schema)
    except Exception as exc:  # jsonschema exposes multiple schema-error subclasses
        raise ValidationError(f"Invalid {label} schema {schema_path}: {exc}") from exc
    return Draft202012Validator(schema, format_checker=FormatChecker())


def _validate_schema(record: dict[str, Any], validator: Draft202012Validator, label: str, line_no: int) -> None:
    record_id = record.get("input_id", record.get("id", f"line-{line_no}"))
    errors = sorted(validator.iter_errors(record), key=lambda err: (list(map(str, err.absolute_path)), err.message))
    if errors:
        err = errors[0]
        where = _pointer(err.absolute_path) or "/"
        raise ValidationError(f"{label} {record_id!r} path {where}: {err.message}")


def resolve_json_pointer(document: Any, pointer: str, *, context: str) -> Any:
    if pointer == "":
        return document
    if not pointer.startswith("/"):
        raise ValidationError(f"{context} path {pointer!r}: JSON Pointer must be empty or start with '/'")
    current = document
    for raw_token in pointer[1:].split("/"):
        index = 0
        decoded: list[str] = []
        while index < len(raw_token):
            char = raw_token[index]
            if char == "~":
                if index + 1 >= len(raw_token) or raw_token[index + 1] not in "01":
                    raise ValidationError(f"{context} path {pointer!r}: invalid JSON Pointer escape")
                decoded.append("~" if raw_token[index + 1] == "0" else "/")
                index += 2
            else:
                decoded.append(char)
                index += 1
        token = "".join(decoded)
        if isinstance(current, dict) and token in current:
            current = current[token]
        elif (
            isinstance(current, list)
            and token.isdecimal()
            and (token == "0" or not token.startswith("0"))
            and int(token) < len(current)
        ):
            current = current[int(token)]
        else:
            raise ValidationError(f"{context} path {pointer!r}: target does not exist")
    return current


def _walk_strings(value: Any, path: str = ""):
    if isinstance(value, str):
        yield path or "/", value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from _walk_strings(item, f"{path}/{str(key).replace('~', '~0').replace('/', '~1')}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _walk_strings(item, f"{path}/{index}")


def _check_unique_ids(record: dict[str, Any], record_id: str) -> None:
    collections = (
        ("senses", "sense_id"),
        ("examples", "example_id"),
        ("collocations", "collocation_id"),
        ("related_terms", "relation_id"),
        ("confusables", "confusable_id"),
        ("sources", "source_id"),
    )
    for collection, key in collections:
        seen: set[str] = set()
        for index, item in enumerate(record.get(collection, [])):
            value = item[key]
            if value in seen:
                raise ValidationError(f"record {record_id} path /{collection}/{index}/{key}: duplicate ID {value!r}")
            seen.add(value)


def _check_references(record: dict[str, Any], record_id: str) -> None:
    sources = {item["source_id"] for item in record["sources"]}
    sense_ids = {item["sense_id"] for item in record["senses"]}

    def check_refs(obj: Any, path: str) -> None:
        if isinstance(obj, dict):
            refs = obj.get("evidence_refs")
            if isinstance(refs, list):
                for index, ref in enumerate(refs):
                    ref_path = f"{path}/evidence_refs/{index}"
                    source_id = ref["source_id"]
                    if source_id not in sources:
                        raise ValidationError(
                            f"record {record_id} path {ref_path}/source_id: unknown source_id {source_id!r}"
                        )
                    resolve_json_pointer(record, ref["claim_path"], context=f"record {record_id} {ref_path}/claim_path")
            for key, value in obj.items():
                if key == "origin_source_ids" and isinstance(value, list):
                    for index, source_id in enumerate(value):
                        if source_id not in sources:
                            raise ValidationError(
                                f"record {record_id} path {path}/{key}/{index}: unknown source_id {source_id!r}"
                            )
                elif key == "frequency" and isinstance(value, dict):
                    source_id = value["source_id"]
                    if source_id not in sources:
                        raise ValidationError(
                            f"record {record_id} path {path}/{key}/source_id: unknown source_id {source_id!r}"
                        )
                elif isinstance(value, (dict, list)):
                    check_refs(value, f"{path}/{key}")
        elif isinstance(obj, list):
            for index, value in enumerate(obj):
                check_refs(value, f"{path}/{index}")

    check_refs(record, "")
    for collection in ("examples", "collocations", "related_terms", "confusables"):
        for index, item in enumerate(record.get(collection, [])):
            if item["sense_id"] not in sense_ids:
                raise ValidationError(
                    f"record {record_id} path /{collection}/{index}/sense_id: "
                    f"unknown sense_id {item['sense_id']!r}"
                )
            if collection == "confusables":
                for contrast_index, contrast in enumerate(item["contrast_examples"]):
                    path = f"/confusables/{index}/contrast_examples/{contrast_index}"
                    for ref_index, ref in enumerate(contrast["evidence_refs"]):
                        if ref["source_id"] not in sources:
                            raise ValidationError(
                                f"record {record_id} path {path}/evidence_refs/{ref_index}/source_id: "
                                f"unknown source_id {ref['source_id']!r}"
                            )
                        resolve_json_pointer(
                            record,
                            ref["claim_path"],
                            context=f"record {record_id} {path}/evidence_refs/{ref_index}/claim_path",
                        )
    for index, uncertainty in enumerate(record["uncertainties"]):
        resolve_json_pointer(record, uncertainty["path"], context=f"record {record_id} /uncertainties/{index}/path")


def validate_records(
    records: list[dict[str, Any]],
    source_records: list[dict[str, Any]],
    output_schema: dict[str, Any],
    input_schema: dict[str, Any],
    *,
    output_schema_path: Path,
    input_schema_path: Path,
    expected_ids: tuple[str, ...] | None,
    expected_revision: int | None,
    expected_schema_version: str,
    expected_revisions: dict[str, int] | None = None,
) -> None:
    if expected_revision is not None and expected_revisions is not None:
        raise ValidationError("expected_revision and expected_revisions are mutually exclusive")
    if expected_revisions is not None and expected_ids is not None and set(expected_revisions) != set(expected_ids):
        raise ValidationError("expected_revisions must exactly map every expected input_id")
    if expected_revisions is not None and any(
        not isinstance(input_id, str) or isinstance(revision, bool) or not isinstance(revision, int) or revision <= 0
        for input_id, revision in expected_revisions.items()
    ):
        raise ValidationError("expected_revisions must map string input IDs to positive integer revisions")
    output_validator = _validator(output_schema, output_schema_path, "output")
    input_validator = _validator(input_schema, input_schema_path, "input")

    input_by_id: dict[str, dict[str, Any]] = {}
    for line_no, source in enumerate(source_records, start=1):
        _validate_schema(source, input_validator, "source input", line_no)
        source_id = source["id"]
        if source_id in input_by_id:
            raise ValidationError(f"source input {source_id} path /id: duplicate input ID")
        input_by_id[source_id] = source

    ids: list[str] = []
    for line_no, record in enumerate(records, start=1):
        _validate_schema(record, output_validator, "record", line_no)
        record_id = record["input_id"]
        ids.append(record_id)
        if record_id not in input_by_id:
            raise ValidationError(f"record {record_id} path /input_id: no matching source input")
        source = input_by_id[record_id]
        if record["headword"]["expression"] != source["expression"]:
            raise ValidationError(
                f"record {record_id} path /headword/expression: does not match source input /expression"
            )
        if record["headword"]["reading"] != source["reading"]:
            raise ValidationError(f"record {record_id} path /headword/reading: does not match source input /reading")
        if expected_revisions is not None and record_id not in expected_revisions:
            raise ValidationError(f"record {record_id} path /revision: no expected per-ID revision is configured",
                                  record_id=record_id, path="/revision")
        expected_record_revision = (
            expected_revisions.get(record_id) if expected_revisions is not None else expected_revision
        )
        if expected_record_revision is not None and record["revision"] != expected_record_revision:
            raise ValidationError(
                f"record {record_id} path /revision: expected revision {expected_record_revision}, got {record['revision']}",
                record_id=record_id, path="/revision",
            )
        if record["schema_version"] != expected_schema_version:
            raise ValidationError(
                f"record {record_id} path /schema_version: expected {expected_schema_version!r}"
            )
        for path, value in _walk_strings(record):
            if ANKI_FIELD_SEPARATOR in value:
                raise ValidationError(f"record {record_id} path {path}: contains Anki's field separator U+001F")
        _check_unique_ids(record, record_id)
        _check_references(record, record_id)

    if len(ids) != len(set(ids)):
        duplicate = next(item for index, item in enumerate(ids) if item in ids[:index])
        raise ValidationError(f"dataset path /input_id: duplicate record {duplicate!r}")
    if expected_revisions is not None and set(expected_revisions) != set(ids):
        raise ValidationError("expected_revisions must exactly map every dataset input_id")
    if expected_ids is not None and tuple(ids) != expected_ids:
        raise ValidationError(f"dataset path /input_id: expected ordered IDs {list(expected_ids)!r}, got {ids!r}")


def load_and_validate_dataset(
    input_path: Path,
    source_path: Path,
    output_schema_path: Path,
    input_schema_path: Path,
    constraints: DatasetConstraints,
) -> tuple[list[dict[str, Any]], str, list[dict[str, Any]]]:
    raw, records = read_jsonl(input_path, "enriched JSONL")
    sha256 = hashlib.sha256(raw).hexdigest()
    if sha256 != constraints.input_sha256.lower():
        raise ValidationError(
            f"dataset path $: SHA-256 mismatch for frozen revision-1 input; "
            f"expected {constraints.input_sha256}, got {sha256}"
        )
    _, source_records = read_jsonl(source_path, "source input JSONL")
    output_schema = _load_json(output_schema_path, "output schema")
    input_schema = _load_json(input_schema_path, "input schema")
    validate_records(
        records,
        source_records,
        output_schema,
        input_schema,
        output_schema_path=output_schema_path,
        input_schema_path=input_schema_path,
        expected_ids=constraints.input_ids,
        expected_revision=constraints.revision,
        expected_schema_version=constraints.schema_version,
        expected_revisions=constraints.revisions,
    )
    return records, sha256, source_records
