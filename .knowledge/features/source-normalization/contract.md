# Source normalization and input validation contract

Current selection/cardinality and input batching follow the [accepted batching extension](../batching-mimi/decisions.md). The dated Gate 1/Gate 2 first-five requirements below preserve historical acceptance; they no longer impose a general fixed-five or unique-expression runtime gate.

Status: **Gate 1 and Gate 2 accepted; final offline Tango E2E passed, 2026-10-20**. Scope is the inspected first-five Tango source/input boundary plus shared version-2 output validation/build and supported five-note/five-card delivery. Independent software review, bounded language review and user Anki client testing are separate gates/evidence.

## Authority and accepted artifacts

Source semantics and independent expectations are defined by the mapping contract, version `tango-n1-mimi-n1-mapping/v1`. Shared stage/config/test requirements are in the common stage contract and Phase 1 test plan.

The Gate 1 acceptance manifest binds reviewed code, source, data/config, tests, final validation and scope. Released paths remain in place so the YAML's relative paths keep their meaning:

| Artifact | Accepted path under the job root |
| --- | --- |
| Translator input | `phase-1/implementer/input.jsonl` |
| Stage-aware YAML | `phase-1/implementer/tango.yaml` |
| Native source linkage | `phase-1/implementer/source-map.jsonl` |
| Original selected text/native rows | `phase-1/implementer/raw-notes.jsonl` |
| Selection/exception accounting | `phase-1/implementer/exceptions.json` |
| Normalization and input checks | `phase-1/implementer/normalization-report.json`, `input-validation-report.json` |

Job root: `jobs/tango-source-normalization-2026-10-20/`. Input SHA-256 is `6bdd0a5000e352046107085301ff402253c253dd251bb14c0a944b7420b8df2f`; YAML SHA-256 is `c81ef2df56fdb052fcd78167179dfc05c167cbd6b734d89cd0c90e4b53f69c2b`. The manifest records all related hashes and exact IDs.

## Source, selection and projection

- Immutable source: `datasets/Tango_N1_MiMi_n1.apkg`, SHA-256 `275658b9dc9873ca90a56abea1440659f8a1aa4ab685d0b8716161f1b142ff06`.
- Supported profile: `tango-n1-mimi-n1-v1`, modern Zstandard `collection.anki21b`, SQLite schema 18, inspected target deck and exact supported note-type field signature. Never fall back to the upgrade-warning `collection.anki2` member. [source_apkg.py](../../../jp_deck/source_apkg.py) uses bounded decompression and temporary read-only SQLite access; the original APKG is not rewritten and media payloads are not opened or exported.
- Select the first five distinct target-deck notes by numeric native note ID before eligibility/type/export filtering. Card-ID and stt evidence independently corroborate 青春, 晩年, 葬式, 世帯, 世間. Scheduling/due order must not replace the reviewed second note.
- The project-ID prefix and source lineage come from the accepted mapping contract. Native note/GUID/model/card/deck/snapshot identity remains in separate artifacts. Do not use row, expression or stt as the unique identity, replace failed sample members, merge duplicates or invent missing content.
- Each input record has exactly `id`, `expression`, `reading`, `meaning_vi` under the unchanged input schema. The [source adapter](../../../jp_deck/sources/tango_n1_mimi/adapter.py) maps the reviewed source fields and applies only accepted cleanup; raw source text is preserved separately. A source gloss is context, not a linguistic reference answer.
- Input JSONL uses the accepted key order, compact UTF-8 JSON and one LF per record. Exactly five unique IDs/expressions are required at the input-stage boundary. Single-record helper validation remains usable for structural eligibility accounting.

The full-scope 1179-note/card accounting and outside-sample conversion exceptions are evidence about this snapshot. They do not certify other notes linguistically or establish scaled enrichment/export support.

## Implemented interfaces

