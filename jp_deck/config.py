"""Safe, typed YAML configuration loaded at the command-line boundary only."""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Mapping

import yaml
from yaml.constructor import ConstructorError

from .sources import is_registered_adapter
from yaml.nodes import MappingNode


class ConfigError(ValueError):
    """A concise, actionable configuration-file error."""


class _UniqueKeySafeLoader(yaml.SafeLoader):
    """SafeLoader variant that rejects duplicate keys instead of keeping one silently."""

    def construct_mapping(self, node: MappingNode, deep: bool = False) -> dict[Any, Any]:
        self.flatten_mapping(node)
        seen: set[Any] = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=deep)
            try:
                duplicate = key in seen
                seen.add(key)
            except TypeError as exc:
                raise ConstructorError(
                    "while constructing a mapping",
                    node.start_mark,
                    "mapping keys must be scalar and hashable",
                    key_node.start_mark,
                ) from exc
            if duplicate:
                raise ConstructorError(
                    "while constructing a mapping",
                    node.start_mark,
                    f"duplicate key {key!r}",
                    key_node.start_mark,
                )
        return super().construct_mapping(node, deep=deep)


@dataclass(frozen=True)
class ConfigPaths:
    input: Path
    source_input: Path
    output_schema: Path
    input_schema: Path
    output_dir: Path


@dataclass(frozen=True)
class PackageSettings:
    apkg_filename: str
    model_name: str
    model_id: int
    deck_name: str
    deck_id: int
    guid_namespace: str
    stable_id_epoch_seconds: int | float


@dataclass(frozen=True)
class DatasetConstraints:
    input_sha256: str
    input_ids: tuple[str, ...]
    revision: int | None
    schema_version: str
    revisions: Mapping[str, int] | None = None


@dataclass(frozen=True)
class AppConfig:
    paths: ConfigPaths
    package: PackageSettings
    constraints: DatasetConstraints
    config_path: Path
    config_sha256: str
    overrides: tuple[tuple[str, str], ...] = ()
    stage_config: StageConfig | None = None


@dataclass(frozen=True)
class StagePaths:
    input: Path | None = None
    source_input: Path | None = None
    output_schema: Path | None = None
    input_schema: Path | None = None
    output_dir: Path | None = None


@dataclass(frozen=True)
class StageConstraints:
    input_sha256: str | None = None
    input_ids: tuple[str, ...] | None = None
    revision: int | None = None
    schema_version: str | None = None
    source_input_sha256: str | None = None
    revisions: Mapping[str, int] | None = None


@dataclass(frozen=True)
class SourceSettings:
    apkg: Path
    sha256: str
    adapter: str
    mapping_contract: Path
    mapping_contract_version: str
    mapping_contract_sha256: str
    deck_ids: tuple[int, ...]
    note_type_ids: tuple[int, ...]
    selection_order: str
    selection_count: int


@dataclass(frozen=True)
class NormalizationDestinations:
    source_map: Path
    raw_notes: Path
    exceptions: Path
    report: Path


@dataclass(frozen=True)
class BatchSettings:
    batch_size: int
    output_dir: Path


@dataclass(frozen=True)
class AggregationSettings:
    manifest_path: Path
    manifest_sha256: str
    acceptances: tuple[Path, ...]
    contract_path: Path
    contract_sha256: str
    provenance_path: Path
    report_path: Path
    review_scope: str


@dataclass(frozen=True)
class StageConfig:
    paths: StagePaths
    package: PackageSettings | None
    constraints: StageConstraints
    source: SourceSettings | None
    normalization: NormalizationDestinations | None
    config_path: Path
    config_sha256: str
    overrides: tuple[tuple[str, str], ...] = ()
    declared_paths: StagePaths | None = None
    batching: BatchSettings | None = None
    aggregation: AggregationSettings | None = None


def _fail(path: Path, key: str, message: str) -> None:
    raise ConfigError(f"{path}: {key}: {message}")


def _mapping(value: Any, *, path: Path, key: str) -> dict[str, Any]:
    if not isinstance(value, dict) or any(not isinstance(item, str) for item in value):
        _fail(path, key, "must be a mapping with string keys")
    return value


def _exact_keys(value: dict[str, Any], required: set[str], *, path: Path, key: str) -> None:
    unknown = sorted(set(value) - required)
    missing = sorted(required - set(value))
    if unknown:
        _fail(path, key, f"unknown key(s): {', '.join(unknown)}")
    if missing:
        _fail(path, f"{key}.{missing[0]}" if key else missing[0], "is required")


