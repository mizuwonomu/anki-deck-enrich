# Anki rendering contract

### Boundary

[render.py](../../../jp_deck/render.py) projects a validated research record into escaped learner HTML. render_record returns a RenderedRecord; its ordered anki_fields are Expression, FrontCollocation and BackContent. render_preview produces a standalone inspection page from those render results. The research schema is not an Anki note type.

### Front and back

Front shows only exact headword.expression and the first existing collocations[0].expression in JSON order. Preserve the expression's characters, including okurigana. Do not strip it to Kanji characters or add reading, meaning, hints or technical IDs.

| Expression | Front collocation |
| --- | --- |
| 措置 | 措置を取る |
| 拍車 | 拍車をかける |
| 懸念 | 懸念を示す |
| 兆し | 回復の兆し |
| 意向 | 意向を示す |

Back retains full approved learner text: reading/POS, every meaning/explanation, examples with their readings/translations/origin labels, all collocations with usage, related terms and confusables when present, and useful existing source attribution/license. Content is grouped under its actual sense_id and is not summarized or collapsed by default. 拍車's existing examples and collocations belong to its second, figurative sense.

**Final projection:** uncertainties[].issue_vi does not appear in learner fields, hidden debug fields, an uncertainty section/heading, or preview. The source JSONL and local diagnostics remain intact. Field classification is defined once in the [audit contract](../field-audit/contract.md#field-dispositions).

### Evidence and text handling

- Cite only existing evidence_refs/origin_source_ids resolved against local source URLs. Attach support to the supported claim, not every nearby field. Do not fabricate references or repair URLs during rendering.
- Keep example origin labels separate from evidence attestation. A generated example is not relabeled as quoted merely because usage has support.
- Dynamic text and attribute values are HTML-escaped. Linked source URLs must be absolute HTTP(S); rendering does not fetch or validate live page content.
- A null frequency displays “chưa có số đo”, never zero. Empty collections do not authorize invented examples or comparisons.
- Model/card templates remain the packaging layer's responsibility. In the Anki back template, FrontSide repeats the question before BackContent; standalone preview is an inspection surface, not proof of Anki-client font/layout behavior.
- A record with no first collocation fails with its record/path instead of inventing a front value or silently dropping the note. A generic future partial-export policy is not established by this M1 behavior.

### Verification

[test_render.py](../../../tests/test_render.py) covers exact front pairs, source/item/sense pairing, the sense-explanation mutation, Unicode/HTML/URL handling and exclusion of diagnostics. [test_packaging.py](../../../tests/test_packaging.py) checks the stored fields and preview. Test changes follow the [shared evidence policy](../field-audit/contract.md#test-evidence-policy). The [log](log.md) records executed evidence; [tracker](../../tracker.md#outstanding-limitations) owns remaining limits.
