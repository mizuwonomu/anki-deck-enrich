# Anki-rendering implementation record

### How it was actually done

Research mapped the existing five JSONL records into one front/back card per word. The user approved first-collocation fronts, full uncollapsed back content and local-only technical metadata. Pi Luna implemented escaped HTML with sense-grouped learner content, source labels/links and a standalone preview. The initial engineering review found an audit weakness rather than an actual wrong-sense rendering in the delivered deck.

The user then accepted the detailed output and closed the learning-layout MVP, with one final change: reviewer uncertainty text should remain outside the deck. Luna removed that display section and its unused styling, changed the expected-visible audit policy, and extended existing render/package assertions. The source remained translator revision 1; the final directory is a presentation variant, not revision 2.

### Outcome and evidence

- Research report: proposed mapping and risks, not a runtime/import result. Its visible-ID/open-choice recommendations were superseded by user decisions.
- Initial implementation: implemented HTML/CSS, preview, source scope and correct baseline grouping.
- Final result: reported focused red/green checks and 24/24 tests without skips, using existing fixtures/builds.
- Independent final review: fresh 24/24 pass; for each GUID, the new stored BackContent equals the old BackContent after deleting only the uncertainty section. Front fields, all other text/links and native identities matched. Both source issues were absent from raw/decoded fields and preview.

Current standalone output: final preview. The user accepted the earlier output/deck's detail and intends to reimport the final package; agent execution reports do not claim that this new artifact was opened in Anki. Current package location and hashes are owned by the [packaging log](../apkg-packaging/log.md).
