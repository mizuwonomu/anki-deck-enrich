# Anki-rendering decisions

### Chosen approach + why

- **Render deterministically from the frozen JSONL.** The user wanted to inspect the existing five-word translation, not compare a new translator run. Rendering must therefore preserve reviewed content and associations; it cannot “improve” language or silently fix known source discrepancies (2026-10-17, M1 instruction).
- **Use the first collocation because it is deterministic and inspectable.** The user explicitly selected JSON order for the trial rather than adding a linguistic-ranking heuristic. Selection can be reconsidered only through another user decision; renderer convenience is not a reason to move it to the back (approval).
- **Preserve full explanations before pruning.** The original trial was intended to let the user assess learning load. After viewing the output/deck, the user accepted its length because the detail helps learning and chose to close the MVP. There is no authorization for automatic summarization or collapsing (acceptance).
- **Use sense IDs internally while hiding IDs on cards.** Grouping must retain a reliable semantic key, especially for literal/figurative 拍車, but learners do not need project/source/sense IDs to study. This separates association from display rather than deleting structure.
- **Exclude uncertainty issue text after the learning trial.** The earlier approved projection displayed uncertainty notes. The user later observed that this mixed agent/reviewer interpretations into the learning deck and explicitly requested removal from audit/render/package. Preserve the research data and validation, omit the entire issue section, and record the omission locally. This is a superseded presentation policy, not retrospective evidence that the initial implementation violated its then-current contract (2026-10-17, same acceptance; final result).
- **Preserve honest source scope.** A hyperlink is useful only if it retains the original claim/origin relationship. Twelve source records do not make every collocation verified; two JSONL collocations have evidence refs. The separate bounded reviewer ledger does not authorize changing that graph.

### Assumptions it rests on

- All five approved records have collocations and resolvable references. Future arbitrary records require another scoped validation/rendering agreement.
- The learner prefers detailed Vietnamese explanations for this trial. A later reduction in learning load must be a user decision, not a performance or aesthetic shortcut.
- HTML/CSS is shared input to preview and Anki templates, but only the user/client can establish actual display/import behavior.

### Failed approaches

- Tried: detect diagnostic leakage by searching only the raw unescaped issue string in HTML → Failed because: apostrophes were encoded as HTML entities, producing a false absence result → Avoid when: comparing source text with serialized markup without parsing/decoding. Assertions were changed to visible/HTML-decoded text, preserving the absence requirement rather than weakening it. This was an implementer-reported probe blind spot; the independent reviewer later checked raw and decoded SQLite/preview values (final result, review).

### Rejected proposals and user nuances

- Visible technical IDs were proposed in research but rejected before implementation because the user considers them local debug information. Do not describe that proposal as a failed production exporter.
- “Kanji expression” was resolved as the exact headword expression, including 兆し; no Kanji-only stripping was implemented.
- The wrong-sense audit false acceptance is recorded in [field-audit decisions](../field-audit/decisions.md#failed-approaches), not duplicated here. Current rendering retained the correct pairings throughout that review.


### Known explanation citation limitation (2026-10-25)

Read-only code inspection and in-memory synthetic diagnostics established that plain `senses[i].explanation_vi` text passes schema/render/audit, but adding an exact `evidence_refs` claim targeting `/senses/0/explanation_vi` fails render audit. A control using the same source and `/senses/0/meaning_vi` passes. The [renderer](../../../jp_deck/render.py) currently emits explanation text without the citation wrapper used for meaning text; the [auditor](../../../jp_deck/audit.py) requires the declared claim-scoped links. This is a reproduced runtime limitation, not a linguistic judgment. The probe was not saved as a regression-test artifact, and no runtime correction or broad suite was performed.

The user chose translator-owned Kanji/root explanations without required web lookup/citation under the [mapping supplement](../enrichment/translation-output-mapping-v1.md). That choice does not fix citation rendering or waive evidence checks for other content. Keep this limitation separate from the already accepted package and from the pending retranslation run.
