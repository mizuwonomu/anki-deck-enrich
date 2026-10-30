"""Deterministic genanki model/deck construction and artifact build flow."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import tempfile
from importlib.metadata import version
from pathlib import Path
from typing import Any

import genanki

from .audit import audit_apkg, snapshot_package_identity
from .config import AppConfig, PackageSettings, effective_settings
from .pathrefs import relative_reference
from .render import CSS, RenderedRecord, render_preview, render_record
from .validation import load_and_validate_dataset

FIELD_NAMES = ["Expression", "FrontCollocation", "BackContent"]
TEMPLATE_FRONT = (
    '<div class="card front"><div class="front-expression">{{Expression}}</div>'
    '<div class="front-collocation">{{FrontCollocation}}</div></div>'
)
TEMPLATE_BACK = '{{FrontSide}}<hr id="answer">{{BackContent}}'


def stable_guid(namespace: str, input_id: str) -> str:
    return genanki.guid_for(namespace, input_id)


def _new_anki_package(
    records: list[dict[str, Any]], rendered: list[RenderedRecord], settings: PackageSettings
) -> genanki.Package:
    model = genanki.Model(
        model_id=settings.model_id,
        name=settings.model_name,
        fields=[{"name": name} for name in FIELD_NAMES],
        templates=[{"name": "Recognition", "qfmt": TEMPLATE_FRONT, "afmt": TEMPLATE_BACK}],
        css=CSS,
    )
    deck = genanki.Deck(deck_id=settings.deck_id, name=settings.deck_name)
    for record, result in zip(records, rendered, strict=True):
        note = genanki.Note(
            model=model,
            fields=result.anki_fields,
            guid=stable_guid(settings.guid_namespace, record["input_id"]),
            tags=[],
        )
        deck.add_note(note)
    return genanki.Package(deck)


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build(config: AppConfig, *, force: bool = False) -> dict[str, Any]:
    if config.stage_config is not None and config.stage_config.aggregation is not None:
        from .aggregation import validate_aggregate
        from .output_validation import build_targets

        build_targets(config.stage_config)
        verified = validate_aggregate(config.stage_config)
        if verified["input_sha256"] != config.constraints.input_sha256:
            raise ValueError("builder enriched hash is not the verified aggregate hash")
    input_path = config.paths.input
    source_path = config.paths.source_input
    output_schema_path = config.paths.output_schema
    input_schema_path = config.paths.input_schema
    output_dir = config.paths.output_dir.resolve()
    settings = config.package
    output_names = {
        "apkg": settings.apkg_filename,
        "preview": "preview.html",
        "audit": "audit.json",
    }
    targets = {key: output_dir / name for key, name in output_names.items()}
    existing = [str(path) for path in targets.values() if path.exists()]
    if existing and not force:
        raise FileExistsError(
            "Refusing to overwrite generated output(s): " + ", ".join(existing) + "; rerun with --force to replace these files"
        )

    records, input_sha256, _ = load_and_validate_dataset(
        input_path, source_path, output_schema_path, input_schema_path, config.constraints
    )
    rendered = [render_record(record) for record in records]
    output_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix=".jp-deck-m1-build-", dir=output_dir) as stage_name:
        stage = Path(stage_name)
        staged_apkg = stage / output_names["apkg"]
        staged_preview = stage / output_names["preview"]
        staged_audit = stage / output_names["audit"]

        _new_anki_package(records, rendered, settings).write_to_file(
            staged_apkg, timestamp=settings.stable_id_epoch_seconds
        )
        audit = audit_apkg(
            staged_apkg,
            records,
            rendered,
            guid_namespace=settings.guid_namespace,
            model_id=settings.model_id,
            deck_id=settings.deck_id,
            deck_name=settings.deck_name,
            model_name=settings.model_name,
            field_names=FIELD_NAMES,
            template_front=TEMPLATE_FRONT,
            template_back=TEMPLATE_BACK,
        )
        preview_html = render_preview(rendered)
        staged_preview.write_text(preview_html, encoding="utf-8")
        # A second independently constructed package proves structural ID/GUID stability
        # without asserting ZIP byte-for-byte reproducibility (ZIP timestamps may differ).
        repeat_stage = stage / ".repeat-check"
        repeat_stage.mkdir()
        repeat_apkg = repeat_stage / "repeat-check.apkg"
        _new_anki_package(records, rendered, settings).write_to_file(
            repeat_apkg, timestamp=settings.stable_id_epoch_seconds
        )
        first_identity = snapshot_package_identity(staged_apkg)
        second_identity = snapshot_package_identity(repeat_apkg)
        if first_identity != second_identity:
            raise RuntimeError("Repeat-build Anki identity audit failed")
        audit["native_note_and_card_ids_stable"] = True
        repeat_apkg.unlink()

        package_bytes = staged_apkg.read_bytes()
        preview_bytes = staged_preview.read_bytes()
        source_bytes = source_path.read_bytes()
        content_counts = _content_counts(records)
        audit_owner = targets["audit"]
        persisted_settings = effective_settings(config)
        persisted_settings["paths"] = {
            key: relative_reference(audit_owner, Path(value))
            for key, value in persisted_settings["paths"].items()
        }
        persisted_overrides = {
            key: relative_reference(audit_owner, Path(value))
            for key, value in config.overrides
        }
        audit_document = {
            "audit_version": 3,
            "build": {
                "input_path": relative_reference(audit_owner, input_path),
                "input_sha256": input_sha256,
                "source_input_path": relative_reference(audit_owner, source_path),
                "source_input_sha256": hashlib.sha256(source_bytes).hexdigest(),
                "output_schema_sha256": hashlib.sha256(output_schema_path.read_bytes()).hexdigest(),
                "input_schema_sha256": hashlib.sha256(input_schema_path.read_bytes()).hexdigest(),
                "python_version": platform.python_version(),
                "genanki_version": genanki.__version__,
                "jsonschema_version": version("jsonschema"),
                "model_name": settings.model_name,
                "deck_name": settings.deck_name,
                "model_id": settings.model_id,
                "deck_id": settings.deck_id,
                "field_names_in_order": FIELD_NAMES,
                "input_ids_in_order": [record["input_id"] for record in records],
                "configuration": {
                    "path": relative_reference(audit_owner, config.config_path),
                    "sha256": config.config_sha256,
                    "effective_settings": persisted_settings,
                    "overrides": persisted_overrides,
                },
            },
            "artifacts": {
                "apkg": {
                    "filename": output_names["apkg"],
                    "size_bytes": len(package_bytes),
                    "sha256": hashlib.sha256(package_bytes).hexdigest(),
                },
                "preview": {
                    "filename": output_names["preview"],
                    "size_bytes": len(preview_bytes),
                    "sha256": hashlib.sha256(preview_bytes).hexdigest(),
                },
            },
            "content_counts": content_counts,
            "diagnostic_content_disposition": {
                "source_uncertainty_count": content_counts["uncertainties"],
                "uncertainties_retained_in_source_jsonl": True,
                "excluded_from_learner_fields": ["uncertainties[].issue_vi"],
                "interpretation": (
                    "Uncertainty issue text remains in the validated source JSONL and its source count; "
                    "excluding it from learner fields and preview is an intentional final presentation policy."
                ),
            },
            "technical_metadata_disposition": {
                "note_fields": FIELD_NAMES,
                "excluded_from_learner_fields": [
                    "input_id and all project/object/source/sense IDs",
                    "schema_version and revision",
                    "raw evidence_refs, source_id values, and JSON claim paths",
                    "source locators, raw JSON, input/schema/package hashes, and build audit details",
                ],
                "native_anki_ids_and_guids": "structural package data only; stable identities verified across two builds",
            },
            "package_audit": audit,
            "repeat_build_identity_audit": {
                "two_independent_builds_compared": True,
                "model_deck_note_card_ids_and_guids_identical": True,
                "byte_identical_apkg_claimed": False,
            },
            "live_anki_boundary": "Not verified: package was not imported or previewed in Anki Desktop/mobile.",
        }
        _write_json(staged_audit, audit_document)

        # Only the three named deliverables are moved into place; unrelated output files stay untouched.
        for key in ("apkg", "preview", "audit"):
            os.replace(staged_apkg if key == "apkg" else staged_preview if key == "preview" else staged_audit, targets[key])

    return {
        "output_dir": str(output_dir),
        "artifacts": {key: str(path) for key, path in targets.items()},
        "audit": audit_document,
    }


def _content_counts(records: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"records": len(records), "senses": 0, "examples": 0, "collocations": 0,
              "related_terms": 0, "confusables": 0, "sources": 0, "uncertainties": 0,
              "unmeasured_frequencies": 0}
    for record in records:
        for key in ("senses", "examples", "collocations", "related_terms", "confusables", "sources", "uncertainties"):
            counts[key] += len(record[key])
        counts["unmeasured_frequencies"] += sum(item["frequency"] is None for item in record["collocations"])
    return counts
