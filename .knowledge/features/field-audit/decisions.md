# Field-audit decisions

### Chosen approach + why

- **Separate visible, structural and deliberately omitted fields.** A blanket requirement to show every JSON scalar would leak operational details and, under the final policy, reviewer uncertainty text. A blanket deletion would lose local evidence. Disposition therefore records the approved projection while source content counts remain source counts (2026-10-17, metadata decision, final audit/report).
- **Check relationships, not just presence.** The learner can receive every original character and still learn the wrong sense if an explanation or translation is attached to the wrong item. Audit therefore checks sense text, item groupings, article-level field pairing and claim-bound source links. This rationale is backed by a reproduced failure, not only a hypothetical risk.
- **Use a focused mutation regression.** One canonical 拍車 record already has two senses. Corrupting only the rendered explanations makes the association failure observable without copying a new dataset. Fixed expected source pairs supply an independent oracle. This added the 24th test while leaving the previous 23 intact (review, follow-up).
- **Inspect actual output independently.** A builder-generated audit flag cannot independently prove that builder's serialization is correct. The reviewer read ZIP/SQLite directly and the existing integration test was later extended to inspect stored fields for issue-text absence. The final comparison proved that each new back equals the old back after removing exactly the uncertainty section; other learning content was unchanged (final review).
- **Treat URLs as claim-scoped evidence.** The frozen JSONL links two collocations; the historical reviewer separately attested three. Importing that third judgement into the renderer would silently change the frozen evidence graph. Keep the ledger/report separate, preserving the user-selected content baseline.
- **Keep test reasoning proportional.** The user explicitly asked for meaningful schema/type/field/character/render checks, an explanation before test changes, and no unauthorized skips. The [test policy](contract.md#test-evidence-policy) records the exact operational consequence (2026-10-17, test scope, five questions and no-skip direction).

### Failed approaches

- Tried: accept a render when every explanation appears somewhere on the back → Failed because: swapping the two 拍車 explanations in both back_html and sense_sections still passed the original audit → Avoid when: substituting global text coverage for sense association. Reviewer and coordinator independently reproduced the gap; the delivered APKG itself had correct pairings. The fix checks meaning_vi/explanation_vi inside their own sections, with red-before-fix/green-after evidence (original finding, fix report). This is a cross-cutting lesson for rendering/export checks.
- Tried: mutate the source record's example translation before rendering and expect a pairing failure → Failed because: the renderer correctly rendered that newly changed source, so there was no source/output mismatch → Avoid when: the expected input and output are altered together. The fixture was corrected to corrupt rendered output against the unchanged record. This was a test-oracle mistake, not a product defect (implementation account).

### Assumptions and user nuances

- Text checks use whitespace normalization, substring presence and known HTML structure; they are bounded consistency checks, not a semantic language model or general-purpose HTML correctness proof.
- The final omission of issue_vi is owned by [rendering policy](../anki-rendering/decisions.md). Audit preserves that boundary and rejects reintroduction; it does not erase uncertainties or revise translation findings.
- A code-review finding and a linguistic-review finding have different authority. Resolving an audit gap did not resolve the seven historical language/evidence findings, nor authorize another dictionary search.
