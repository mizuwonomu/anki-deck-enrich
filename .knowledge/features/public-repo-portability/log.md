# Public repository portability execution narrative

## Implemented and independently reviewed

The refactor retires the implicit/default-MVP CLI and requires explicit stage configuration. Public regression data is fabricated and self-contained; the real Tango fixtures, operational configs, datasets, reviewed translations, run evidence and delivered packages remain local. The public/local boundary describes the reviewed 50-file public selection.

New persisted paths resolve against the final file that declares them, including staging publication. Batching uses manifest v2, aggregation provenance/report v2, and package audit v3; valid legacy absolute evidence keeps its existing interpretation. YAML paths remain YAML-relative, CLI build overrides remain cwd-relative, and resolved-path publication protections remain in force. Source Markdown/profile requirements and live Anki behavior were not generalized or removed.

Independent native Sol/high review accepted candidate r4 in the final code review. All CP1, CC1, CR1 and CR2 findings were closed. Fresh independent verification included 134 tests, source-free and production-native synthetic relocation E2E, meaningful guard mutants and legacy-v1 replay. The real 45-note private replay retained exact ordered IDs, 25+20 membership, r3/r2 revisions, complete payloads, aggregate bytes and per-GUID learner fields/card associations/preview. The independent historical-preservation check matched all 1050 protected files. Rebuilt APKG container bytes differ; package content and identities are the verified boundary.

The sole subsequent edit adds `*:Zone.Identifier` to `.gitignore`. The final metadata-delta review accepted this one-line change: the final selection has the same 50 files and the other 49 records are identical. The final public manifest is SHA-256 `4448c301d7ad2933b7ed95818d1f15f2423e7242958e0a674c9b02f6d95b2e1b`.

## Review decisions that must survive a session clear

- Synthetic native regression must exercise the actual production adapter, raw/source-map validators and downstream native boundary under narrowly scoped test-only fixture bindings. Reimplementing these in a toy adapter can leave production gates untested even with a green suite.
- Mutation kills must show the intended behavior changed. A default no-force `FileExistsError` does not establish protection under `force=True`; a missing fake YAML or different error wording does not establish rejection before reading a valid private target.
- Export checks cover symlinked allowlist roots, intermediate ancestors and directly selected config-file parents before traversal/content reads. Source-map path identity is tested with valid wrong targets and a changed owner, after rebinding outer hashes.
- Final-file ownership applies separately to native linkage in report and provenance. A report-unit test alone does not replace source-backed relocation through every downstream consumer.

## Final execution closure (2026-10-28)

The refactor is **accepted and closed** in the coordinator acceptance. The exact final Pi Task `task_ecf5c19f099f` / Dispatch `ctx_3fcb2981bcb3` delivered succeeded `worker_done` `msg_348a6bbc612d`. The coordinator verified both final reports, all nine attached log hashes and the declaring clean-copy import before accepting that settlement. A copied candidate hash in the Markdown was corrected before the final delivery; JSON/code bindings were unchanged.

The resumed coordinator freshly checked all 50 public source/export records, the unchanged 33 Python hashes, both private 51-file trees and all 1,050 protected historical files, with zero mismatches. The clean-copy suite log records 134 passing tests; the three private read-only validator logs record exit 0. These existing executed results were read and hash-bound during this continuation, without another broad suite/private build. The final private oracle confirms 45 complete records, ordered IDs, r3/r2 revisions, 25+20 membership, removed-example count, GUID fields/card associations, aggregate and preview. See report binding and fresh byte verification.

The unread handoff message proved to be an old exact-Dispatch heartbeat, not completion. It was processed before acknowledgement. Normal approval review became available; the coordinator then resumed the same existing Pi session after its Subscription Sharing interruption. Existing final logs were preserved after a prior duplicate-log `FileExistsError`; no replacement worker, provider or model was introduced. Recovery receipts preserve this distinction.

The final delivery was acknowledged only after report and terminal disposition checks. Orca reports the Dispatch completed; `worker-release` returned retained / external_terminal with processAction none. No terminal remained reclaimable, and the coordinator inbox was empty. This settles ownership without claiming process exit. Exact receipts are in lifecycle closure; execution state is the operational entrypoint. The consumed cross-session baton was removed after durable closure.

No staging, commit, publication, new translation/source attestation or live Anki verification was authorized or performed as part of these acceptances. The user will make the comparison image; it is not an outstanding software deliverable.
