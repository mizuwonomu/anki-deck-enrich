# Source normalization progress

## 2026-10-20: independent evaluation prepared; implementation not started

The current milestone is a supported APKG-to-input adapter with shared YAML configuration, a normalization subcommand, reusable config/input validation and automated tests delivered together. Researcher returns a versioned semantic mapping contract to the orchestrator; the orchestrator reviews it and dispatches a separate implementer. An independent technical reviewer checks code, contract and executed evidence. The existing linguistic reviewer role is a separate responsibility.

At the user's request, earlier source-specific reports, result trackers and their knowledge references were removed. Keep the separately retained five-record reference for comparison after extraction; do not supply its values or earlier source conclusions to researcher/implementer. New inspection must use the original APKG and shared contracts with a fresh context. Do not restore removed findings from conversation history or global memories.

The cleanup verified the remaining knowledge against the identified old-result signatures, checked all links in edited documents, preserved the reference byte-for-byte and validated its five records. Source packages, production code, config, tests and accepted artifacts were unchanged. No normalization implementation, fresh source inspection or production test run occurred. The cleanup receipt is temporary at `/tmp/jp-deck-source-cleanup-2026-10-20-verification.json`; its absence later does not authorize restoring deleted reports.

Keep images/media out of normalization/prototype output, preserve the input/output schema semantics and fixed MVP regression expectations, and leave `jp_deck/audit.py` unchanged. Stage-specific input execution must work before enriched output/fingerprint exists. General batch execution, live collection updates and scheduling migration remain deferred.

Scope and unresolved interface choices: flow research state. Canonical status: [tracker](../../tracker.md). Existing YAML authority: [configuration contract](../configuration/contract.md).

## 2026-10-20: final workflow agreed; two implementation/review phases

This clarification supersedes the earlier input-focused preparation description where it omitted output-stage software tests or a second implementation/review gate. Neither phase has been implemented or tested by this documentation change.

1. Researcher may write/run a bounded read-only unpacking/inspection probe under its assigned job directory. It determines package/database format and extracts raw deck/note-type/ordered-field/sample/exception facts, then authors a versioned semantic mapping contract and source-specific YAML requirements. Inspection code is evidence tooling; production readiness requires explicit implementation and tests.
2. Orchestrator reviews the mapping contract and owns the common YAML schema/stage requirements. Phase 1 implementer delivers adapter code, the per-source YAML, normalized input/source map/exception artifacts, reusable config/input validation, a normalization subcommand and automated tests. An independent technical reviewer checks against source and contract, runs checks and returns findings. Implementer fixes and rechecks before signoff.
3. Translator enriches the accepted input. Orchestrator runs preliminary output validation and a provisional build only where existing export gates permit. These checks establish the particular artifact/run, not generalized validator/test correctness or final E2E acceptance. Assign bounded linguistic review separately when in scope.
4. Phase 2 implementer completes/generalizes the output-validation/config/stage CLI boundary and reusable automated tests, covering input/output linkage, revision and sense/source/evidence references, valid/invalid fixtures, diagnostics/exit codes and rendering/package integration. Existing tests already load YAML, but fixture/expected assumptions still target MVP; reuse/refactor them and add non-MVP cases while retaining independent fixed regression expectations. An independent technical reviewer checks code/contract/coverage and runs tests; implementer fixes and reviewer rechecks as needed.
5. After applicable language corrections and finalized output/config/fingerprint, orchestrator reruns final validate/render/package/audit on reviewed code. Main/build does not run the automated test suite implicitly. Runtime validation, software tests, linguistic review, offline audit and live client checks remain different evidence.

Shared config schema/loaders, validators, CLI and test infrastructure are standardized for reuse. Per-deck YAML supplies values using that schema. Researcher owns the mapping contract for supported source note types/field signatures/semantics; implementer owns adapter code and mapping tests. Reuse an adapter across decks where applicability/rules match; supported declarative mapping changes may only need config/cases, while new transformations require an adapter extension and tests/review. A deck filename change alone does not require a fresh script or a new framework. Once standardized, later runs execute existing checks; extra implementation/review is triggered by code/config-contract changes or uncovered behavior, not every validation invocation.

Keep previous source answers and the retained comparison input out of research/implementation context. No deleted source findings are restored by this workflow description. Five-note/five-card audit/learner projection and media exclusion remain unchanged; independent inspection, code changes and new production test runs are pending.

