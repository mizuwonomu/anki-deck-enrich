# Progress

## Current focus  (2026-10-28) DONE: public-repo portability accepted; final 50-file export, exact Pi worker_done/report, preserved history and terminal disposition verified -> [decisions](features/public-repo-portability/decisions.md)

### tracker.md  (living status — flags + pointers only)

## Status

- public-repo-portability: DONE (2026-10-28), technical/offline scope; no open findings or execution work -> [closure](features/public-repo-portability/log.md#final-execution-closure-2026-10-28).

- mimi-rerun-new-contract: OFFLINE DELIVERY DONE (2026-10-25), 45 notes/cards; original Orca dispatch lifecycle remains unsettled -> delivery, acceptance.

- batching-mimi: DONE (2026-10-25) for input preparation, reusable reviewed-output aggregation and scoped offline export -> [feature narrative](features/batching-mimi/log.md#featuresbatching-mimilogmd--feature-narrative-durable).

- source-normalization: DONE (2026-10-20) -> [baseline implementation/review/E2E log](features/source-normalization/log.md).
- pipeline-refactor: DONE (2026-10-21) -> [features/pipeline-refactor/log.md](features/pipeline-refactor/log.md).

## Refactor task closure

- RF-01–RF-07: CLOSED -> acceptance, independent recheck, final Luna verification.

The accepted refactor is closed. New cleanup requests below are not implemented migrations. Exact execution identities and settled lifecycle outcomes remain in the job state.

## Open debt and deferred scope

| Item | Status | Authority / required boundary |
| --- | --- | --- |
| Canonical source-Markdown runtime requirement | OPEN; deletion unsafe today | User rejects this authoring requirement. Coordinate active config/provenance/sidecar/test migration before deleting the file; preserve old acceptance and source/native linkage -> [decisions](features/pipeline-refactor/decisions.md#post-refactor-extraction-and-runtime-boundaries). |
| Missing-contract diagnostic filename | OPEN; reproduced read-only | Missing Markdown exits 2 and its message names the missing file, but `errors[0].file` points at the healthy normalized input. This source/provenance I/O case was outside the earlier F1 sidecar/schema matrix -> [read boundary](../jp_deck/input_validation.py:130), [stage wrapping](../jp_deck/output_validation.py:89). |
| Real-source batching scale | UNVERIFIED beyond the 45-note pilot | Configurable cardinality is implemented; larger synthetic tests do not establish a larger real-deck baseline, full-deck eligibility or throughput -> [executed evidence](features/batching-mimi/log.md). The single snapshot-specific Tango profile remains. |
| Source attestation | UNVERIFIED beyond the selected review scope | Fresh rerun: 85 collocations remain unverified, source_sample=[], newly generated examples and no translator source citations. Meaning/schema review passes for every record; Kanji/root verification is excluded by the mapping supplement. Prior delivery evidence remains historical -> current delivery, [selected scope](features/batching-mimi/decisions.md#accepted-output-evidence-and-replay). |
| Additional isolated regression variants | NOT NEWLY EXERCISED | Separate persisted row-deletion/duplication/serialization-only and example-specific source-sample variants remain disclosed coverage limits; do not infer exhaustive boundary coverage from the passing suite -> code review limits. |
| Historical temporary evidence | PARTIALLY RECOVERED | Current output bytes and acceptance graph have durable evidence; some historical review/query records and old /tmp links remain unavailable. Unknown query strings do not reset the cumulative source-search budget -> data-review limits, [durability decision](features/batching-mimi/decisions.md#failed-approaches-in-accepted-output-work). |
| In-code translation/full agent pipeline | NOT IMPLEMENTED | Technical replay consumes persisted enriched output; language production and semantic review remain separate -> [architecture](index.md), [translator role](roles/translator.md). |
| Orca rerun lifecycle | UNSETTLED; data delivery accepted | AGY Bash could not execute the host launcher; automatic approval review rejected abandon because process exit was unproven. Sessions remain untouched; do not infer worker_done from accepted artifacts -> run state, delivery boundary. |
| Worker/attempt/report tracking | DISCUSSION PENDING; no new implementation | Separate CLI transport success, agent liveness, attempt failures, review verdicts and artifact acceptance; define recovery rules from observed MiMi failures -> [tracking observations](features/batching-mimi/decisions.md#observed-tracking-signals-and-discussion-boundary-2026-10-26). |

## Separate existing limitations

- Linguistic evidence: UNVERIFIED -> bounded r3 review. No budget reset or additional language research is part of this refactor.
- Anki client import/reimport/layout/scheduling/media migration: NOT VERIFIED; the new export uses its configured stable identities, and offline source linkage does not preserve original scheduling/native card identity -> delivery boundary.
- Historical worker lifecycle delivery failures and retained contexts are recorded separately from artifact acceptance -> original execution state. Do not resume settled workers just to rewrite old bookkeeping.
