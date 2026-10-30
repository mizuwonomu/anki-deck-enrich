"""Command-line entry point for the configured frozen APKG build."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .aggregation import aggregate_output, validate_aggregate
from .batching import prepare_batches, validate_batches
from .config import ConfigError, load_stage_config
from .input_validation import (
    InputStageError,
    protected_stage_paths,
    publish_validation_report,
    validate_input_dataset,
    validation_report_path,
)
from .normalization import normalize_source
from .output_validation import (
    app_config_for_build,
    apply_stage_path_overrides,
    build_targets,
    contextualize_build_error,
    validate_output,
)
from .packaging import build
from .source_apkg import SourceError
from .validation import ValidationError

STAGES = (
    "normalize", "validate-input", "validate-output", "prepare-batches", "validate-batches",
    "aggregate-output", "validate-aggregate", "build",
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        prog="python -m jp_deck",
        description="Run a deterministic pipeline stage with an explicit version-2 YAML configuration.",
    )
    result.add_argument("stage", choices=STAGES, help="stage to execute; every stage requires --config")
    return result


def _stage_parser(stage: str) -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog=f"python -m jp_deck {stage}")
    result.add_argument("--config", type=Path, required=True, help="version-2 stage YAML configuration")
    if stage == "build":
        result.add_argument("--input", type=Path, default=None, help="override configured enriched JSONL")
        result.add_argument("--source-input", type=Path, default=None, help="override configured source-note JSONL")
        result.add_argument("--output-schema", type=Path, default=None, help="override configured enriched schema")
        result.add_argument("--input-schema", type=Path, default=None, help="override configured source-note schema")
        result.add_argument("--output-dir", type=Path, default=None, help="override configured artifact directory")
        result.add_argument("--force", action="store_true", help="replace only the named build deliverables")
    elif stage == "normalize":
        result.add_argument("--force", action="store_true", help="replace only the named normalization outputs")
    elif stage == "prepare-batches":
        result.add_argument("--force", action="store_true", help="replace only the named batch artifacts")
    elif stage == "aggregate-output":
        result.add_argument("--force", action="store_true", help="replace only named aggregate outputs")
    return result


def _stage_failure(stage: str, exc: Exception) -> dict[str, object]:
    if isinstance(exc, ConfigError):
        code = "config_error"
    elif isinstance(exc, SourceError):
        code = "source_error"
    elif isinstance(exc, FileExistsError):
        code = "artifact_exists"
    elif isinstance(exc, (InputStageError, ValidationError)):
        code = "validation_error"
    elif isinstance(exc, OSError):
        code = "io_error"
    elif isinstance(exc, ValueError):
        code = "validation_error"
    else:
        code = "io_error"
    return {
        "stage": stage,
        "status": "fail",
        "errors": [{
            "code": code,
            "message": str(exc),
            "record_id": getattr(exc, "record_id", None),
            "file": getattr(exc, "file", None),
            "path": getattr(exc, "path", None),
        }],
    }


def _run_stage(stage: str, argv: list[str]) -> int:
    args = _stage_parser(stage).parse_args(argv)
    try:
        config = load_stage_config(args.config, stage=stage)
        if stage == "normalize":
            result = normalize_source(config, force=args.force)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        if stage == "validate-output":
            result = validate_output(config)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        if stage == "prepare-batches":
            result = prepare_batches(config, force=args.force)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        if stage == "validate-batches":
            result = validate_batches(config)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        if stage == "aggregate-output":
            result = aggregate_output(config, force=args.force)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        if stage == "validate-aggregate":
            result = validate_aggregate(config)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        if stage == "build":
            overrides = {
                name: value
                for name, value in (
                    ("input", args.input),
                    ("source_input", args.source_input),
                    ("output_schema", args.output_schema),
                    ("input_schema", args.input_schema),
                    ("output_dir", args.output_dir),
                )
                if value is not None
            }
            config = apply_stage_path_overrides(config, overrides)
            build_targets(config)
            validation = validate_output(config)
            try:
                built = build(app_config_for_build(config, verified_input_sha256=validation["input_sha256"]), force=args.force)
            except ValueError as exc:
                effective_input = config.paths.input or config.config_path
                raise contextualize_build_error(exc, file=effective_input) from exc
            result = {
                "stage": "build",
                "status": "pass",
                "checked_counts": validation["checked_counts"],
                "input_sha256": validation["input_sha256"],
                "source_input_sha256": validation["source_input_sha256"],
                "artifacts": built["artifacts"],
                "package_audit": built["audit"]["package_audit"],
            }
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        report = validate_input_dataset(config)
        report_path = validation_report_path(config)
        protected = protected_stage_paths(config, publisher_stage="validate-input")
        publish_validation_report(report_path, report, protected=protected)
        result = dict(report)
        result["artifacts"] = {"input_validation_report": str(report_path)}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ConfigError, SourceError, InputStageError, ValidationError, FileExistsError, OSError, ValueError, RuntimeError) as exc:
        print(json.dumps(_stage_failure(stage, exc), ensure_ascii=False, indent=2), file=sys.stderr)
        return 2


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments and arguments[0] in STAGES:
        return _run_stage(arguments[0], arguments[1:])
    args = parser().parse_args(arguments)
    return _run_stage(args.stage, arguments[1:])


if __name__ == "__main__":
    raise SystemExit(main())
