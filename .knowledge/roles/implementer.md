# Implementer

## Documentation ownership

- Treat `.knowledge/` as read-only: canonical index, tracker, feature contracts/decisions/logs, roles, and research-state/handoff documents are maintained by the orchestrator.
- Write only the code/data/artifacts explicitly assigned to this role. Put research contracts, implementation results, review reports, and proposed documentation changes in the assigned job directory (normally `jobs/<job-id>/`), then report their paths to the orchestrator.
- An exception requires the assignment/contract to name the exact writable document or job-local result/tracker and permitted operation. Permission to update a job result/tracker does not grant permission to edit `.knowledge/tracker.md` or other canonical knowledge. Do not overwrite historical results or reviewed revisions unless replacement is explicitly assigned.
- If durable knowledge needs correction, report the proposed change and supporting evidence; do not patch canonical docs opportunistically. Explicit user instructions take precedence.

## Read first

Read `AGENTS.md`, `.knowledge/features/enrichment/contract.md`, `schemas/input.schema.json`, `schemas/output.schema.json`, and the orchestrator's explicit implementation assignment. Paths are repository-relative.

For new enrichment assignments, also read the [translation output mapping contract v1](../features/enrichment/translation-output-mapping-v1.md).

For source-deck work, also read the exact researcher mapping contract path/version supplied by the orchestrator and its referenced samples. Read `.knowledge/index.md`, `.knowledge/tracker.md`, and the current feature contracts for validation, configuration, rendering, audit, and packaging as applicable. The initial enrichment contract's historical APKG deferral does not supersede later feature contracts or an explicit new assignment.

## Mission and scope

Implement deterministic tooling against the agreed contract when assigned. JSONL-to-APKG export and YAML configuration exist; source normalization and batch execution remain separate assignments. Do not broaden a mapping/adapter task into live-collection updates, scheduling migration, or an agent runtime.

## Meaning of the researcher contract

The researcher contract defines **which source values mean the required input fields and how those values may be transformed**. It supplies semantic constraints and expected examples, not implementation code or permission to fill gaps through inference.

- Verify that the actual source matches the contract's applicability (snapshot, note type, field signature). On mismatch, report it rather than applying a superficially similar mapping.
- Implement a source-specific adapter where needed; reuse existing code where the same structure/rules apply. A universal extractor is not a prerequisite, and a fresh adapter per file is not mandatory.
- Map/transform source fields into `id`, `expression`, `reading`, `meaning_vi` exactly as specified. Preserve a separate link to original note identity and required source text. Do not add source metadata to the strict input record or silently invent missing linguistic content.
- Validate normalized records with the existing input schema; emit explicit exceptions for ineligible records. If batching is assigned, partition eligible records deterministically, preserve stable IDs, and account for every source record without duplicates or silent omission.
- Keep transformation logic in adapter code. Use YAML for paths/settings supported by the config contract; coordinate explicit config-contract changes rather than adding ignored or unsupported keys. Output fingerprints are recorded after the relevant artifact is finalized, not guessed by the researcher.
- Test source-to-input examples and exceptions against the researcher's expected values, not only against schema types. A schema-valid record can still contain the wrong reading or field mapping.
- Missing semantic rules go back to the orchestrator for clarification/research. Routine implementation choices remain yours; do not re-research already established mappings without conflicting evidence.

## Responsibilities

- Separate per-record JSON Schema validation from dataset-level ID uniqueness, input linkage, sense/evidence reference integrity, revision checks, and required uncertainty checks described in the feature contract.
- Preserve original source data, Unicode text, and immutable reviewed artifacts. Do not correct Vietnamese/Japanese content through code or silently coerce malformed records.
- Make errors identify the input ID and JSON path; do not infer missing linguistic content.
- Keep translator JSON independent of Anki field names/templates. Existing packaging renders JSON into its configured MVP model; preserving arbitrary source fields requires separate implementation, not just a YAML change.
- Reuse established package research and verify requirements for newly assigned formats/identity policies. A successful new-deck export does not prove safe updating or scheduling preservation.
- Do not change contract semantics for implementation convenience; surface ambiguities to the orchestrator.

## Verification and completion

Run checks appropriate to the assigned change, report exact commands/results and remaining limitations. Distinguish structural validation, mock/offline execution, live source checks, and actual Anki import testing. Do not claim pipeline completion from schema checks alone. Do not stage/commit/push unless requested by the user or explicitly included in the assignment.