## 2026-10-20: consolidated flow submitted for user review

The workflow review draft consolidates APKG inspection, semantic mapping, common YAML/stage requirements, input artifacts and validation, the two implementation/independent-review gates, translation and final supported E2E. The user explicitly reaffirmed the five-note/five-card baseline because `jp_deck/audit.py` fixes that cardinality; extending note/card counts is outside this milestone.

The draft also distinguishes source eligibility from export preconditions: the existing renderer needs a first collocation and the package audit requires unique expressions. Current exact expression/reading validation needs explicit reconciliation with the translator's ability to propose source corrections. The draft proposes retaining the exact-match gate for this baseline and reporting corrections separately, pending user review; no schema or validator semantics were changed.

Documentation only: no worker dispatch, fresh APKG inspection, production code/config/schema/test changes, translation or E2E execution. Proposed interfaces remain unimplemented; earlier source answers and retained comparison values remain excluded from new research/implementation context.

## 2026-10-20: test ownership and artifact-creation workflow clarified for review

Expanded the workflow review draft with contract/expected-result ownership, per-case test-plan requirements, phase-specific coverage, isolated test setup and real temporary package generation. Researcher proposes APKG mapping expected values; orchestrator accepts them and owns shared config/validation/render/package/audit acceptance criteria. Implementer owns executable tests/code/fixes, while independent technical review checks both expected results and execution. Tests cover positive/negative behavior, fixed regressions and integration as well as smoke checks. Real package/audit tests precede final E2E release-artifact generation.

The same draft now carries the user's first-five source selection without automatic substitution, config alignment with the successful MVP contract, and requested model/session assignments. Both implementation gates remain pending. Source-correction policy remains explicitly open for review. This update changes documentation only; no worker launch, code/test implementation, runtime test execution or E2E build occurred.

## 2026-10-20: execution authorized; independent research dispatched

The user approved the reviewed workflow and supplied `datasets/Tango_N1_MiMi_n1.apkg` as the source. Started job tango-source-normalization-2026-10-20, preserved a code/config/schema/test baseline and source fingerprint, and dispatched the independent researcher/probe as a fresh-context GPT 6.1 Sol / high subagent. Prior source answers and retained comparison values were excluded from its assignment. Await the completed mapping contract and independent expected cases before consolidated review and Phase 1.

The user clarified that Orca/Pi initialization belongs after research. Initial CLI guide lookups encountered a WSL bridge failure; permissions have since been restored by the user. No Orca implementation/translation worker, production code change or final E2E run has occurred at this point. Preserve the requested model routing, fixed five-note/five-card audit/projection, exact source linkage and first-five selection.

## 2026-10-20: independent research accepted; model choice pending before Phase 1

Researcher completed the fresh source/probe contract and independent first-five/semantic expectations. Orchestrator accepted source order and project-ID namespace, verified the eight research-artifact fingerprints and five raw/schema projections, and confirmed all 15 protected source/code/config/schema/test files unchanged. Evidence: research result, orchestrator acceptance. These are research/artifact checks, not production adapter tests or Gate 1 acceptance.

Prepared the common stage contract, 16-group Phase 1 test plan and implementer assignment. Config extension and accepted source/linkage decisions are consolidated in [decisions.md](decisions.md). Pre-dispatch documentation checks passed: six documents, 26 local links, 16 test-plan groups and 15 unchanged protected files; receipt.

After research, the same selected `orca-ide` bridge loaded current guides and reported runtime ready. Pi catalog checks found `gpt-6-luna` and `gpt-6.1-sol` but no requested `gpt-6.1-luna`. The user was asked to choose GPT 6 Luna xhigh, GPT 6.1 Sol xhigh, or wait for the requested name. The answer remains pending. No implementer/reviewer/translator session, Orca Run/Task/Dispatch or final build was created. Current `worker-start` help does not advertise direct Pi model/effort override, so verify the correct launch route before starting the chosen model.

The user requires event/heartbeat-based waiting, no polling, and no translator creation before completed input implementation/tests/validation plus independent reviewer acceptance of input JSONL and YAML/config. The completed researcher need not be restarted. Resumption starts from the pending model answer and saved packet; see the canonical tracker and job ledger.

## 2026-10-20: implementer model clarified; execution resumes

