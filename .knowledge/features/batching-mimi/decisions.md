# Batching MiMi decisions

## Chosen approach and why

The accepted shared contract and review binding anchor these decisions (2026-10-23). Source mapping remains the accepted adapter's responsibility; batching partitions one independently validated normalized master. This keeps selection and mapping stable across translator work units and prevents repeated first-N source selection for successive batches.

Frozen ordered IDs define actual cardinality. Batch size is a maximum, so a short final batch is valid. Exact membership, unique native/project identities and equality of all four normalized input fields are checked together: a complete-file hash proves unchanged bytes but cannot establish source fidelity or disjoint partial memberships. Expression text is not an identity key; distinct source notes must survive even when their expressions match.

The optional typed YAML batching section configures batch size and artifact location; code derives the manifest, ordered memberships and actual counts. One runtime validation contract serves CLI and the thin job script, avoiding a second correctness algorithm in smoke tests. Input preparation accepts stage-relevant configuration without inventing enriched hashes or package settings.

## Assumptions and revisit signals

- Mapping applicability remains tied to the supported source snapshot/note-type signature; a new source or unsupported value requires explicit handling
- Membership is frozen before extraction/batching; a selected blocker fails instead of silently substituting a later note. Any earlier exclusion must be explicit in the selection evidence
- The exporter retains its one-card-per-note profile; a new template/cardinality policy needs a separate contract
- Accepted technical artifacts are reusable only with their original membership/content/provenance bindings. A new configuration or source revision is not automatically equivalent
- Configurable cardinality is an implementation property; the actual real-source scale claim is bounded by the executed baseline in the [feature evidence](log.md)

## Failed approaches

- Tried: a validation script always passed the default config to the CLI -> Failed because: caller-supplied config and unknown arguments were ignored, allowing a false pass for another dataset -> Avoid when: wrapping a public validator; preserve its caller-facing argument semantics (review F1)
- Tried: protecting the configured output directory without every named build target, then adding preview/audit protection only when package settings existed -> Failed because: input-only config can already declare those targets, allowing force or symlink aliases to overwrite unrelated build output -> Avoid when: a stage accepts partial config; protect known targets from both original/effective declarations independently of later-stage readiness (review F2)
- Tried: propagating input helper failures without the effective batch context -> Failed because: schema and membership errors lost the known file/record/path information -> Avoid when: composing shared validators at a file boundary; preserve existing structured context and add the actual batch/file context (review F3)

Exact reproductions and closure remain in the independent review and accepted recheck; command matrices and hashes are not copied here.

## Nuances agreed with the user

Batching divides translation/review work; it is not a request for separate APKG deliveries per batch. The intended eventual result is one merged deck from accepted enriched outputs. Technical input acceptance does not approve language or complete that future workflow. Translator/reviewer session assignment is a later checkpoint; this extraction does not dispatch them.

## Translation/review execution boundaries (2026-10-23)

The user-approved translation-to-aggregate flow, whose acceptance, invariants and aggregation steps are now the [contract](contract.md), uses independent translator/reviewer sessions per batch, with batches progressing in parallel. An individual reviewer starts after its own batch passes deterministic validation; it does not wait for another batch. The later execution instruction requires every translation/review batch to be accepted before the aggregate implementer resumes. Execution state owns exact worker identities and hold/release authority.

AGY owns translation, necessary language-source research and assigned JSON/report artifacts. Coordinator/reviewer/code workers own deterministic validation, tests, rendering, audit and packaging. Do not expand translator work into CLI discovery, Windows/System32/process debugging or implementation/testing. A missing/hung exact lifecycle launcher is reported as a lifecycle blocker while preserving the session and translation artifacts; it does not establish artifact failure or successful worker settlement.

Unverified attestation is distinct from a contradicted construction. Preserve original quoted/adapted labels when failed retrieval does not establish authorship. Close concrete wording/provenance/bookkeeping errors without forcing stylistic rewrites or inventing support. Technical query-ledger reconciliation may supersede inaccurate companion metadata while preserving original artifacts as history; retain unknown strings, conservative historical counts and any overrun rather than erase them. Source verification remains a separate gate.

The current strict acceptance contract does not silently accept needs_human_review. An actual user disposition is required for unresolved required source checks. If a future user decision permits delivery with recorded limitations, keep original review verdicts/unverified statuses, bind that decision to exact artifacts/reviews, and explicitly contract/test any corresponding aggregation acceptance behavior. That conditional path is not implemented or approved by a generic continue instruction. See the review decision boundary.

## Consumer regression independence

Different public CLI entrypoints can share an upstream accepted-batch replay gate. Their identical rejection of bad data proves routing/replay behavior, not independent validation in each later consumer. A downstream revision-map regression needs a real persisted-input positive/negative control with correct actual input hash and a fixed independent expected map; it must reach the typed loader or standalone output body directly. A mutation that loses a fixture or triggers an earlier gate is not evidence of downstream protection. The r2 recheck records the concrete R5 case and distinguishes a coverage gap from a runtime defect.

