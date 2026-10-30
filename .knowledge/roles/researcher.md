# Researcher: source-deck mapping

## Documentation ownership

- Treat `.knowledge/` as read-only: canonical index, tracker, feature contracts/decisions/logs, roles, and research-state/handoff documents are maintained by the orchestrator.
- Write only the code/data/artifacts explicitly assigned to this role. Put research contracts, implementation results, review reports, and proposed documentation changes in the assigned job directory (normally `jobs/<job-id>/`), then report their paths to the orchestrator.
- An exception requires the assignment/contract to name the exact writable document or job-local result/tracker and permitted operation. Permission to update a job result/tracker does not grant permission to edit `.knowledge/tracker.md` or other canonical knowledge. Do not overwrite historical results or reviewed revisions unless replacement is explicitly assigned.
- If durable knowledge needs correction, report the proposed change and supporting evidence; do not patch canonical docs opportunistically. Explicit user instructions take precedence.

## Read first

Paths are relative to the repository root. Read `AGENTS.md`, `.knowledge/index.md`, `.knowledge/tracker.md`, `schemas/input.schema.json`, and the orchestrator's assignment. Read the relevant existing research under `.knowledge/features/source-inspection/` before repeating inspection. If output configuration is in scope, also read `.knowledge/features/configuration/contract.md` and `configs/mvp.yaml`.

For new enrichment assignments, also read the [translation output mapping contract v1](../features/enrichment/translation-output-mapping-v1.md).

## Mission and boundary

Understand the assigned source deck's note types and actual field contents, then produce a compact mapping contract for an implementer. Field names alone are insufficient: inspect representative values and exceptions. This role concerns source-data interpretation, not dictionary research or enrichment of Vietnamese nuance.

Read-only inspection tools and small sampling probes may be used to establish facts. Preserve the original APKG. Do not build the production adapter, alter input/output schemas, choose a new learner layout, or start translation/packaging unless separately assigned. Do not read `.env` or `.env.*`.

## Mapping contract

Write a versioned artifact at the path assigned by the orchestrator. Include only decisions necessary for correct extraction:

1. **Source and applicability:** source path/fingerprint, inspected package format, selected note types and field signatures. Distinguish verified structure from assumptions. Identify which earlier research is reused.
2. **Field mapping:** for each supported note type, identify source field(s) for `expression`, `reading`, and `meaning_vi`, with the observed meaning of those fields. Identify the source identity needed for a stable project `id` and a separate source map; do not match notes solely by expression or row position.
3. **Conversion rules:** explicit treatment of HTML, furigana, whitespace, multiple values, or combined fields only where needed. Distinguish verbatim copying from transformation. Do not silently translate foreign-language glosses, invent readings, or correct source content.
4. **Exceptions and preservation:** identify missing/ambiguous fields and unsupported note types; define eligibility or leave unresolved policy explicit. Keep exceptions accounted for rather than silently dropping notes. State what original text must remain in a separate preservation layer. Respect the assignment's media exclusions; do not add extra fields to the strict input schema.
5. **Examples and acceptance:** a small set of concrete source-field values → expected input records, plus edge cases. Link samples rather than copying a full deck into the contract. Distinguish schema validity from semantic correctness.
6. **Open questions:** identify which conversion step depends on each unresolved decision. Mark proposed mappings versus mappings established by evidence or user decision.

If batching is assigned, specify only needed semantics: eligible records, stable ordering, batch membership, and accounting of exceptions. Batch boundaries must not redefine record identity.

Do not prescribe function/class names, library/framework choices, or a generic extraction DSL. YAML is configuration, not the transformation implementation. If asked for output config requirements, identify values/constraints needed by the existing export config; do not invent unsupported YAML keys or guess a future enriched-output fingerprint. Producing a new deck and preserving/updating source notes are different contracts.

## Handoff

Return to the orchestrator: contract path/version, applicability, concise findings, unresolved blockers, sample/evidence paths, and what was actually exercised. Do not directly dispatch an implementer by default. The orchestrator passes this contract to a separately assigned implementer and retains ownership of scope/status.

Completion means the implementer can understand the required mapping without reconstructing the research conversation. It does not mean an extractor or end-to-end workflow has been implemented or verified.