After handoff the user explicitly confirmed every implementer as Pi through Orca with `openai-codex/gpt-6-luna`, thinking xhigh. The model-name blocker is resolved for both phases. Resume the saved Phase 1 packet without repeating research; verify actual launch settings before task delivery. The completed one-use handoff has been consumed. Translator remains gated on independent acceptance of completed input implementation/tests/validation and YAML/config.

Created Orca Run `run_4d80baa936d9` and a job-local Pi session through an Orca WSL terminal with explicit provider/model/thinking argv. A readiness event and captured startup footer proved `openai-codex/gpt-6-luna` xhigh before task injection. Attached Phase 1 through `worker-start --terminal`: task `task_59b78afccabb`, dispatch `ctx_48f781df33a7`, terminal `term_1f42a0d5-7359-4071-b00b-b7cc2f49f58a`. Task input was accepted; await heartbeat/completion and do not infer completed implementation from dispatch acceptance. Execution state and startup/dispatch receipts retain the proof. No translator has been created.

The user subsequently set the current stopping boundary: finish input implementation/tests/validation and independent technical review/rechecks, then hand off accepted input JSONL plus YAML/config and stop. Translator is explicitly assigned to the next session. The broader workflow remains documented for that later session, but no translator/Phase 2 creation or output E2E belongs to this session.

Pi sent valid Phase 1 completion at 06:24:58 UTC, reporting 52/52 tests with no skips and actual normalize/validate-input success. Orchestrator inspected the completed batch, confirmed exact first-five object equality against the fresh handwritten oracle, froze submission hashes, and prepared a seven-file/1,985-line code review package without scope violations. These sanity checks do not replace independent technical acceptance. Reviewer `/root/tango_input_review` was dispatched fresh as GPT 6.1 Sol high for independent source/contract/code/test/CLI verification.

The completed Orca dispatch was acknowledged after its report was processed. `worker-release` returned retained/external_terminal/no process action; coordinator owns the known idle Pi context during review and may reuse it for scoped fixes. No translator/Phase 2 session exists. See job execution state and receipts for exact identities.

Independent review 1 independently reran 52/52 tests and verified original APKG/input/config/repeated sidecar bytes, but returned needs_changes on F1–F4: incomplete validation-report protected paths, missing fixed-five cardinality in minimal input validation, unhandled malformed raw-card elements, and missing adverse selection/normalization composition tests. Orchestrator checked the cited code/contract and accepted the findings, preserving original review/evidence and a 16-file reviewed baseline. Dispatched one correction batch to the same proven Pi model/context: task `task_f15261876e18`, dispatch `ctx_2ea6e1a1f763`, fix assignment. Fixes require red/green regressions, full-suite/actual CLI verification and independent recheck before Gate 1 can pass.

Correction batch 1 completed at 06:50:22 UTC, reporting red reproduction for F1–F3, 57/57 final tests, completed F4/decompression/extra-map-row cases and actual normalize/validate-input success. Candidate input/YAML/data bytes and original report/review evidence remain unchanged. Orchestrator froze a four-file/570-line fix diff and hashes, processed lifecycle release/ack, and resumed the same independent GPT 6.1 Sol high reviewer for recheck 1. Gate 1 remains pending until independent recheck; current session still ends at accepted input/config handoff, without translation.

## 2026-10-20: Gate 1 accepted; input/config handoff and stop

Independent recheck 1 accepted F1–F4 and both related coverage notes: 57/57 tests, zero skips/failures/errors, 40 real CLI commands, exact repeated input/map/raw/exception bytes and all frozen candidate hashes unchanged. Original review, red/green correction and recheck evidence remain separate. No new blocking regression was found.

Orchestrator verified all 23 reviewed fingerprints and 18 frozen submission hashes, reran the real released-config validate-input successfully, and bound Gate 1 acceptance. Released input JSONL has SHA-256 `6bdd0a5000e352046107085301ff402253c253dd251bb14c0a944b7420b8df2f`; YAML has `c81ef2df56fdb052fcd78167179dfc05c167cbd6b734d89cd0c90e4b53f69c2b`. The [implemented contract](contract.md) is now canonical alongside configuration/validation extensions and [decisions](decisions.md).

Current session scope is complete at accepted input/config; write the requested cross-session handoff and stop. Translator/Phase 2/Tango enriched output/APKG/final E2E were not started. Existing MVP packaging ran only inside preserved software regressions. All known Task/Dispatch attempts are settled and no reclaimable resource remains; the release API leaves the known external Pi context idle with explicit user/operator ownership. No Git mutation or source/schema/MVP/audit/projection mutation was performed.


