# Pipeline refactor handoff

### features/pipeline-refactor/log.md  (feature narrative, durable)

The 2026-10-21 extraction consolidates the completed Tango work into a baseline for the user's requested repository refactor. The implementation was validated through isolated job packets so research expectations, implementation changes, reviewer findings and accepted artifact versions could be compared independently. That separation produced useful provenance, but also left operational configs, live test fixtures, probes, launchers and copied source trees in dated job directories. This extraction records the existing boundaries and a dependency-aware next-work tracker; it does not perform the migration.

The architecture is maintained in [the index](../../index.md), rationale and assumptions in [decisions](decisions.md), and all outstanding work/status in [the canonical tracker](../../tracker.md). The accepted source workflow and its original implementation/review narrative remain in [source-normalization](../source-normalization/log.md).

## Completed producer handoff and evidence

| Producer | Completed contribution to reuse | Authoritative artifacts |
| --- | --- | --- |
| Independent researcher | Inspected the original APKG/database and note-type semantics; defined source selection, identity, conversion/exception rules and independent positive/negative expectations. Research tooling was evidence collection rather than the production normalizer. | Research result, mapping contract v1, semantic expectations, research acceptance. |
| Phase 1 implementer and technical reviewer | Implemented/rechecked the supported reader/profile, typed v2 input config, normalization/input validation stages and source-linkage/protected-publication regressions. | Implementer correction result, independent recheck, Gate 1 acceptance. |
| Translator and bounded word reviewer | Produced the approved enriched r3 artifact and resolved concrete JSON/citation/spelling findings while preserving the explicit language/source evidence boundary. | Corrected r3, bounded review, translation check. |
| Phase 2 implementer | Added v2 output validation/build integration and tests; corrected original/effective path protection, offending-file diagnostics and independent native/template test expectations after review. | Initial result, correction result, frozen corrected submission. |
| Independent Phase 2 technical reviewers | Reported initial concrete findings, then independently executed the corrected suite and real CLI/package/audit/SQLite/HTML checks and issued an accepted exact-byte recheck. | Initial review, accepted recheck, Gate 2 acceptance. |
| Orchestrator | Preserved exact session/artifact identity across interruptions, consolidated worker evidence, then executed the separate final offline E2E on accepted code and delivered the artifacts. | Final binding, E2E acceptance, delivery report, execution state. |

## Read-only inventory captured for the refactor

Inspection on 2026-10-21 found six active test files with 70 test methods. The accepted results are the previous independent runs linked above, not a newly executed suite in this extraction. No production validation, package build, worker dispatch or new source research was performed here.

The script-extension inventory (`.py`, `.sh`, `.js`, `.mjs`, `.ps1`, excluding session transcripts) contains 111 files under `jobs/`: 86 code copies in snapshot directories and 25 other job scripts. These counts describe file placement, not a claim that every script is unreferenced or safe to remove. Final Gate 2 explicitly pins `phase-2/reviewer/probe-1.py`, `recheck-1-probe.py` and `recheck-1-html-followup.py` under `jobs/tango-source-normalization-2026-10-20/`.

At the initial inventory, operational/configuration entrypoints included root MVP config, job-local input-stage YAML, output fixture YAML and final run YAML. Source/output tests then consumed job-local configuration/data/research expectations. These historical migration inputs remain preserved; current consumers use root YAML/stable fixtures as recorded in the accepted execution below.

## Outcome of this extraction

The completed source/implementation/review/E2E evidence now has one compact role-to-artifact handoff. Current architecture and intended cleanup boundaries are distinguished, and the tracker targets refactor work rather than presenting the old completed delivery as the project's next task. Only canonical documentation was changed; configs, code/tests, scripts and accepted artifacts remained in place. A future implementation assignment must read the exact [implementer role](../../roles/implementer.md), supplied source/config contracts and the tracker; its independent reviewer must read the exact [reviewer role](../../roles/reviewer.md). Reuse the existing researcher contract unless new source semantics are explicitly introduced.

## 2026-10-21: implementation authorized and dispatched

The user approved shared pipeline plus source-specific packages, then explicitly requested one common refactor job/contract, a Pi `openai-codex/gpt-6-luna` xhigh implementer through Orca, an independent same-session `gpt-6.1-sol` high technical reviewer, no speculative fallback code/bloat, and a separate final fixture/full-suite rerun by the same Luna session. The shared contract v1 and implementation plan bind both workers. The orchestrator published a byte-identical stable source contract and baseline inventories: 20 runtime/config/test files, 111 allowlisted job scripts/code copies and 371 protected historical/data/schema/artifact files. The fresh baseline suite passed 70/70 tests in 17.478 seconds; log.

