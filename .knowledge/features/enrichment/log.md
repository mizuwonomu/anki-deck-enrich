# Enrichment milestone log

## 2026-10-17 — M1 rendering decisions approved

The user approved the APKG research findings and risks, the first-collocation front policy, and exclusion of technical/debug metadata from the deck. These decisions supersede the research report's earlier open questions about collocation selection and visible technical IDs. The report remains a historical research artifact; this log records the accepted projection.

### Frozen content and scope

- Use `datasets/mvp/enriched/mvp-2026-10-16-001/revision-1.jsonl` unchanged: 5 records, IDs `mvp-001` through `mvp-005`, schema version `0.1.0`, revision `1`.
- Raw-byte SHA-256: `6c5e688bb5f512636425703417f3e6c0832d13c01c80df0a967cd7949e458d6f`.
- No translator rerun, linguistic correction, rewriting, trimming, or silent source-link repair for M1. The user selected revision 1 as the rendering baseline despite the separately recorded review findings; this does not erase those findings or certify linguistic correctness.
- Target a separate MVP deck with 5 notes, 5 cards, and one front/back card template. No reverse cards, extra cards per collocation, real-deck update, or review-history migration.
- The research recommendation is to use `genanki` for package generation, with deterministic mapping, HTML rendering and package/render audits. No implementation or package has been created yet.

### Approved front and back

- Front: only the exact `headword.expression` and the first existing `collocations[0].expression` in JSON order. Preserve the expression itself, including okurigana; do not strip text to Kanji-only characters. No reading, Vietnamese meaning, hints, or technical identifiers on the front.
- Current front pairs: 措置 / 措置を取る; 拍車 / 拍車をかける; 懸念 / 懸念を示す; 兆し / 回復の兆し; 意向 / 意向を示す.
- Back: retain all learning content at full length: reading, POS, every sense and explanation, examples with readings/translations and honest origin labels, all collocations, related terms, confusables when present, learner-relevant uncertainty text, and available source attribution/links. Do not collapse or summarize content by default.
- Group examples, collocations, related terms and confusables under the sense identified by their `sense_id`. For 拍車, the two collocations and existing examples belong to its figurative second sense; do not attach them to its literal first sense.
- First-collocation placement is provisional for the learning trial: the user may later move it to the back after reviewing learning load. Do not change this placement automatically.

### Technical metadata boundary

- Hashes, project input/object/source/sense IDs, schema/revision metadata, JSON Pointers, raw evidence-reference structures and other diagnostic payloads stay in local JSONL/job/audit artifacts. Do not render them, or add dedicated debug/raw-JSON note fields to the deck.
- This is a presentation/export projection, not deletion of source JSON fields or a schema change. Use IDs and JSON Pointers internally to preserve correct associations and construct links.
- Native Anki model/deck/note/card identities and stable GUIDs remain necessary structural package data. They are not learner-facing fields or a visible debug section. Use stable identities for this MVP namespace; this establishes no mapping to the original deck.
- Preserve useful source labels, URLs, author/attribution and license information where present. Human-readable source attribution is distinct from the excluded internal `source_id` and debug locator fields.

### Evidence and remaining verification

- Construct hyperlinks only from the existing `evidence_refs`, `origin_source_ids` and corresponding `sources[].url`, preserving their claim/sense scope. Do not create evidence links for unsupported items or reuse an example's source as collocation proof.
- The baseline contains 6 senses, 10 examples, 13 collocations, 9 related terms, no confusables, 12 source records and 2 uncertainties. Only 2 collocations have evidence references in this JSONL.
- The previous reviewer found 7 issues and attested 3 of 13 collocations; 10 remained unverified. All 26 allowed reviewer queries were consumed. Do not reset that ledger or start another lexical-evidence search as a packaging task.
- Keep separate audit coverage for fields displayed as learning content, fields used structurally, and debug metadata deliberately omitted from note fields. Omitting approved debug metadata must not be reported as accidental data loss.
- Future implementation must validate the frozen input, sense/evidence integrity, field order, HTML escaping, hyperlink mapping, expected 5-note/5-card package and stable identities. `genanki` on Python 3.13.5, package generation, and actual Anki import/rendering are still untested. The user will inspect the deck in Anki before content pruning.
- All current records have collocations. If a future record lacks one, do not invent a front value or silently drop the note; surface the record/path. A generic missing-collocation policy has not been separately approved and is not a blocker for these five records.

### Artifacts and next work

- Research job: `apkg-m1-research-job.json`.
- Luna high research report, including the user-supplied APKG-internals document and current Anki/genanki comparison: `apkg-m1-research-2026-10-17.md`.
- Translation/review job and query ledger: `job.json`.
- Revision-1 review: `review-r1.json`; summary: `summary-r1.json`.
- Ready for a separate deterministic implementer assignment after this handoff; no implementer was dispatched in this session. The approved choices above must not be reopened as unanswered questions.
- Use `.venv/bin/python`, pinned to Python 3.13.5; manage future dependencies with `uv`. Never read `.env` or `.env.*`. Do not use Git in this workspace unless the user later requests it. Wait for worker completion events, without progress polling or repetitive waiting reports.


## 2026-10-17 — M1 implementation, acceptance and final projection recorded

The earlier entry above is the approved research/handoff checkpoint, not the current implementation status. M1 was subsequently implemented and independently code-reviewed. The user accepted the detailed learning layout and chose to close the MVP, then requested one final presentation change: uncertainty issue text stays local rather than appearing among learner explanations. The current [rendering contract](../anki-rendering/contract.md) supersedes the earlier uncertainty-display requirement; translator revision 1 and its research/review history remain unchanged.

Durable knowledge is now split by responsibility: [validation](../validation/contract.md), [field audit](../field-audit/contract.md), [Anki rendering](../anki-rendering/contract.md) and [APKG packaging](../apkg-packaging/contract.md), each with linked decisions and execution evidence. The [packaging log](../apkg-packaging/log.md) owns the final artifact/provenance pointer; the final independent review records the bounded technical verdict. Current verification limits and the user's next import action are centralized in [tracker](../../tracker.md).
