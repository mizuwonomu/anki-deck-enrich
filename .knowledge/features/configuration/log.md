# Configuration implementation record

## Execution on 2026-10-18

The orchestrator wrote one shared contract v1.1 and plan, captured pre-edit source/test snapshots and protected hashes, and ran the original 24-test suite successfully. Pi `openai-codex/gpt-6-luna` with xhigh reasoning implemented through Orca in the existing workspace. A same-session GPT `gpt-6.1-sol` high subagent independently reviewed completed output, found the repeat-path/epoch defects, and rechecked one completed Luna correction batch.

Final reviewer evidence: **36 tests run, 36 passed, zero failures/errors/skips**, using `.venv/bin/python -m unittest discover -s tests -v`. Reviewer also built through the real CLI in its own directory, reran original reproductions and boundary/publication probes, and independently inspected ZIP/SQLite/HTML without relying on exporter audit flags. Final review reports PASS with no open finding in scope. Initial review evidence remains preserved.

Final candidate and reviewer rebuild match the accepted historical package in complete raw fields, templates/CSS, model/deck identities, GUIDs/native note/card IDs and associations, 5-note/5-card counts, empty media/history and allowed empty Default metadata deck. Preview bytes are identical. Source/schema/renderer/historical hashes remain unchanged. The orchestrator separately confirmed direct readback and protected hashes in delivery verification.

## Candidate for user Anki testing

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| APKG | 86234 | `9d5e0285ceeca06f0084ca5b1f00f2e12b216ee8a9a2c4e764bca6be89a5862c` |
| Preview | 28791 | `aceab2bb55fed481795374d3627cdd09cac5004b0179dac705176f00372d919f` |
| Local audit | 8340 | `126e9e761e4acd85a47373f52884f0748a68820c83baa3196061c82f809c3239` |

Config: mvp.yaml, SHA-256 `81019cbca44d55e5a17dc63cb4662082521bde179951f405f9135f862c2ffb56`. Baseline APKG remains `32352b35502cb4ea12c6abdc44d3ff9ba6287bd69ef6a7893763fdd27c679828` (86234 bytes). Different ZIP hashes are expected/allowed; byte-identical ZIP output is not claimed.

Implementation and correction evidence: final implementer result, correction batch, job state. These are executed offline results. Agents did not import or preview the candidate in Anki Desktop/mobile. User client testing is the next step; no public artifact URL was created.

## 2026-10-20: source-input stage configuration accepted

The [Gate 1 source-normalization contract](../source-normalization/contract.md) adds typed version-2 input-stage config while preserving version-1 MVP YAML/build behavior and all 36 old regressions. New source/normalization settings and optional future-stage requirements support normalization/input validation before enrichment exists. Enriched and normalized-input hash meanings remain distinct; report publishers protect all declared input/schema/config/source roles, including future-stage paths.

Independent recheck passed 57/57 tests and 40 CLI checks after one correction batch. The manifest binds the accepted Tango YAML/input/code and actual final validation. Output-stage v2 CLI/build integration remains future Phase 2; no Tango enrichment or package was produced here.


## 2026-10-20 — Tango output-stage accepted and final E2E passed

The shared v2 validate-output/build extension was independently accepted after F1–F3 correction/recheck: 70/70 enabled tests and 26 independent CLI commands. Existing v1/API, renderer/audit, schemas, baseline tests and historical artifacts remain preserved. Separate final E2E re-normalized/validated actual Tango r3, built/audited five notes/cards and compared complete repeat native identities/preview. Gate 2, independent recheck, final E2E, delivery and limitations. No live Anki import or linguistic-attestation certification.