[config.py](../../../jp_deck/config.py) retains version-1 `AppConfig`/build behavior and adds typed `StageConfig` loading through `load_stage_config(path, *, stage)`. YAML is parsed only at this boundary; transformation logic remains code, not a YAML DSL. Existing package/path/constraint meanings remain intact.

| Command | Implemented behavior |
| --- | --- |
| `python -m jp_deck normalize --config PATH [--force]` | Validate source/config/profile, freeze the sample, project/validate and publish the six named input/linkage/raw/exception/check artifacts. Existing generated targets require explicit force; protected input/schema/config/source paths and output collisions are refused. |
| `python -m jp_deck validate-input --config PATH` | Validate strict JSONL/schema, fixed count, unique IDs/expressions, optional expected IDs/hash, and full native/map/raw linkage when the source profile is configured. Publish the derived input-validation report only after complete protected-path checks. |
| `python -m jp_deck validate-output --config PATH` | Read-only complete normalized/enriched validation, configured five-ID set/order, revision/schema/references, declared fingerprints and optional native source linkage; JSON stdout only. |
| `python -m jp_deck build --config PATH [path overrides] [--force]` | Require complete v2 package/path/hash settings, validate effective data and protected targets, then use the existing typed builder/audit/repeat construction. |
| Existing `python -m jp_deck [--config PATH ...]` | Preserve the legacy version-1 frozen build, overrides, help and error behavior. |

Normalization uses [normalize_source](../../../jp_deck/normalization.py); standalone dataset checks use [validate_input_dataset](../../../jp_deck/input_validation.py). The supported Tango normalization config supplies source/contract fingerprints, accepted IDs, fixed selection and normalization destinations. Minimal standalone input validation may omit source/profile/expected IDs/package/enriched data, but still requires exactly five input records and both input/schema paths.

Version 2 retains `paths`, `package` and `constraints`, adding supported `source`/`normalization` sections. Unknown/duplicate keys, unsupported versions/profile/enums, malformed declared values and invalid package settings are rejected. Missing irrelevant future-stage settings are allowed. Paths resolve from the YAML's parent; legacy explicit path overrides retain cwd semantics.

`paths.source_input` is normalized input. `paths.input` and `constraints.input_sha256` still mean enriched output and its raw-byte hash. The released YAML pins `constraints.source_input_sha256`; it deliberately omits the future enriched hash. Do not repurpose it, reuse the MVP enriched hash or move the YAML alone without resolving/revalidating its relative paths.

New stage success is JSON stdout with stage/pass/counts/artifact information. Controlled failure is JSON stderr with stage/fail/errors and exit 2; normal success exits 0. Errors use stable config/source/validation/io/artifact-exists categories and available file/record/path details. Invalid argparse usage retains its conventional exit-2 diagnostic. Malformed nested sidecars must fail structurally before relationship access; a matching raw hash does not establish valid structure. Unexpected programming exceptions are not hidden by a blanket catch.

Output commands were added and independently accepted at Gate 2. The version-1 loader/legacy build remains unchanged; version-2 output stages use `load_stage_config` and adapt only a fully validated build config to the existing typed builder.

## Evidence and next-stage gate

Independent recheck 1 accepted all 16 plan groups after F1–F4 corrections: 57/57 tests with zero failures/errors/skips, including 36 unchanged baseline regressions, and 40 real CLI commands. It verified source/input/config/data hashes, adverse composition, complete report-path protection, minimal-config count enforcement, controlled nested-sidecar failures and the bounded decompression/extra-map-row cases. Original review and correction red/green evidence remain preserved separately.

Orchestrator verified the 23 reviewed fingerprints and reran the real released-config validate-input command before binding the acceptance manifest. This accepts faithful normalized input/config and code behavior within this profile; it is not language approval, enriched-output acceptance, a Tango APKG, final E2E or live Anki import evidence.

