# Source normalization decisions

## 2026-10-20: approved workflow and independent source acceptance

The user approved the workflow, including exactly five notes/cards, unique expressions, first collocation on the front, existing learner projection and unchanged `jp_deck/audit.py`. Both implementation phases require implementer-owned tests/fixes and independent technical review with executed verification. Tests create their own temporary render/package/audit artifacts before final E2E. Expected mapping values come from independent research; orchestrator owns shared acceptance criteria and test plans. See the workflow's test section for the complete ownership/coverage contract.

Independent research was completed in job tango-source-normalization-2026-10-20 using the original APKG and a fresh GPT 6.1 Sol high context, excluding removed source findings, global memory and the retained historical comparison values. Accepted evidence is the mapping contract, fresh expected input and orchestrator acceptance. This accepts source interpretation, not a production adapter or Gate 1 completion.

Accept numeric native note-ID ascending order within the inspected deck, selecting the first five before eligibility/type/export filtering. Research independently corroborated this sample with card IDs and stt 1–5. Scheduling/due order is unsuitable because it would replace a reviewed sample member. Accept the explicit source-lineage project-ID prefix in the mapping contract; retain original note/GUID/card/deck/snapshot linkage separately. Never replace an invalid first-five member with a later eligible note, deduplicate expressions or invent source content.

## 2026-10-20: shared config extension preserves the working exporter contract

The Phase 1 common stage contract defines the version-2 extension anchored in `configs/mvp.yaml`, preserving the version-1 build API/CLI and key meanings. New stage/source/normalization settings make input-only normalization possible without future enriched output or its hash. The loader and normalize/validate-input subcommands are now implemented and independently accepted at Gate 1; output-stage commands remain deferred. See the [implemented contract](contract.md).

`paths.input` and `constraints.input_sha256` continue to identify enriched output and its raw bytes. `paths.source_input` identifies normalized four-key input JSONL. APKG and normalized-input fingerprints have separate provenance/constraint fields. Do not repurpose the old hash, copy the MVP hash to new output or guess a future enriched hash. If the extension proves wrong, revise its contract/tests explicitly while preserving independent fixed MVP regressions.

Retain exact expression/reading linkage for this baseline and preserve source gloss after only accepted cleanup. Translation owns enrichment. A correction needed for responsible delivery requires explicit reconciliation, not silent rewriting of normalized input or relaxation of the validator.

## 2026-10-20: event-driven coordination and runner/model authority

The user explicitly requires heartbeat/completion/escalation events instead of polling partial results or terminal output. Do not create the translator agent/session until the input implementer is complete and independent review/rechecks have accepted the validated input JSONL plus YAML/config. An implementer report alone does not release translation.

Keep requested models/runners separate from reusable role definitions and verify effective model/effort before claiming a successful launch. Catalog discovery and the user's resolved model choice belong to the job ledger, not an assumption that catalog contents are permanent. The user confirmed `openai-codex/gpt-6-luna` xhigh for all implementers. This run used explicit Pi argv/session storage through an Orca WSL terminal, verified the actual startup/footer, then attached Task/Dispatch lifecycle with `worker-start --terminal`; no default-model task was used. Completed external-terminal releases were recorded as retained/no process action, with explicit next ownership.

## 2026-10-20: acceptance includes adverse boundaries and independent recheck

The first 52-test pass and faithful first-five candidate did not close the software contract: independent review found future-input/schema report clobbering, missing standalone fixed-count enforcement, malformed sidecars causing uncontrolled exceptions and missing adverse composition tests. Keep those failed-approach lessons in the reusable boundary rather than treating one successful artifact as generalized validator proof.

Accepted correction: one shared stage-aware protected-path policy preserves every declared read/input role even when output values alias it; fixed-five enforcement belongs at the dataset/stage boundary, not the single-record eligibility helper; sidecar hashes do not replace nested shape/primitive validation. Tests must exercise invalid selected members plus a valid sixth candidate and duplicate requested samples through composition, with no replacement/publication. Preserve independent source expectations and valid empty raw text while rejecting malformed structure.

The accepted recheck ran 57/57 tests and 40 real CLI commands. Original review, red/green correction and recheck evidence are separate immutable artifacts. Gate 1 releases only the tested/validated input/YAML/source linkage. The user explicitly stopped this session there and deferred translator to the next session; later output standardization/review and final E2E remain required.


## 2026-10-20: word work is separate from JSON/tooling chores

During continuation the user explicitly assigned word review to an in-session GPT 6.1 Sol medium worker and root to orchestration. The user then authorized that reviewer to directly fix output JSON/schema compatibility, citation bookkeeping and obvious spelling/kana in a new artifact; agy only checks translation/meaning. This is a scoped data correction, not permission to weaken schema files, edit software/audit/projection or rewrite translator nuance. Correction assignment and r3 report bind the exception and result. Do not send routine formatting/spelling chores back to translator or restart exhausted searches.

A generic JMdict DTD page does not establish a lexical entry or an exact compound. Reference-valid pointers can still target unsupported renderer claims (the r1 headword POS-array refs demonstrated this). Preserve truthful source limitations and remove unsupported evidence rather than invent provenance/retarget claims just to pass export. A failed source retrieval does not prove a plausible word/example false and does not authorize relabeling quoted/adapted text as generated. All five collocation budgets are exhausted at 2/2 in this run; r3 remains unverified for attestation/provenance even though concrete findings and technical checks are complete.

## 2026-10-20: keep live workers across a coordinator handoff

The user requested a handoff during Phase 2, then explicitly resumed the same Pi after an accidental abort. Resume the existing terminal/Task/Dispatch; do not create a duplicate agent or discard partial work. The coordinator may end its turn after writing durable state while the worker continues. Inspect saved state and completion mail before redispatching. A startup/footer proves model/effort for operator-created Pi terminals; null generic launch-preference fields are not a model change.

Worker-side orchestration CLI hangs must not turn translation into operating-system/process debugging. Keep data/report completion distinct from authoritative lifecycle settlement. The agy final idle turn is observed, but automatic approval review rejected fencing its user-owned live terminal twice; preserve it and record the unresolved Dispatch rather than forge completion or kill processes. The job ledger contains the incident/recovery evidence and current actors.


## 2026-10-20 — accepted output-stage and final-delivery boundaries

Gate 2 independently accepts v2 validate-output/build and its supported five-card integration after F1–F3 corrections. Effective CLI overrides must not erase protection of original YAML-declared inputs/schemas; immutable typed declared paths and effective paths form one publication boundary, including symlinks/force. Error diagnostics attach effective schema/enriched paths where those are known. Independent integration expectations include literal fields/templates and ordered note/GUID/card relationships, not only production audit success or a combined native-ID range.

Accepted recheck, Gate 2 and final E2E remain distinct evidence. Final source re-normalization uses separate destinations and byte-compares the accepted input/linkage; original Gate 1 and historical artifacts stay immutable. The final revision/hash/config are actual r3 bindings, not a proposed future hash or the old MVP fingerprint.

A complete independent report/final turn and valid code/artifact evidence can be accepted while worker-side lifecycle delivery fails. Coordinator uses its documented settlement authority with explicit delivery-failure metadata and processAction none; no worker_done is forged and no retained session is stopped. Exact Task/Dispatch/session recovery is recorded in the job state. Technical package acceptance does not erase the bounded unverified linguistic evidence or establish live Anki behavior.