## Project knowledge ownership

Keep this project's knowledge, trackers and handoffs under this workspace's `.knowledge/`, with operational contracts and work evidence under its `jobs/`. An inherited execution cwd or old cross-project baton does not authorize edits to another repository's knowledge/tracker. The user explicitly corrected this boundary; do not create external navigation updates for this project.


### decisions.md  (why — the expensive part)

#### Accepted output evidence and replay

We retained deterministic software for source normalization, structural/reference checks, batching, acceptance replay, rendering and export because these operations need reproducible data invariants; translators retain Vietnamese interpretation and independent reviewers supply scoped judgments. The accepted software binding (SHA-256 a5642184a7144b08c60e9a71ac48bf63d316931babf22a6a7acf104eb2af9401, 2026-10-25) and v2 contract anchor this checkpoint without a Git anchor, as requested by the user.

Acceptance is a graph of actual persisted files because status flags and mutually consistent metadata can still describe the wrong source, output or review. Frozen producer membership determines expected records; accepted outputs never define their own expected set. Per-ID revisions remain bound across the graph because one corrected record need not force relabeling or rereviewing every other record. The revision map and verified aggregate hash reach the ordinary typed builder, preserving the existing rendering/audit path rather than introducing a separate exporter. Exact serialized-byte rules are documented in the typed YAML/interchange contract.

Two review profiles exist because structural acceptance and comprehensive attestation answer different questions. `structure-and-collocation-attestation/v1` retains strict required attestation; the user selected `schema-first-sampled-source/v1` for this delivery to prioritize all-record schema/reference/render checks with a small declared source sample. The selected scope must agree in YAML, receipts and review reports. A narrower fresh review is not conversion of an older `needs_human_review` verdict, and it does not waive a concrete contradicted claim or correction-required disposition. The existing historical strict-gate discussion above remains historical; these explicit implemented profiles are the current software behavior.

#### Assumptions and revisit signals for accepted output

- Source-backed replay relies on the configured finite adapter and its accepted source/mapping signature; a new deck format or changed native schema requires a new applicability decision. Generic normalized-source fixtures must not acquire native-linkage claims
- Complete-file hashes bind bytes and relationships, not linguistic truth or human identity. New review scopes, trust/authentication requirements or new artifact schemas require explicit contracts rather than a generic accept/skip flag
- Manifest membership stays immutable after input preparation. Excluding a note requires a separately frozen selection, while correcting content requires new output/review/receipt bindings. Repeated expressions remain distinct input IDs
- The current one-card export profile and first existing front collocation remain the rendering contract. New card/template/media or scheduling-preservation requirements must be specified separately
- Structural repeat-build identity compares configured model/deck/note/card identities and GUIDs; it is not ZIP byte equality

#### Failed approaches in accepted-output work

- Tried: using the execution evidence directory's name as an acceptance receipt job_id -> Failed because: the receipt identifies the frozen producer manifest, so aggregation correctly rejected /job_id before publication -> Avoid when: an execution run has a different name from its input-preparation job; derive producer identity from the independently frozen manifest. This is a cross-cutting interchange contract, anchored by the receipt correction
- Tried: returning early for legacy strict reports whose source_sample was optional -> Failed because: a supplied sample escaped semantic validation even though omission was compatible -> Avoid when: preserving optional fields across schema versions; optional means omission is allowed, not that supplied content can bypass validation. The r2 recheck owns the closed reproduction
- Tried: preserving required work only in /tmp diagnostic snapshots -> Failed because: shutdown removed those snapshots and made historical paths unusable -> Avoid when: work must survive session or machine restarts; persist contracts, data, reports and source transcripts under the owning jobs/ and .knowledge/ trees, with /tmp reserved for disposable probes
- Tried: independently reconstructing canonical JSONL without the runtime's recursive key ordering -> Failed because: equal record objects produced different serialized bytes and the review helper's byte assertion failed -> Avoid when: checking deterministic artifact bytes; use the declared serialization contract before diagnosing a product defect. The final delivery review distinguishes the corrected helper from unchanged runtime

The existing consumer-regression independence decision above remains the reason for direct loader/body controls; its final mutation-sensitive closure is recorded in the feature log rather than restating that rationale here.

#### Nuances settled for this delivery

The user requested retaining the 青春 card without its faulty-provenance example. Removing that example, its now-unused source and dangling uncertainty was a bounded content decision, not inferred generated authorship or permission to drop examples from other cards. Its new record revision is tracked in the bound user-directed correction. Manual confirmation of 使い捨てマスク remains a human observation separate from the reviewer's independent attestation status; a tool access error does not establish a website outage or false usage.