The user-authorized continuation completed the approved broader workflow, preserving exactly five notes/cards, the accepted learner projection and unchanged `jp_deck/audit.py`. Gate 1 evidence above remains historical input-stage acceptance; current software/delivery evidence follows below.


## Accepted output-stage boundary (Gate 2)

[output_validation.py](../../../jp_deck/output_validation.py) supplies `validate_output(config: StageConfig)`, typed path overrides, protected build targets and complete `AppConfig` adaptation. It reuses existing input/schema/semantic/reference validation and the unchanged renderer/builder/audit APIs. No new YAML format, automatic agent runtime or arbitrary batch support is introduced.

| Stage | Required fields | Draft/unused values |
| --- | --- | --- |
| validate-output | Both JSONLs and schemas, exactly five ordered configured IDs, positive revision and schema version | Package/output directory and final hashes may be absent; every declared value/hash remains validated. |
| build | All paths/package settings and both actual normalized/enriched hashes, five ordered IDs, revision/schema | Optional native profile/sidecars retain their pairing/applicability checks. |

The complete source set must equal the assigned set; source line order alone is not identity. Enriched order follows configured IDs, headword expression/reading match source exactly, and source gloss remains context rather than an expected Vietnamese answer. Empty collocations may validate but block the unchanged renderer/build; no content is invented or dropped.

`validate-output` publishes no disk report or package. Build overrides use invocation-cwd paths and are validated against effective hashes/native linkage. Immutable typed `declared_paths` preserve original YAML declarations; targets are checked against original and effective input/schema paths, config, source/contract/sidecars and each other, including resolved symlinks. Force permits only the three generated deliverables. Expected schema/render failures retain actual effective file and available record/path diagnostics, JSON stderr and exit 2.

Independent recheck closed F1–F3 after the same Pi correction batch: **70/70** tests (57 protected baseline plus 13 output-stage tests), **26** real CLI commands, two independently inspected/audited native packages, and zero unresolved failed software checks. Initial probe-selector/coordinator-document observations are explicitly classified with preserved raw evidence and focused successful followup. Gate 2 manifest binds exact accepted bytes and separates artifact acceptance from failed worker-side lifecycle delivery.

## Final offline delivery

Final E2E ran after Gate 2 on reviewed code. Separate re-normalization reproduced accepted input/map/raw/exception bytes; input/output checks, five-note/five-card build, existing post-build audit and complete direct repeat native identity/preview checks passed. Final enriched revision 3 has SHA-256 `a4556c726ca6af892134c079a64ebf8f68c844b95d1cdf532c326f2b5a083af3`; final config/binding preserves the original Gate 1 YAML.

Use the delivery report for APKG/preview/audit paths, fingerprints and limits. All five collocation attestations/example provenances remain unverified with spent search budgets. No live Anki import, scheduling/source-deck/media migration or byte-identical ZIP guarantee is claimed.

## 2026-10-21 refactor boundary

The shared refactor contract and independent recheck govern current source/stage composition. Root Tango YAML is the operational entrypoint; stable fixtures replace active test dependencies on dated jobs. The source evidence entrypoint (local-only) distinguishes the immutable runtime contract copy from original research navigation.

Shared stages select a finite registered adapter and use configured snapshot/selection fingerprints; source semantics/raw/native linkage belong to the adapter. Normalization writes only explicitly named targets after resolved collision/protected-path/force checks, independently of the YAML directory. Relative YAML paths still resolve from the YAML location. The v1/v2 CLI, five-card schemas/learner projection and native identities are retained. Existing JSON/JSONL/schema/shape errors carry the effective file and available record/JSON Pointer through stage wrapping, using existing error types.

Historical input/raw/exception/enriched bytes remain unchanged. Relocated maps may change only configured source/contract path values, with full semantic/native equality checked independently. Historical YAML/manifests/deliveries remain in place. Archived job code resolves through the original-path/hash index; current runtime/tests do not import it. Final same-Luna verification and closure belong to [tracker](../../tracker.md).
