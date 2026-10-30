"""Test-scoped synthetic replacement for source-normalized master preflight."""

from __future__ import annotations

import hashlib
from typing import Any

from jp_deck.input_validation import InputStageError, _schema_validator, validate_input_objects
from jp_deck.validation import read_jsonl


def validate_master(config) -> dict[str, Any]:
    """Validate only fabricated master/schema bindings; do not impersonate Tango evidence."""
    if config.paths.source_input is None or config.paths.input_schema is None:
        raise InputStageError("synthetic batching requires source_input and input_schema", file=str(config.config_path))
    raw, records = read_jsonl(config.paths.source_input, "synthetic normalized master JSONL")
    validate_input_objects(records, _schema_validator(config.paths.input_schema), expected_ids=config.constraints.input_ids)
    digest = hashlib.sha256(raw).hexdigest()
    expected = config.constraints.source_input_sha256
    if expected is not None and digest != expected:
        raise InputStageError(
            f"synthetic source_input_sha256 mismatch: expected {expected}, got {digest}",
            file=str(config.paths.source_input), path="/",
        )
    return {"input_sha256": digest, "checked_counts": {"input_records": len(records)}}