The user explicitly requested a fresh Pi implementer and later waived further Pi confirmation after the actual post-review suite had run. Those were execution-specific overrides, recorded in software acceptance; they do not redefine future verification requirements. Historical artifact bytes and their original reports remain unchanged when canonical knowledge is updated.

## Observed tracking signals and discussion boundary (2026-10-26)

These are observations of the completed `mimi-rerun-new-contract` run, not a new tracking implementation or a guarantee about every provider/version. The user requested continuing the discussion of tracking after distinguishing report contracts from worker execution/lifecycle signals. The accepted 45-note/card offline delivery remains complete; this discussion does not reopen translation or packaging.

### Report results and interrupted attempts

A read-only recheck found four completed `review-r*.json` reports conforming to `schemas/batch-review.schema.json`, with actual artifact hashes matching each binding: batch-001 r1 `needs_revision`, batch-001 r3 `pass`, batch-002 r1 `needs_revision`, batch-002 r2 `pass`. Both uninterrupted R1 reviews produced their requested reports with clear verdicts. This is two observed R1 work units, not a measured near-zero failure rate. Language-audit companion JSON is job-local evidence with required fields; it should not be described as independently covered by the published batch-review JSON Schema.

Both native reviewer subagents later hit an explicit usage-limit execution error. Batch-001 r2 communicated the missing-に finding but never completed its formal review/language-audit reports; the coordinator independently inspected the actual reading, persisted the interim finding, and sent a focused r3 correction to the same translator. The r3 language audit explicitly records `r2_formal_report_completed=false`; final acceptance used a complete fresh r3 review. Batch-002 r2 had independent validation before interruption and completed its review reports after the same reviewer resumed. Execution failure was not reinterpreted as a review verdict or a pass.

### Signals observed at each boundary

| Evidence | What it established in this run | What it did not establish |
| --- | --- | --- |
| `worker-start` receipt: `state=ready`, `stage=input_accepted`, observed turn start | Launch/input delivery succeeded | Translation, review, or Task completion |
| `terminal send`: `accepted=true`, sometimes only `input_accepted` and provider observation `unsupported` | Input was accepted by the terminal transport | The prompt was processed or the new turn finished |
| Coordinator inbox wait: `ok=true`, `messages=[]`, `timedOut=true`, no connection loss | The mailbox query succeeded and timed out without a delivered message | Worker failure, successful completion, or process exit |
| Worker state: `ok=true`, `lastError=null`, `outcome=in_progress`, `liveness=live`, no required attention/next action | The state query succeeded and the process/agent was still observed live | Every tool executed inside the agent succeeded |
| Expanded worker output: Bash exit127, command not found / No such file or directory | The worker could not execute its Orca lifecycle launcher | Invalid translated JSONL or a failed package build |
| Native reviewer message: `Agent errored: You’ve hit your usage limit`, agent status `errored` | Explicit reviewer execution failure | An Orca quota-error representation for AGY; no AGY translator quota case was observed |
| Validated translator files, final terminal messages, and final review receipts | Actual content existence, cardinality, structural correctness, and scoped artifact acceptance | Authoritative Orca `worker_done` settlement or exhaustive source attestation |

The translators still wrote complete, structurally valid 25/20-record outputs. The missing lifecycle message was not detectable by checking JSON validity alone. Coordinator-side `ok=true` described a successful CLI observation, not successful worker work. The exact reason for a nested tool failure was available in terminal text even while the structured worker projection did not report it as a failed Dispatch.

### Recovery boundaries and remaining discussion

The coordinator used terminal final messages, file events, explicit validation and same-session corrections when normal completion reporting was unavailable. This involved operator/LLM judgment; it was not an implemented deterministic recovery state machine. User-directed continuation of artifact E2E was recorded separately from the unsettled Orca lifecycle. Automatic approval review rejected `worker-abandon` because process exit was unproven; the sessions/dispatches were left untouched. Historical handles are evidence, not proof that a handle is currently live or reusable.

Keep transport success, process/agent liveness, execution-attempt outcome, review verdict, and exact-byte artifact acceptance distinct in the tracking discussion. A future contract still needs decisions about identity/revision bindings, required completion artifacts, missing/invalid reports, explicit quota errors, stale/unknown status, heartbeat timeouts, retry/reuse authority, and escalation. No new state machine, error schema, retry policy or coordinator implementation has been approved or implemented by these observations. Current accepted-byte replay remains in `jp_deck/aggregation.py`; the production translation/agent stage remains external.

Across-run accepted/reserved note-ID tracking is a separate unresolved capability: current batching validates one frozen manifest, not a global allocation ledger. Source-evidence tracking is also separate: all 85 collocations in the delivered run are unverified because the coordinator assignment allowed zero new collocation queries, not because 85 searches failed. Historical budgets must be reconciled per construction rather than assumed exhausted for every fresh phrase. Neither adjacent topic authorizes restarting workers or source research during this discussion handoff.
