# Field and package audit contract

Current package cardinality and identity matching follow the [batching extension](../batching-mimi/decisions.md). The five-note package description below records the original regression baseline; the accepted extension audits configured identities rather than expression uniqueness.

### Boundary

[audit.py](../../../jp_deck/audit.py) compares validated source records with the learner projection and the generated APKG. It verifies preservation and associations; it does not adjudicate Vietnamese nuance or rerun the bounded lexical reviewer. [Validation](../validation/contract.md) supplies structurally/reference-valid input, [rendering](../anki-rendering/contract.md) owns display policy, and [packaging](../apkg-packaging/contract.md) owns file construction.

### Field dispositions

| Class | Examples | Required treatment |
| --- | --- | --- |
| Learner content | Expression/reading/POS, meanings/explanations, example sentence/reading/translation/origin, collocation usage, related-term notes, available attribution/license | Preserve the approved text and correct pairing; null corpus frequency remains unmeasured. |
| Research structure | input/object/sense/source IDs, evidence_refs, origin_source_ids and JSON Pointers | Resolve grouping and claim/source relationships internally; do not expose raw structures in Anki fields. |
| Local diagnostics | uncertainty issue_vi, hashes, schema/revision, source locators/observations and build/debug payloads | Preserve locally and omit from learner fields. Source counts may include omitted objects. |
| Native Anki structure | Model/deck/note/card IDs, GUIDs and template ordinal | Store in package structure, never as extra learner/debug note fields. |

The source has two uncertainties; the final learner projection displays zero issue texts. That distinction is intentional omission, not a claim that the source objects disappeared.

### Render audit requirements

- Expected learner strings must appear in normalized visible back text. This is necessary but not sufficient.
- Each sense's meaning and explanation must occur in its own sense section. Linked examples/collocations/related terms/confusables must remain under that sense.
- Each example/article must keep its own sentence, reading, translation, origin and scoped source links together. Matching total text or URL counts alone is insufficient.
- Source links must match the existing origin/evidence relationships, including the exact claim target; unexpected citation markup fails. An example source is not collocation proof.
- Internal IDs/claim paths must not leak into the back. Existing source issue text must be absent; the renderer/serialization tests also check all note fields and preview directly.
- AuditError gives a record/path when a render invariant fails. Audit does not delete or rewrite content to make itself pass.

### Package audit requirements

Read-only ZIP/SQLite inspection verifies CRC, collection integrity, the exact three ordered note fields and stored field values, the expected native identities and card relationships, 5 notes/cards, one model/template and one populated MVP deck. Genanki's empty Default metadata entry is allowed; no card may use it. Media map and review history are empty for M1. The builder compares two identity snapshots; that is structural repeatability, not a promise of identical ZIP bytes.

The configured GUID namespace is a required explicit `audit_apkg` argument after the [configuration refactor](../configuration/contract.md). The existing per-note and expected-GUID-set checks still use `genanki.guid_for(namespace, input_id)`; audit does not read YAML or retain a fallback namespace.

### Test evidence policy

Before adding a test, answer: **what behavior changes; what could break; which existing tests already prove it; what is the lowest reliable verification layer; is another test necessary?** Reuse appropriately scoped canonical fixtures and existing package builds where sufficient. Avoid copied omnibus fixtures, variable/boilerplate/chore assertions and exhaustive unrelated matrices.

When a test fails, investigate and explain the cause before changing code or expectations. Preserve stable assertions and behavior. Do not comment out/disable tests to obtain green; skipping, xfail or discovery/deselection that conceals failures requires explicit user permission. Targeted runs may reproduce a defect, but final relevant-suite evidence cannot hide its failures. A user-approved behavior change can change the corresponding expectation with the reason recorded.

Independent source expectations and direct SQLite/HTML checks complement the project's own audit flags. The suite's current evidence is bounded to M1, not exhaustive proof of future records. The [decisions](decisions.md) explain the defect that made this distinction concrete; open limits are centralized in [tracker.md](../../tracker.md#outstanding-limitations).
