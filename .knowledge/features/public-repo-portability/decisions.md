# Public repository portability decisions

## Status and authority

The user confirmed the following design decisions on 2026-10-27 after reviewing the fixture/helper and CLI portability research state. These decisions supersede its earlier open choices about the legacy CLI, public data inclusion and relative paths. The user subsequently authorized refactor execution: one Pi worker using OpenAI `gpt-6-luna` with `max` reasoning through Orca, and an independent `gpt-6.1-sol/high` native subagent in the coordinator session. The coordinator owns canonical knowledge. The user later explicitly requested checkpoint-based Pi session rotation: persist an exact worker checkpoint, stop the old session, then launch a fresh Pi with the same provider/model/reasoning from that checkpoint. Never overlap code writers; corrections and final verification belong to the authoritative continuation. No staging, commit or publication is authorized. Before/after assets are explicitly user-owned.

## CLI contract

- Retire the legacy CLI entry point and its implicit MVP configuration. Public compatibility with that invocation is no longer required.
- Standardize the existing stage commands around explicit YAML configuration: `python -m jp_deck <stage> --config configs/<name>.yaml`.
- Keep operational YAML under root `configs/`. Public examples and test configurations must resolve without historical MVP/jobs or machine-specific roots.
- Preserve substantive validation, rendering, packaging and publication-protection coverage through the supported interface and self-contained fixtures. Tests asserting intentionally retired CLI behavior may be retired explicitly; removing a data dependency alone is not a reason to lose coverage.

## Public data and illustration boundary

- All real data stays local: source APKGs, real normalized/raw/enriched JSONL, real run manifests, reviews, receipts and other job evidence, and delivered artifacts. The user explicitly confirmed that this includes data in `datasets/` and `jobs/`, not only `artifacts/`.
- The public repository contains code, self-contained synthetic fixtures, documentation and a comparison image asset. Do not turn real translated output into a public fixture to bypass the data boundary.
- Showcase the source and enriched result through an image asset under `docs/assets/`; select matching vocabulary content so the comparison is meaningful. The user will create this asset; worker completion does not depend on it. The asset is an illustration, not a reproducible public real-data delivery or proof of live Anki import.
- Keep original accepted snapshots and their required frozen inputs/evidence locally, unchanged. Exclusion from public commits does not imply local deletion.
- Real-data download, redistribution or public package delivery is not part of this migration. Attribution remains relevant to the comparison asset; no source distribution permission has been established by these decisions.

## Relative paths and replay contract

- New persisted manifest, receipt and provenance references use relative paths resolved against the file that declares each reference. Paths inside YAML continue to resolve against that YAML; any retained CLI path overrides resolve from the invocation cwd.
- Keep explicit absolute input support and internal resolved-path protection. The goal is relocatable persisted bindings, not banning absolute paths inside the implementation.
- Inventory every producer and consumer before choosing the precise migration/version mechanism. Do not silently reinterpret historical receipts or change accepted historical bytes.
- Produce separately identified portable evidence for migrated metadata. Recompute and verify affected metadata/hash bindings through the dependency graph; this does not grant new linguistic approval.
- Relative paths are only one part of reproducibility. Preserve frozen ordered IDs, native lineage, batch membership, complete reviewed content, per-ID revisions, review scope and content fingerprints. Reject changed or inconsistent replay inputs.
- The private MiMi baseline remains 45 notes, batches 25+20, with batch-001 r3 and batch-002 r2. Larger real-source execution remains unverified.

## Verification boundary for the implementation plan

- The public tree must run meaningful regression and deterministic E2E with synthetic fixtures in another clean location, without access to local real datasets, historical jobs, archives or delivered artifacts.
- Separately verify the migrated real 45-note replay with private inputs and new portable evidence. Keep this result distinct from the public synthetic E2E and from the immutable historical acceptance.
- Test resolution from a different invocation cwd and after relocation, and retain protection against target aliases, collisions and unintended overwrite.
- Inventory historical archive-integrity checks and delivery-verifier preservation assertions separately from runtime regression. Local history remains preserved; its existence must not be a hidden public test dependency.
- No translation/source research, live Anki validation, new orchestration implementation or historical worker cleanup is included.

## Implementation freedom and evidence

Fixture/helper layout, the exact comparison asset path, migration mechanics and metadata versioning are implementation choices within the contracts above. The executed candidate supplies the behavior/coverage disposition, producer-to-consumer path inventory, public-file inclusion manifest and separate public-synthetic/private-real evidence. See the [execution narrative](log.md) and public/local boundary; final worker lifecycle/report binding remains separate from software review acceptance.

Documentation inspection also found that the current architecture entrypoint links to `archives/job-code-2026-10-21-index.json`, while `archives/` is absent from this checkout. Reconcile such historical links during public documentation preparation; this decision update did not reconstruct or delete archive contents.

## Verification decisions established during review

Public synthetic native tests must call the production conversion/linkage code under scoped test-only fixture constants, and leave default production applicability strict. Retain consumer-specific publication and diagnostic boundaries, not merely shared preflight checks. Force-protection probes use `force=True`; exporter symlink probes supply a valid private target with the same basename and verify no content read. Versioned owner-relative metadata is checked after relocation with distinct report/provenance owners and with actual native source linkage. These requirements and their independent mutation evidence are recorded in the [execution narrative](log.md).
