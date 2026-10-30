# Configuration contract

The current optional typed batching settings and variable-cardinality boundary are anchored by the [batching extension](../batching-mimi/decisions.md). Earlier fixed-five/ten-native-ID descriptions below are historical milestone constraints, not additional limits on the current runtime.

## Boundary and configuration ownership

The CLI loads one YAML file through [config.py](../../../jp_deck/config.py), applies explicit path overrides, then passes immutable typed configuration to packaging/validation/audit. Downstream modules do not load YAML or retain duplicate MVP fallback settings. configs/mvp.yaml is the shipped configuration. The shared implementation/review job contract records its exact key schema and accepted values.

The version-1 build config requires `config_version`, `paths`, `package`, and `constraints`. Paths cover enriched/source inputs, both JSON Schemas, and output directory. Package settings cover APKG filename, deck/model names and IDs, GUID namespace, and stable write epoch. Constraints cover raw input SHA-256, ordered IDs, revision, and schema version. Progress, completion and agent/job state remain outside YAML. Field names/order, templates, CSS, rendering rules, identity construction algorithms, audit coverage, and preview/audit basenames stay in code.

`AppConfig` contains `ConfigPaths`, `PackageSettings`, `DatasetConstraints`, config path/hash and explicit path overrides. Python callers supply configuration explicitly to `build(config, *, force=False)`; `load_and_validate_dataset` receives explicit constraints, and `audit_apkg` receives the configured GUID namespace. Former module-level MVP constants and the old keyword-only build-path API are not retained as duplicate fallback configuration.

## Paths, CLI and validation

`--config` defaults to repository `configs/mvp.yaml` independently of invocation cwd. Relative YAML paths resolve from the configuration file's parent. Explicit `--input`, `--source-input`, `--output-schema`, `--input-schema`, and `--output-dir` override only their corresponding paths, resolving relative to invocation cwd. `--force` retains existing overwrite semantics. `--help` does not read the config.

Use safe YAML parsing with duplicate-key rejection. Reject missing/unknown keys, invalid shapes/types, bool-as-number, null/blank required strings, malformed fingerprints, empty/duplicate IDs, invalid revisions/config version, invalid/colliding deck/model IDs, and unsafe APKG filenames. Epoch validation applies genanki's actual `int(timestamp * 1000)` arithmetic and requires the fixed ten sequential note/card IDs to fit signed SQLite 64-bit integers. Invalid configuration produces a file/key diagnostic and CLI exit 2, without traceback, before output-directory creation or publication. Do not read dotenv or interpolate environment variables.

The default output is `artifacts/config-refactor-yaml/revision-1/`. The configured APKG basename may be `repeat-check.apkg`; internal repeat-build staging must occupy a different path. Existing named outputs require explicit force; only APKG/preview/audit are published after the retained audits and independent identity comparison. Configuration path/hash, effective settings and override provenance belong in the local audit, never learner fields.

## Acceptance and scope

The shipped MVP retains the original fingerprint, five ordered IDs, revision, names, native identities, field/template/CSS definitions and full learner content. Compare exact raw fields, preview bytes and structural identities with the accepted baseline; ZIP equality is not required. Source data, JSON Schemas, renderer, historical artifacts and diagnostic omission policy remain intact.

This is still a bounded five-note exporter. Configuration migration does not implement arbitrary batches, source-deck extraction, multi-deck processing or safe live-collection updates. See [decisions](decisions.md), [executed evidence](log.md), and [tracker](../../tracker.md) for decisions, results and the pending user Anki check.

## Version-2 input-stage extension (Gate 1 accepted 2026-10-20)

The separate [source-normalization contract](../source-normalization/contract.md) now governs an implemented/tested version-2 extension anchored in the same working config shape. `load_stage_config` returns typed `StageConfig` for normalize/validate-input, with supported `source` and `normalization` settings and stage-specific missing-field requirements. Every supplied value is validated; unknown keys are not ignored. Transformation/profile logic remains Python code.

The existing version-1 loader/build API and shipped MVP YAML are preserved. `paths.input`/`constraints.input_sha256` still identify enriched bytes; `paths.source_input` identifies normalized input; `constraints.source_input_sha256` pins those input bytes separately. Input-only stages run before enriched output/hash/package exists. Full native-profile validation uses explicit source/map/raw/config fingerprints and the accepted first-five IDs.

Independent Gate 1 review/recheck passed 57/57 tests and 40 CLI checks, including count enforcement, declared future-input/schema protection and controlled malformed-sidecar errors. The acceptance manifest binds exact code/data/config. That Gate 1 acceptance covered input stages; the later accepted output extension follows below. Arbitrary source adapters remain outside scope. The earlier refactor acceptance above remains historical evidence for version 1.


## Version-2 output-stage extension (Gate 2 accepted 2026-10-20)

The [source-normalization contract](../source-normalization/contract.md#accepted-output-stage-boundary-gate-2) now also governs implemented `validate-output` and explicit `build`. The same version-2 YAML keys/settings are reused. Output validation requires both JSONLs/schemas, exactly five ordered IDs, positive revision/schema version; package/output directory and hashes may be omitted for a draft, while declared values/hashes are enforced. Build requires complete package/path settings and both actual normalized/enriched hashes.

CLI overrides retain invocation-cwd semantics. `StageConfig.declared_paths` captures immutable original path declarations, while effective `paths` reflect overrides; protected targets use both sets without downstream YAML reload. The existing `AppConfig`, `load_config` and typed builder/legacy v1 behavior remain compatible.

Independent recheck executed 70/70 tests and 26 CLI commands after F1–F3 fixes. Gate 2 pins exact code/config/evidence; the final r3 YAML binds actual source/input/output and a separate delivery namespace/directory. Original accepted Gate 1 and MVP configs remain unchanged. Agent progress stays outside YAML.

## Canonical source configuration after the pipeline refactor

configs/tango-n1-mimi.yaml is the supported v2 operational entrypoint, alongside unchanged `configs/mvp.yaml`. It references stable source-contract/fixture inputs and separate generated normalize/build destinations. YAML is still parsed only at the typed CLI boundary; finite adapter selection delegates mapping/applicability/version semantics to the source package. There is no transformation DSL or dynamic discovery.

YAML paths still resolve from the YAML parent and explicit CLI overrides from invocation cwd. Normalization authorization now uses explicitly named targets with resolved collision/protected-path/force checks, allowing root YAML to publish into a sibling run directory. Historical YAML snapshots remain untouched. Original and effective overridden protected paths stay immutable through build adaptation.

From the repository root, invoke `normalize`, `validate-input`, `validate-output`, then `build`, each with `--config configs/tango-n1-mimi.yaml`. From another cwd, supply the absolute config path; its internal relative paths retain YAML-parent resolution. Existing generated normalize/build targets require the existing `--force` option or deliberately configured fresh destinations. No per-deck pipeline script is needed. Exact refactor/review/final-verification evidence belongs to the shared job contract and [tracker](../../tracker.md), separately from historical acceptance above.
