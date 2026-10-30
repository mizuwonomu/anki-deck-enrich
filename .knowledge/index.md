# Project architecture

### index.md  (current architecture — structural, durable)

The enrichment pipeline is source APKG/profile -> adapter normalization -> validated master and frozen input batches -> external translation -> deterministic output validation and scoped independent review -> immutable batch acceptances -> deterministic aggregate/provenance -> render, build and offline package audit. Runtime code lives in `jp_deck/`, reusable tests and fixtures in `tests/`, operational YAML in root `configs/`, and execution contracts/reports/data in `jobs/`. `batching.py` owns frozen input partitioning; `aggregation.py` replays actual manifest, source, schema, review, disposition and acceptance bindings before publishing or validating aggregate bytes. `validate-output` and `build` consume that verified aggregate with per-ID revisions and the existing renderer/package/audit path. Translation and linguistic judgment remain external stages; the runtime consumes persisted reviewed JSONL. The [accepted flow decisions](features/batching-mimi/decisions.md#accepted-output-evidence-and-replay), [execution narrative](features/batching-mimi/log.md#featuresbatching-mimilogmd--feature-narrative-durable) and [tracker](tracker.md) define the current boundary and outstanding work.

Cross-cutting acceptance boundary: producer identity, review scope, expected per-record revisions and actual file hashes form one producer-to-build contract. Optional legacy review fields are validated when present. See [accepted-output decisions](features/batching-mimi/decisions.md#accepted-output-evidence-and-replay) for the corresponding failure modes.

Cross-cutting provenance dependency: the configured source-contract Markdown is currently read and hashed by source-aware stages, and its path/version/hash appear in source-map validation. Adapter code executes the mapping; Markdown is not interpreted as transformation logic. This dependency on a knowledge artifact still exists despite the source-package refactor. The [post-refactor decisions](features/pipeline-refactor/decisions.md#post-refactor-extraction-and-runtime-boundaries) explain the deletion/translation boundaries; the [tracker](tracker.md#open-debt-and-deferred-scope) records the user's requested direction and unimplemented cleanup.

Cross-cutting publication rule: named preview/audit targets remain protected when an input-only config declares a build output directory without package settings; the APKG filename is additionally protected when known. Original/effective paths, symlink aliases and force remain inside this boundary. See [the reviewed publication failure](features/batching-mimi/decisions.md#failed-approaches).

YAML location determines relative-path resolution; explicitly configured named targets determine normalization publication authorization. Resolved protected paths, collisions and force checks run before publication. Other durable safeguards: [sense-scoped audit expectations](features/field-audit/decisions.md#failed-approaches), [diagnostic omission from learner content](features/anki-rendering/decisions.md#chosen-approach--why), and [worker identity/cwd provenance](features/apkg-packaging/decisions.md#cross-cutting-delivery-failures).

## Purpose and authority

Enrich Japanese vocabulary with Vietnamese explanations and traceable dictionary evidence. Researcher owns source interpretation, translator owns Vietnamese nuance, implementer owns assigned code/tests, independent reviewer owns scoped verification, and orchestrator owns canonical knowledge. Read the exact [orchestrator](roles/orchestrator.md), [researcher](roles/researcher.md), [implementer](roles/implementer.md), [translator](roles/translator.md) or [reviewer](roles/reviewer.md) role for the assigned work.

Software validation, learner-content projection, bounded source/language review and Anki client behavior are separate contracts. Dataset cardinality and package audit now follow configured identities; the original five-note delivery remains a frozen regression baseline. The [batching checkpoint](features/batching-mimi/log.md) records real-source input evidence separately from synthetic variable-count export tests. This workspace is the Git repository; `.gitignore` is the public/local boundary, and dated decisions plus immutable artifact fingerprints remain the evidence anchors.

## Current layout

~~~text
configs/mvp.yaml                 # Retained v1 operational configuration
configs/tango-n1-mimi.yaml        # Preserved v2 five-note operational baseline
configs/batching-mimi.yaml        # Accepted input-batching pilot configuration
configs/mimi-enrichment.yaml      # Reviewed-output aggregation and final export configuration
schemas/                         # Input/output and review/acceptance/provenance schemas
jp_deck/                         # Runtime CLI, typed config, reader/profile, validation and export
  config.py                      # YAML boundary and typed stage/build settings
  source_apkg.py                 # Supported modern APKG reader
  sources/                       # Finite adapter selection, no dynamic discovery
    tango_n1_mimi/adapter.py      # Mapping/applicability/raw/native linkage
  normalization.py               # Shared source-to-input orchestration and named publication
  validation.py                  # Shared record semantics plus typed builder dataset loader
  input_validation.py            # Input-stage/native linkage checks and report publication
  output_validation.py           # Output-stage orchestration and protected build adaptation
  batching.py                    # Frozen-membership partitioning and persisted batch validation
  aggregation.py                 # Accepted-output replay, deterministic merge and provenance
  render.py, packaging.py, audit.py
tests/                           # Public regression/stage tests with synthetic data
  helpers/                       # Synthetic records, APKG generation and native-stage helpers
  fixtures/synthetic/            # Public fabricated input/output/config fixtures
  fixtures/tango_n1_mimi/         # Preserved real research fixtures, local-only
configs/synthetic-demo.yaml      # Public explicit-config demonstration
datasets/                        # Original source APKG and preserved datasets
jobs/                            # Historical/current reports, config snapshots and run evidence
archives/                        # Frozen job-code archive and original-path/hash index
artifacts/                       # Delivered APKG/preview/audit and preserved historical outputs
.knowledge/
  roles/                         # Portable role ownership and execution instructions
  sources/tango_n1_mimi/          # Legacy hash-pinned contract dependency, local-only; removal is tracked
  features/                      # Contracts, decisions and evidence narratives
  handoffs/                      # Local disposable cross-session notes and extraction templates
  tracker.md                     # Current refactor status, next tasks and open debt
~~~

The public repository is this workspace filtered by `.gitignore`, which replaced the earlier allowlist exporter. It contains runtime/schema code, synthetic tests/config, the README, dependency metadata and `.knowledge/` guidance. Real operational configs, datasets, job evidence, packages, `.knowledge/handoffs/`, `.knowledge/sources/` and real fixtures remain local. The historical archive-integrity test is preserved outside public discovery under `jobs/public-repo-portability/local-only/`.

Knowledge files cite private evidence (`jobs/`, `datasets/`, `artifacts/`, `archives/`, `handoffs/`, operational `configs/*.yaml`, real fixtures and session transcripts) as plain-text historical anchors, not links. Those artifacts are not in the public repository; treat the named claims as recorded decisions rather than sources to open.

## Validation and normalization boundaries

| Component | Current responsibility |
| --- | --- |
| [validation.py](../jp_deck/validation.py) | Strict JSONL/schema/ID/source/reference/JSON Pointer semantics, typed builder dataset loading, and existing error types carrying optional effective file/record/path context. |
| [source adapter](../jp_deck/sources/tango_n1_mimi/adapter.py) | Reviewed field conversion/applicability, configured native identities, raw/source-map construction and source-specific linkage/shape validation. |
| [input_validation.py](../jp_deck/input_validation.py) | Schema, unique-ID and configured-membership checks, effective file/record/path diagnostics, publication protection and adapter-delegated native verification. |
| [output_validation.py](../jp_deck/output_validation.py) | Composes input checks, record/revision validation, effective diagnostics and protected build targets; aggregation-mode validation first replays accepted aggregate evidence. |
| [normalization.py](../jp_deck/normalization.py) | Consumes `StageConfig`, honors configured exact source identities, delegates semantic conversion, validates and publishes named input/raw/map/exception/report targets. It does not generate YAML. |
| [batching.py](../jp_deck/batching.py) | Splits the validated master once; checks persisted batch schema, exact/disjoint membership, complete normalized record equality, provenance/hash bindings and protected publication. |
| [aggregation.py](../jp_deck/aggregation.py) | Checks the frozen source/batch and accepted-output evidence graph, preserves complete records in manifest order, publishes named aggregate/provenance/report targets and revalidates persisted bytes for downstream consumers. |

Aggregation-mode output validation and the typed builder replay accepted aggregate provenance before loading the dataset with its verified hash and exact per-ID revision map. Legacy scalar-revision configurations retain their existing path. Shared upstream checks and consumer-local validation are separate layers; public CLI rejection alone does not prove the later layer was reached.

## Feature authorities

| Area | Contract and durable context |
| --- | --- |
| Public repository and CLI/path portability (accepted and closed) | [Decisions](features/public-repo-portability/decisions.md), [execution narrative](features/public-repo-portability/log.md) |
| Input batching, reviewed-output aggregation and export | [Contract](features/batching-mimi/contract.md), [decisions](features/batching-mimi/decisions.md), [evidence](features/batching-mimi/log.md), [status](tracker.md) |
| Current refactor direction / handoff | [Decisions](features/pipeline-refactor/decisions.md), [completed producer handoff and inventory](features/pipeline-refactor/log.md), [progress](tracker.md) |
| Source mapping, normalization and stage workflow | [Contract](features/source-normalization/contract.md), [decisions](features/source-normalization/decisions.md), [execution narrative](features/source-normalization/log.md) |
| Configuration | [Contract](features/configuration/contract.md), [decisions](features/configuration/decisions.md) |
| Record validation | [Contract](features/validation/contract.md), [decisions](features/validation/decisions.md) |
| Field/sense/package audit | [Contract](features/field-audit/contract.md), [decisions](features/field-audit/decisions.md) |
| Learner rendering | [Contract](features/anki-rendering/contract.md), [decisions](features/anki-rendering/decisions.md) |
| APKG construction | [Contract](features/apkg-packaging/contract.md), [decisions](features/apkg-packaging/decisions.md) |
| Language/evidence semantics | [Enrichment contract](features/enrichment/contract.md), [milestone history](features/enrichment/log.md) |

## Evidence entrypoints

Current reviewed-output software is anchored by the candidate binding, independent code recheck and software acceptance. The selected real-data run has separate delivery acceptance, executed E2E, independent package review and artifact handoff. These bind the original operational bytes; this documentation extraction does not rewrite them.

The [producer handoff](features/pipeline-refactor/log.md) maps researcher/worker responsibilities to their exact artifacts. The Gate 1 manifest, Gate 2 manifest and final E2E manifest are separate historical acceptance records. The delivery report owns local APKG/preview/audit paths and fingerprints. Refactoring must produce new evidence for changed code rather than rewriting these records.

The current refactor has frozen corrected bytes and independent acceptance; job state tracks final same-Luna verification and closure. The local-only source evidence entrypoint `.knowledge/sources/tango_n1_mimi/` holds the immutable contract snapshot and original research context. Original executable job paths resolve through the archive index; archived code is evidence, not a runtime import.