The sandboxed Orca guide call failed with `UtilBindVsockAnyPort:307: socket failed 1`; the exact same binary succeeded with escalation. The CLI does not carry Pi provider/model overrides, so the coordinator created a Pi terminal with its verified `--provider`, `--model`, `--thinking` flags, checked its actual `openai-codex/gpt-6-luna` xhigh footer/cwd, and attached that existing terminal through supervised `worker-start`. Run `run_2330adf554be`, Task `task_e7756b47e86e`, Dispatch `ctx_6904608802d7`, Pi session `8c30e983-8a96-432e-a10d-54448ad60a42`. Input is accepted; implementation/review/final acceptance are not yet claimed. Current execution state owns live handles and next actions.

### Provider quota interrupted the first batch

After three empty event waits, fleet inspection showed a live Pi terminal with activity done but no `worker_done`. Its actual terminal output ended with `Error: Codex error: The usage limit has been reached` after writing migrated fixture files. The coordinator preserved the terminal/session and active Dispatch, recorded partial-state hashes, and requested quota restoration or an explicit worker configuration change. No implementation completion, reviewer dispatch, script cleanup, final Luna rerun or refactor acceptance is claimed. The earlier baseline 70/70 result is pre-refactor evidence only.

### Same-session continuation after user-corrected provider

The user explicitly selected the correct provider in the existing Pi session and requested the task be sent again. The coordinator observed `(openai) gpt-6-luna` xhigh, amended only the shared contract/assignment provider requirement, sent superseding message `msg_19ded8085f0f`, and delivered continuation input through the same terminal. Subsequent worker output proved an actual working turn: reading coordinator mail, preparing package layout, implementing adapter selection and updating the shared reader/applicability. Task, Dispatch, terminal and Pi session remain unchanged; no duplicate worker/reviewer was created. Implementation completion and verification gates remain pending.

## 2026-10-21: refactor independently accepted and final same-Luna rerun passed

Luna completed the shared pipeline/source-package migration, root YAML, stable fixture migration and byte-preserving archive of 111 scripts/code copies. Batch 1 passed 74/74 worker tests while retaining the original 70. Same-session `gpt-6.1-sol` high independently ran 74/74 and 41 CLI checks, verified native/preview/fixture/protection/archive parity and found no bloat; review 1 identified one inherited effective-filename diagnostic gap explicitly covered by the new contract.

The same Luna session reproduced F1 with red regressions and applied only existing error-context/parser/schema/linkage changes in four runtime files plus two existing test files. Fix evidence records 76/76 tests and 13 CLI cases. The same Sol reviewer accepted exact corrected bytes after independently running 76/76, 17 F1 failure probes and four healthy stages with direct native/learner parity. No outstanding finding, fallback implementation, framework, compatibility shim or dependency remains.

Only after that acceptance, the same Pi session ran the mandatory final verification: 76/76 tests, zero failures/errors/skips, 27.513 seconds; all 47 frozen entries, 20 fixture bindings, 371 original protected files and 111 archived members matched before/after. Input/raw/exception/enriched bytes are unchanged; only the canonical contract path differs in the actual source-map records. Parent integrity verification found no unexpected/missing runtime/config/test/archive file or active job executable. Final acceptance binds these exact reports, hashes and scope; RF-01 through RF-07 are closed.

The original Pi terminal had been operator-closed before F1 dispatch. Root positively confirmed exit and resumed its exact saved transcript/UUID in a new terminal, using native compaction before retrying the known failed task. After the final worker_done, an Orca runtime restart invalidated the old coordinator handle; normal `run-use` rebound the same Run to the current coordinator, replayed the same final message idempotently and acknowledged it. No task/artifact was rerun or reclassified. Zero reclaimable worker resources remain; the coordinator performed no process action on external/user-owned terminals. Exact identities/recovery receipts live in job state. Original research/language budgets, historical manifests/deliveries and unverified live-Anki/language boundaries are unchanged.

## Documentation extraction and dependency assessment

The user requested the finished-feature extraction and questioned both the canonical source Markdown copy and the extent of code-driven determinism. The extraction retained the accepted implementation summary and added rationale/boundary clarification rather than another execution diary. Current source/config/test inspection identified the existing Markdown hash pin and distinguished adapter execution from research/translation and frozen-output replay; those responsibilities are now explicit in the architecture and appended decisions.

A read-only `validate-output` probe used a temporary config with absolute original paths and only the mapping-contract path changed to a nonexistent temporary file. It returned controlled JSON exit 2 naming the missing contract in the message; the real document remained byte-identical. All 47 accepted submission entries still matched their recorded hashes. The completed 76-test acceptance remains historical executed evidence; this extraction did not rerun the suite or modify its runtime/config/fixtures/archives/evidence. Current cleanup requirements and scope limits are recorded only in the [tracker](../../tracker.md#open-debt-and-deferred-scope). Git metadata probes failed because Git does not recognize this folder as a repository; no staging or commit occurred.