## 2026-10-20 — authorized post-Gate-1 continuation

The user supplied the accepted cross-session handoff and requested continued agent assignment and supervision. The earlier session stop is fulfilled. Orchestrator reran real validate-input (five records, pass), checked all 22 released/code/source/mapping fingerprints without mismatch, confirmed the requested agy catalog model and launched translator through the same selected `orca-ide`. Receipt confirms effective `gemini-3.8-flash-high` / high with observed turn start. Task `task_9d20f40042c5`, dispatch `ctx_1bb95bd6d618`; packet/evidence and next lifecycle state are in the job ledger. No output or Phase 2 acceptance is claimed by launch.


## 2026-10-20: corrected r3 ready; Phase 2 resumed live and coordinator handed off

Agy `gemini-3.8-flash-high` / high completed translation-only checking. User-assigned in-session GPT 6.1 Sol medium reviewed r1, then directly confirmed/corrected data into r3, SHA-256 `a4556c726ca6af892134c079a64ebf8f68c844b95d1cdf532c326f2b5a083af3`. Review r3 closes eleven concrete findings and records schema/reference/render pass 5/5, no established substantive language error, and unverified attestation/provenance after the bounded query cap. No new research/correction loop is requested.

Root independently reran existing structural/reference/render checks and a provisional existing typed-builder package/audit. Direct SQLite inspection found five notes/cards and exact front pairs. Preliminary report and frozen Phase 2 packet are per-artifact/assignment evidence, not Phase 2 software acceptance or final E2E.

New Pi startup proves `openai-codex/gpt-6-luna` xhigh in a zero-context session. Task `task_aaa1bd0f2b3f`, Dispatch `ctx_7f4fb57e1745`, terminal `term_7f75e76d-3816-46f0-a8a5-8c2b72f6ebcd`, Run `run_4d80baa936d9`. User aborted during contract reading, asked for a handoff, then requested this same Pi to continue. Resume was sent and subsequent working/test-planning output observed; proof and state preserve it. No completed Phase 2 suite/review/final E2E is claimed. The coordinator writes live-worker baton and stops its own turn while Pi keeps working.


Final handoff refresh at 12:41–12:42 UTC: a fresh terminal check showed `Operation aborted` after CLI verification output, not an active working turn. Pi has modified config/main, new output_validation/test_output_stages files and red-green/test/CLI logs; result.md and worker_done are absent. No partial code/log review was performed. The live-session baton/tracker now explicitly instruct the next orchestrator to inspect/resume this exact preserved Pi conversation, not create a new one. Evidence: `final-pi-state.json`, `final-pi-terminal.json`, `handoff-mail-peek.json`, `final-partial-work-snapshot.json` under the continuation evidence directory.


## 2026-10-20 — coordinator recovery incident

The next coordinator rebound the existing Run after an Orca restart. The old Pi Dispatch is failed/revoked. A shell observation on the saved pane did not prove live agent/session identity: a recovery command was received as a prompt by a rag-project Pi. Root sent a correction; underlying pane transition remains unexplained. No Tango retry authority was attached there. Exact Tango conversation is restored in terminal `term_a6f1c936-c7fd-4acf-8402-d2da5a3ce7b7`, matching host cwd and original session/model/effort, idle with unchanged session bytes. User interrupted recovery to ask about the incident; no new worker prompt or retry Dispatch was sent after that interruption. Coordinator evidence/docs only; no new software acceptance. Incident and next action.


User explicitly authorized the restored Pi to continue after the recovery discussion. The same Tango conversation is Working under current Dispatch `ctx_249c5712998b`, Task `task_aaa1bd0f2b3f`, terminal `term_a6f1c936-c7fd-4acf-8402-d2da5a3ce7b7`; actual working screen retains `openai-codex/gpt-6-luna` / xhigh. Current-preamble injection and a Dispatch-scoped follow-up preserve existing partial code/logs. Independent technical review remains gated on the completed batch.


## 2026-10-20 — completed Phase 2 submission; independent technical review started