def _string(value: Any, *, path: Path, key: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail(path, key, "must be a non-blank string")
    return value


def _record_id(value: Any, *, path: Path, key: str) -> str:
    item = _string(value, path=path, key=key)
    if item != item.strip() or any(ord(char) < 0x20 or ord(char) == 0x7F for char in item):
        _fail(path, key, "must be a nonblank ID without surrounding whitespace or control characters")
    return item


def _integer(value: Any, *, path: Path, key: str, minimum: int = 1) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        _fail(path, key, f"must be an integer >= {minimum}")
    return value


def _resolve_path(value: Any, *, config_path: Path, key: str) -> Path:
    raw = _string(value, path=config_path, key=key)
    candidate = Path(raw)
    if candidate.is_absolute():
        return candidate.resolve()
    return (config_path.parent / candidate).resolve()


def _validate_epoch_range(epoch: int | float, note_count: int, path: Path) -> None:
    try:
        first = int(epoch * 1000)
        last = first + 2 * note_count - 1
    except (OverflowError, ValueError) as exc:
        _fail(path, "package.stable_id_epoch_seconds", f"does not produce a SQLite-compatible native ID sequence: {exc}")
    if note_count <= 0 or first < -(2**63) or last > 2**63 - 1:
        _fail(
            path,
            "package.stable_id_epoch_seconds",
            f"the {note_count}-note/{note_count}-card native ID sequence must fit signed 64-bit SQLite IDs",
        )


def load_config(path: Path) -> AppConfig:
    """Read and validate one YAML file; resolve its paths against its own directory."""
    config_path = Path(path).resolve()
    try:
        raw = config_path.read_bytes()
    except OSError as exc:
        raise ConfigError(f"Cannot read configuration {config_path}: {exc.strerror or exc}") from exc
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ConfigError(f"{config_path}: invalid UTF-8 at byte {exc.start}") from exc
    try:
        document = yaml.load(text, Loader=_UniqueKeySafeLoader)
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        location = f"{config_path}:{mark.line + 1}:{mark.column + 1}" if mark else str(config_path)
        detail = getattr(exc, "problem", None) or str(exc).splitlines()[0]
        raise ConfigError(f"{location}: invalid YAML: {detail}") from exc

    root = _mapping(document, path=config_path, key="config")
    _exact_keys(root, {"config_version", "paths", "package", "constraints"}, path=config_path, key="config")
    config_version = root["config_version"]
    if isinstance(config_version, bool) or not isinstance(config_version, int) or config_version != 1:
        _fail(config_path, "config_version", "unsupported version; expected integer 1")

    paths_doc = _mapping(root["paths"], path=config_path, key="paths")
    path_keys = {"input", "source_input", "output_schema", "input_schema", "output_dir"}
    _exact_keys(paths_doc, path_keys, path=config_path, key="paths")
    paths = ConfigPaths(**{
        name: _resolve_path(paths_doc[name], config_path=config_path, key=f"paths.{name}")
        for name in ("input", "source_input", "output_schema", "input_schema", "output_dir")
    })

    package_doc = _mapping(root["package"], path=config_path, key="package")
    package_keys = {
        "apkg_filename", "model_name", "model_id", "deck_name", "deck_id",
        "guid_namespace", "stable_id_epoch_seconds",
    }
    _exact_keys(package_doc, package_keys, path=config_path, key="package")
    filename = _string(package_doc["apkg_filename"], path=config_path, key="package.apkg_filename")
    if (
        filename == ".apkg"
        or not filename.endswith(".apkg")
        or "/" in filename
        or "\\" in filename
        or "\x00" in filename
        or Path(filename).name != filename
    ):
        _fail(config_path, "package.apkg_filename", "must be a basename ending in .apkg with no path separators")
    model_id = _integer(package_doc["model_id"], path=config_path, key="package.model_id")
    deck_id = _integer(package_doc["deck_id"], path=config_path, key="package.deck_id")
    if model_id > 2**63 - 1:
        _fail(config_path, "package.model_id", "must fit a positive signed 64-bit ID")
    if deck_id > 2**63 - 1:
        _fail(config_path, "package.deck_id", "must fit a positive signed 64-bit ID")
    if deck_id == 1:
        _fail(config_path, "package.deck_id", "must not collide with genanki's reserved Default deck ID 1")
    if model_id == deck_id:
        _fail(config_path, "package.deck_id", "must differ from package.model_id")
    epoch = package_doc["stable_id_epoch_seconds"]
    if isinstance(epoch, bool) or not isinstance(epoch, (int, float)):
        _fail(config_path, "package.stable_id_epoch_seconds", "must be a finite positive number")
    try:
        finite_epoch = math.isfinite(epoch)
    except OverflowError:
        # An arbitrarily large Python integer is finite, but the SQLite bound below will reject it.
        finite_epoch = isinstance(epoch, int)
    if not finite_epoch or epoch <= 0:
        _fail(config_path, "package.stable_id_epoch_seconds", "must be a finite positive number")
    try:
        int(epoch * 1000)
    except (OverflowError, ValueError) as exc:
        _fail(
            config_path,
            "package.stable_id_epoch_seconds",
            f"does not produce a SQLite-compatible native ID sequence: {exc}",
        )
    package = PackageSettings(
        apkg_filename=filename,
        model_name=_string(package_doc["model_name"], path=config_path, key="package.model_name"),
        model_id=model_id,
        deck_name=_string(package_doc["deck_name"], path=config_path, key="package.deck_name"),
        deck_id=deck_id,
        guid_namespace=_string(package_doc["guid_namespace"], path=config_path, key="package.guid_namespace"),
        stable_id_epoch_seconds=epoch,
    )

    constraints_doc = _mapping(root["constraints"], path=config_path, key="constraints")
    constraint_keys = {"input_sha256", "input_ids", "revision", "schema_version"}
    _exact_keys(constraints_doc, constraint_keys, path=config_path, key="constraints")
    input_sha256 = _string(constraints_doc["input_sha256"], path=config_path, key="constraints.input_sha256")
    if re.fullmatch(r"[0-9a-fA-F]{64}", input_sha256) is None:
        _fail(config_path, "constraints.input_sha256", "must be a 64-character SHA-256 hex digest")
    input_ids_value = constraints_doc["input_ids"]
    if not isinstance(input_ids_value, list) or not input_ids_value:
        _fail(config_path, "constraints.input_ids", "must be a non-empty ordered list of unique strings")
    input_ids = tuple(
        _string(value, path=config_path, key=f"constraints.input_ids[{index}]")
        for index, value in enumerate(input_ids_value)
    )
    if len(set(input_ids)) != len(input_ids):
        _fail(config_path, "constraints.input_ids", "must not contain duplicate IDs")
    constraints = DatasetConstraints(
        input_sha256=input_sha256,
        input_ids=input_ids,
        revision=_integer(constraints_doc["revision"], path=config_path, key="constraints.revision"),
        schema_version=_string(constraints_doc["schema_version"], path=config_path, key="constraints.schema_version"),
    )
    _validate_epoch_range(package.stable_id_epoch_seconds, len(input_ids), config_path)
    return AppConfig(
        paths=paths,
        package=package,
        constraints=constraints,
        config_path=config_path,
        config_sha256=hashlib.sha256(raw).hexdigest(),
    )


def apply_path_overrides(config: AppConfig, overrides: Mapping[str, Path]) -> AppConfig:
    """Apply only explicitly supplied CLI paths, resolved against invocation cwd."""
    allowed = {"input", "source_input", "output_schema", "input_schema", "output_dir"}
    unknown = set(overrides) - allowed
    if unknown:
        raise ValueError(f"Unknown CLI path override(s): {', '.join(sorted(unknown))}")
    if not overrides:
        return config
    resolved = {key: Path(value).resolve() for key, value in overrides.items()}
    return replace(
        config,
        paths=replace(config.paths, **resolved),
        overrides=tuple((key, str(resolved[key])) for key in sorted(resolved)),
    )


def effective_settings(config: AppConfig) -> dict[str, Any]:
    """Return audit-safe JSON values for resolved configuration (never learner fields)."""
    return {
        "paths": {key: str(getattr(config.paths, key)) for key in ConfigPaths.__dataclass_fields__},
        "package": {
            key: getattr(config.package, key)
            for key in PackageSettings.__dataclass_fields__
        },
        "constraints": {
            "input_sha256": config.constraints.input_sha256,
            "input_ids": list(config.constraints.input_ids),
            "revision": config.constraints.revision,
            "schema_version": config.constraints.schema_version,
            **({"revisions": dict(config.constraints.revisions)} if config.constraints.revisions is not None else {}),
        },
    }


def _sha256(value: Any, *, path: Path, key: str) -> str:
    digest = _string(value, path=path, key=key)
    if re.fullmatch(r"[0-9a-fA-F]{64}", digest) is None:
        _fail(path, key, "must be a 64-character SHA-256 hex digest")
    return digest.lower()


def _parse_package(document: Any, *, path: Path) -> PackageSettings:
    package_doc = _mapping(document, path=path, key="package")
    package_keys = {
        "apkg_filename", "model_name", "model_id", "deck_name", "deck_id",
        "guid_namespace", "stable_id_epoch_seconds",
    }
    _exact_keys(package_doc, package_keys, path=path, key="package")
    filename = _string(package_doc["apkg_filename"], path=path, key="package.apkg_filename")
    if (
        filename == ".apkg"
        or not filename.endswith(".apkg")
        or "/" in filename
        or "\\" in filename
        or "\x00" in filename
        or Path(filename).name != filename
    ):
        _fail(path, "package.apkg_filename", "must be a basename ending in .apkg with no path separators")
    model_id = _integer(package_doc["model_id"], path=path, key="package.model_id")
    deck_id = _integer(package_doc["deck_id"], path=path, key="package.deck_id")
    if model_id > 2**63 - 1:
        _fail(path, "package.model_id", "must fit a positive signed 64-bit ID")
    if deck_id > 2**63 - 1:
        _fail(path, "package.deck_id", "must fit a positive signed 64-bit ID")
    if deck_id == 1:
        _fail(path, "package.deck_id", "must not collide with genanki's reserved Default deck ID 1")
    if model_id == deck_id:
        _fail(path, "package.deck_id", "must differ from package.model_id")
    epoch = package_doc["stable_id_epoch_seconds"]
    if isinstance(epoch, bool) or not isinstance(epoch, (int, float)):
        _fail(path, "package.stable_id_epoch_seconds", "must be a finite positive number")
    try:
        finite_epoch = math.isfinite(epoch)
    except OverflowError:
        finite_epoch = isinstance(epoch, int)
    if not finite_epoch or epoch <= 0:
        _fail(path, "package.stable_id_epoch_seconds", "must be a finite positive number")
    try:
        int(epoch * 1000)
    except (OverflowError, ValueError) as exc:
        _fail(path, "package.stable_id_epoch_seconds", f"does not produce a SQLite-compatible native ID sequence: {exc}")
    return PackageSettings(
        apkg_filename=filename,
        model_name=_string(package_doc["model_name"], path=path, key="package.model_name"),
        model_id=model_id,
        deck_name=_string(package_doc["deck_name"], path=path, key="package.deck_name"),
        deck_id=deck_id,
        guid_namespace=_string(package_doc["guid_namespace"], path=path, key="package.guid_namespace"),
        stable_id_epoch_seconds=epoch,
    )


def _revision_map(value: Any, *, input_ids: tuple[str, ...] | None, path: Path) -> dict[str, int]:
    key = "constraints.revisions"
    revisions = _mapping(value, path=path, key=key)
    if input_ids is None:
        _fail(path, key, "requires constraints.input_ids")
    if set(revisions) != set(input_ids):
        missing = [item for item in input_ids if item not in revisions]
        extra = sorted(set(revisions) - set(input_ids))
        _fail(path, key, f"must be an exact mapping for constraints.input_ids (missing={missing}, extra={extra})")
    return {
        input_id: _integer(revisions[input_id], path=path, key=f"{key}.{input_id}")
        for input_id in input_ids
    }


def _parse_aggregation(document: Any, *, path: Path) -> AggregationSettings:
    key = "aggregation"
    section = _mapping(document, path=path, key=key)
    _exact_keys(section, {"manifest", "acceptances", "contract", "provenance", "report", "review_scope"}, path=path, key=key)
    manifest = _mapping(section["manifest"], path=path, key="aggregation.manifest")
    _exact_keys(manifest, {"path", "sha256"}, path=path, key="aggregation.manifest")
    contract = _mapping(section["contract"], path=path, key="aggregation.contract")
    _exact_keys(contract, {"path", "sha256"}, path=path, key="aggregation.contract")
    acceptances_doc = section["acceptances"]
    if not isinstance(acceptances_doc, list) or not acceptances_doc:
        _fail(path, "aggregation.acceptances", "must be a non-empty ordered list of artifact paths")
    acceptances = tuple(
        _resolve_path(item, config_path=path, key=f"aggregation.acceptances[{index}]")
        for index, item in enumerate(acceptances_doc)
    )
    if len(set(acceptances)) != len(acceptances):
        _fail(path, "aggregation.acceptances", "must not contain duplicate resolved artifact paths")
    review_scope = _string(section["review_scope"], path=path, key="aggregation.review_scope")
    if review_scope not in {"structure-and-collocation-attestation/v1", "schema-first-sampled-source/v1"}:
        _fail(path, "aggregation.review_scope", "must be a supported explicit review profile")
    manifest_path = _resolve_path(manifest["path"], config_path=path, key="aggregation.manifest.path")
    contract_path = _resolve_path(contract["path"], config_path=path, key="aggregation.contract.path")
    provenance_path = _resolve_path(section["provenance"], config_path=path, key="aggregation.provenance")
    report_path = _resolve_path(section["report"], config_path=path, key="aggregation.report")
    named_outputs = {provenance_path, report_path}
    if len(named_outputs) != 2:
        _fail(path, "aggregation", "provenance and report targets must resolve to distinct paths")
    return AggregationSettings(
        manifest_path=manifest_path,
        manifest_sha256=_sha256(manifest["sha256"], path=path, key="aggregation.manifest.sha256"),
        acceptances=acceptances,
        contract_path=contract_path,
        contract_sha256=_sha256(contract["sha256"], path=path, key="aggregation.contract.sha256"),
        provenance_path=provenance_path,
        report_path=report_path,
        review_scope=review_scope,
    )


def load_stage_config(path: Path, *, stage: str) -> StageConfig:
    """Load a version-2 partial config while validating every declared setting.

    Missing future-stage fields are permitted; malformed declared values are not.
    The version-1 full-build loader remains separate and unchanged.
    """
    supported_stages = {"normalize", "validate-input", "validate-output", "build", "prepare-batches", "validate-batches", "aggregate-output", "validate-aggregate"}
    if stage not in supported_stages:
        raise ValueError(f"Unsupported stage config stage {stage!r}")
    config_path = Path(path).resolve()
    try:
        raw = config_path.read_bytes()
    except OSError as exc:
        raise ConfigError(f"Cannot read configuration {config_path}: {exc.strerror or exc}") from exc
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ConfigError(f"{config_path}: invalid UTF-8 at byte {exc.start}") from exc
    try:
        document = yaml.load(text, Loader=_UniqueKeySafeLoader)
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        location = f"{config_path}:{mark.line + 1}:{mark.column + 1}" if mark else str(config_path)
        detail = getattr(exc, "problem", None) or str(exc).splitlines()[0]
        raise ConfigError(f"{location}: invalid YAML: {detail}") from exc

    root = _mapping(document, path=config_path, key="config")
    allowed_root = {"config_version", "paths", "package", "constraints", "source", "normalization", "batching", "aggregation"}
    unknown_root = sorted(set(root) - allowed_root)
    if unknown_root:
        _fail(config_path, "config", f"unknown key(s): {', '.join(unknown_root)}")
    for required in ("config_version", "paths"):
        if required not in root:
            _fail(config_path, required, "is required")
    version = root["config_version"]
    if isinstance(version, bool) or not isinstance(version, int) or version != 2:
        _fail(config_path, "config_version", "unsupported version; expected integer 2")

    paths_doc = _mapping(root["paths"], path=config_path, key="paths")
    path_keys = {"input", "source_input", "output_schema", "input_schema", "output_dir"}
    unknown_paths = sorted(set(paths_doc) - path_keys)
    if unknown_paths:
        _fail(config_path, "paths", f"unknown key(s): {', '.join(unknown_paths)}")
    paths = StagePaths(**{
        name: _resolve_path(paths_doc[name], config_path=config_path, key=f"paths.{name}")
        for name in path_keys.intersection(paths_doc)
    })
    if stage in {"normalize", "validate-input", "prepare-batches", "validate-batches"}:
        if paths.source_input is None:
            _fail(config_path, "paths.source_input", f"is required for {stage}")
        if paths.input_schema is None:
            _fail(config_path, "paths.input_schema", f"is required for {stage}")
    else:
        for name in ("input", "source_input", "output_schema", "input_schema"):
            if getattr(paths, name) is None:
                _fail(config_path, f"paths.{name}", f"is required for {stage}")
        if stage == "build" and paths.output_dir is None:
            _fail(config_path, "paths.output_dir", "is required for build")

    package = _parse_package(root["package"], path=config_path) if "package" in root else None

    constraints_doc = _mapping(root.get("constraints", {}), path=config_path, key="constraints")
    constraint_keys = {"input_sha256", "input_ids", "revision", "revisions", "schema_version", "source_input_sha256"}
    unknown_constraints = sorted(set(constraints_doc) - constraint_keys)
    if unknown_constraints:
        _fail(config_path, "constraints", f"unknown key(s): {', '.join(unknown_constraints)}")
    if "input_sha256" in constraints_doc:
        input_sha256 = _sha256(constraints_doc["input_sha256"], path=config_path, key="constraints.input_sha256")
    else:
        input_sha256 = None
    if "source_input_sha256" in constraints_doc:
        source_input_sha256 = _sha256(
            constraints_doc["source_input_sha256"], path=config_path, key="constraints.source_input_sha256"
        )
    else:
        source_input_sha256 = None
    ids: tuple[str, ...] | None = None
    if "input_ids" in constraints_doc:
        ids_value = constraints_doc["input_ids"]
        if not isinstance(ids_value, list) or not ids_value:
            _fail(config_path, "constraints.input_ids", "must be a non-empty ordered list of unique strings")
        ids = tuple(_record_id(value, path=config_path, key=f"constraints.input_ids[{index}]") for index, value in enumerate(ids_value))
        if len(set(ids)) != len(ids):
            _fail(config_path, "constraints.input_ids", "must not contain duplicate IDs")
    revision = _integer(constraints_doc["revision"], path=config_path, key="constraints.revision") if "revision" in constraints_doc else None
    schema_version = _string(constraints_doc["schema_version"], path=config_path, key="constraints.schema_version") if "schema_version" in constraints_doc else None
    revisions = _revision_map(constraints_doc["revisions"], input_ids=ids, path=config_path) if "revisions" in constraints_doc else None
    if revision is not None and revisions is not None:
        _fail(config_path, "constraints", "revision and revisions are mutually exclusive")
    aggregation = _parse_aggregation(root["aggregation"], path=config_path) if "aggregation" in root else None
    if revisions is not None and aggregation is None:
        _fail(config_path, "constraints.revisions", "is supported only in aggregation mode")
    if stage in {"aggregate-output", "validate-aggregate"} and aggregation is None:
        _fail(config_path, "aggregation", f"is required for {stage}")
    if aggregation is not None and revisions is None:
        _fail(config_path, "constraints.revisions", "is required for aggregation mode")
    if aggregation is not None and revision is not None:
        _fail(config_path, "constraints", "scalar revision is not supported in aggregation mode")
    constraints = StageConstraints(input_sha256, ids, revision, schema_version, source_input_sha256, revisions)
    if stage in {"validate-output", "build", "aggregate-output", "validate-aggregate"}:
        if ids is None:
            _fail(config_path, "constraints.input_ids", f"is required for {stage}")
        if schema_version is None:
            _fail(config_path, "constraints.schema_version", f"is required for {stage}")
        if aggregation is None and revision is None:
            _fail(config_path, "constraints.revision", f"is required for {stage}")
        if aggregation is not None:
            if source_input_sha256 is None:
                _fail(config_path, "constraints.source_input_sha256", f"is required for {stage} aggregation mode")
            if tuple(revisions or ()) != ids:
                _fail(config_path, "constraints.revisions", "must exactly follow constraints.input_ids order")
        if stage == "build":
            if input_sha256 is None and aggregation is None:
                _fail(config_path, "constraints.input_sha256", "is required for build")
            if source_input_sha256 is None:
                _fail(config_path, "constraints.source_input_sha256", "is required for build")
            if package is None:
                _fail(config_path, "package", "is required for build")

    source: SourceSettings | None = None
    if "source" in root:
        source_doc = _mapping(root["source"], path=config_path, key="source")
        source_keys = {
            "apkg", "sha256", "adapter", "mapping_contract", "mapping_contract_version",
            "mapping_contract_sha256", "deck_ids", "note_type_ids", "selection",
        }
        _exact_keys(source_doc, source_keys, path=config_path, key="source")
        selection_doc = _mapping(source_doc["selection"], path=config_path, key="source.selection")
        _exact_keys(selection_doc, {"order", "count"}, path=config_path, key="source.selection")
        def id_list(value: Any, key: str) -> tuple[int, ...]:
            if not isinstance(value, list) or not value:
                _fail(config_path, key, "must be a non-empty list of unique positive integer IDs")
            result = tuple(_integer(item, path=config_path, key=f"{key}[{index}]") for index, item in enumerate(value))
            if len(set(result)) != len(result):
                _fail(config_path, key, "must not contain duplicate IDs")
            if any(item > 2**63 - 1 for item in result):
                _fail(config_path, key, "IDs must fit positive signed 64-bit integers")
            return result
        adapter = _string(source_doc["adapter"], path=config_path, key="source.adapter")
        if not is_registered_adapter(adapter):
            _fail(config_path, "source.adapter", "unsupported source adapter profile")
        selection_order = _string(selection_doc["order"], path=config_path, key="source.selection.order")
        if selection_order != "note_id_ascending":
            _fail(config_path, "source.selection.order", "unsupported selection order")
        mapping_version = _string(source_doc["mapping_contract_version"], path=config_path, key="source.mapping_contract_version")
        source = SourceSettings(
            apkg=_resolve_path(source_doc["apkg"], config_path=config_path, key="source.apkg"),
            sha256=_sha256(source_doc["sha256"], path=config_path, key="source.sha256"),
            adapter=adapter,
            mapping_contract=_resolve_path(source_doc["mapping_contract"], config_path=config_path, key="source.mapping_contract"),
            mapping_contract_version=mapping_version,
            mapping_contract_sha256=_sha256(source_doc["mapping_contract_sha256"], path=config_path, key="source.mapping_contract_sha256"),
            deck_ids=id_list(source_doc["deck_ids"], "source.deck_ids"),
            note_type_ids=id_list(source_doc["note_type_ids"], "source.note_type_ids"),
            selection_order=selection_order,
            selection_count=_integer(selection_doc["count"], path=config_path, key="source.selection.count"),
        )

    normalization: NormalizationDestinations | None = None
    if "normalization" in root:
        norm_doc = _mapping(root["normalization"], path=config_path, key="normalization")
        norm_keys = {"source_map", "raw_notes", "exceptions", "report"}
        _exact_keys(norm_doc, norm_keys, path=config_path, key="normalization")
        normalization = NormalizationDestinations(**{
            key: _resolve_path(norm_doc[key], config_path=config_path, key=f"normalization.{key}")
            for key in norm_keys
        })

    if stage in {"normalize", "prepare-batches", "validate-batches"}:
        if source is None:
            _fail(config_path, "source", f"is required for {stage}")
        if normalization is None:
            _fail(config_path, "normalization", f"is required for {stage}")
        if constraints.input_ids is None:
            _fail(config_path, "constraints.input_ids", f"is required for {stage}")
    elif source is not None and normalization is None:
        _fail(config_path, "normalization", "is required when a source profile is supplied")

    batching: BatchSettings | None = None
    if "batching" in root:
        batching_doc = _mapping(root["batching"], path=config_path, key="batching")
        _exact_keys(batching_doc, {"batch_size", "output_dir"}, path=config_path, key="batching")
        batching = BatchSettings(
            batch_size=_integer(batching_doc["batch_size"], path=config_path, key="batching.batch_size"),
            output_dir=_resolve_path(batching_doc["output_dir"], config_path=config_path, key="batching.output_dir"),
        )
    if stage in {"prepare-batches", "validate-batches"} and batching is None:
        _fail(config_path, "batching", f"is required for {stage}")
    if source is not None and constraints.input_ids is not None and source.selection_count != len(constraints.input_ids):
        _fail(config_path, "source.selection.count", "must equal the configured constraints.input_ids count")
    if package is not None and ids is not None:
        _validate_epoch_range(package.stable_id_epoch_seconds, len(ids), config_path)

    return StageConfig(
        paths=paths,
        package=package,
        constraints=constraints,
        source=source,
        normalization=normalization,
        config_path=config_path,
        config_sha256=hashlib.sha256(raw).hexdigest(),
        declared_paths=paths,
        batching=batching,
        aggregation=aggregation,
    )