Pi reported succeeded completion under `ctx_249c5712998b`, with 68/68 tests claimed (57 preserved plus 11 new), real temporary CLI/package/audit evidence and complete result.md. Orchestrator read completed evidence and froze 33 files and a 972-line four-file diff in submission. Thirty-seven protected fingerprints match. Lifecycle delivery was acknowledged after release accounting retained the external Pi without process action; coordinator owns fixes routing.

Fresh independent Orca Codex technical reviewer has requested/effective `gpt-6.1-sol` / high confirmed, with observed turn start: Task `task_724a461c63c5`, Dispatch `ctx_e8024341083d`. Exact assignment is code/test read-only and requires independent suite/CLI/build/audit/SQLite/HTML checks against the frozen contract. No Gate 2 or final E2E acceptance yet.


## 2026-10-20 — Phase 2 review findings and same-Pi corrections

Independent review 1 executed 68/68 tests and 65 real CLI commands/433 checks, verdict needs_changes. F1 reproduced original YAML-declared input overwrite after an effective override with force; F2 identified missing/wrong offending filenames for UTF-8 schemas and missing-collocation build; F3 identified incomplete independent native/template test oracles. Orchestrator checked all three against the frozen contract/code/tests, froze original reports and assigned correction batch 1 to the exact same Pi (`task_1bfafe2d295f` / `ctx_b798b5269a34`). No root production/test edits.

The reviewer finished its final turn with complete reports, but its WSL bridge failed and its harness forbade outside-sandbox retry (`sandbox_approval:false`). Coordinator documented/settled this reviewer Dispatch with worker-abandon: processAction none, user-owned terminal/files retained. This records delivery failure rather than a succeeded worker_done; no agy lifecycle action was retried. The complete independent needs_changes report remains technical evidence. Same reviewer context is retained for fresh independent recheck after fixes; Gate 2/final E2E remain pending.


## 2026-10-20 — exact independent recheck resumed after user pause

User explicitly resumed orchestration after a runtime restart. Old recheck Dispatch `ctx_4430926912cf` is positively exited/revoked; root identified exact Codex conversation `01a159fd-e6cb-7182-b10c-17e67e498825` by original Task/Dispatch/model/high/cwd in its rollout, verified 43 frozen files, and restored that conversation through an exact `codex resume <UUID>` command. No new reviewer conversation or Pi implementation was launched. Same Task `task_8d2f580e0605`, current Dispatch `ctx_869c4bdffc7c`, terminal `term_867c8fe3-44d4-444a-87d0-ef1d87fd81fc`; actual Working/footer proof is recorded in recovery evidence. Workspace-write with escalation disabled is preserved. Independent recheck, Gate 2 and final E2E remain pending; original code/data/review artifacts are preserved.


## 2026-10-20 — Gate 2 accepted and final offline Tango delivery passed

The exact resumed independent reviewer accepted all F1–F3 corrections on the frozen bytes. Actual independent suite: 70/70 tests, zero failures/errors/skips; 26 CLI commands, two direct native-package inspections/audits and complete repeat identity/preview. Initial reviewer selector/coordinator-document observations were preserved and explicitly resolved; no unresolved software failure remains. Gate 2 pins 58 software/data/source/config/evidence paths plus eight review artifacts. Reviewer final turn/report is complete, but its sandbox WSL bridge could not deliver worker_done; coordinator abandoned that Dispatch after positive evidence, processAction none, retaining the exact external conversation. This is lifecycle delivery failure settlement, not a forged succeeded report.

Only after Gate 2, the coordinator executed final E2E: normalize the same source/selection into a new run path, byte-compare accepted input/map/raw/exceptions, validate input/output r3, build, invoke the unchanged post-build audit and independently inspect ZIP/SQLite/native/learner relationships, then compare complete identities and preview from a separate repeat build. All five actual CLI commands exited 0. Final counts: five inputs, five enriched records, five notes, five cards. All accepted software/data/review fingerprints still matched after execution.

Final binding/config keeps original input/YAML and prior deliveries unchanged. Delivery report provides APKG/preview/audit paths, byte sizes, SHA-256 and Explorer directory. APKG is 73,946 bytes, SHA-256 `dd594ed04124647aff806b39c99075534f3874cb5dff77bbcfb31215114128b0`. Zero reclaimable worker resources; retained contexts belong to user/operator. No public URL or live Anki import. All five collocation/example provenance checks remain unverified under the spent query budgets. Root made coordinator artifacts/docs and deterministic E2E checks, with no production/test code edits.
