# Validation decisions

### Chosen approach + why

- **Use code for deterministic checks.** The user explicitly preferred deterministic extraction/validation/rendering over spending model calls on routine transformations. JSONL preserves agent-owned content while code checks the exchange boundary (2026-10-16, initial direction). This is why the implementation is a validator, not another translation agent.
- **Separate schema validity from semantic integrity.** JSON Schema checks a record's shape; it cannot establish dataset-wide uniqueness, linkage to source notes or existence of referenced sense/source/pointer targets. Those checks therefore run explicitly after schema validation. The distinction was already recorded in the roles/output research state before implementation.
- **Keep source glosses separate from enriched meanings.** An incomplete original Vietnamese gloss must not become an oracle that forbids useful enrichment. Expression and reading remain exact source links; proposed meanings live in the enriched record. Translator ownership follows the user's wording/evidence boundary.
- **Freeze bytes as well as IDs/revision for M1.** The user selected the existing five-word output for rendering without rerunning translation. A semantic-equivalence check alone would not prove that exact reviewed artifact was used. The raw fingerprint catches even whitespace-only changes; IDs/revision and source links establish separate semantic invariants (2026-10-17, M1 direction, implementation assignment).
- **Reject field separators before serialization.** A U+001F embedded in learner data can alter Anki field boundaries despite otherwise valid JSON. Rejecting it gives a source record/path diagnostic rather than discovering damaged field order after packaging.
- **Keep uncertainties valid after hiding them.** The final omission is a presentation policy; the local research/evidence record still needs valid paths for diagnosis and future review. Changing the schema or deleting uncertainty data would lose that traceability. The policy itself is owned by [rendering decisions](../anki-rendering/decisions.md).

### Assumptions it rests on

- The CLI operates on the fixed five-record, revision-1 artifact. More words or another revision require an explicit contract/fingerprint change; changing a test helper is not authorization to widen production inputs.
- Source IDs are project identities, not native Anki note IDs. Native identity construction belongs to [packaging](../apkg-packaging/contract.md).
- Referential integrity can establish that a claim points somewhere, not that its translation, frequency or linguistic interpretation is correct.

### Failed approaches

- Tried: make the hash-mismatch fixture add a blank JSONL line → Failed because: parsing correctly rejected the blank line before the fingerprint check, so the test did not reach its intended condition → Avoid when: constructing a negative fixture without accounting for earlier validation stages. The fixture was changed to valid JSON with trailing whitespace, preserving the hash mismatch. This is an implementer-reported test-development failure, not a production parsing defect (result).
- Tried: match a schema error using an unquoted record-ID expectation → Failed because: the actual diagnostic formats the record ID with quotes → Avoid when: interpreting an assertion-format mismatch as broken schema logic. The expectation was corrected after examining the emitted diagnostic; no validation rule or test was disabled (same result).

### Rejected approaches and user nuances

- Treating one source's presence as validation of every neighboring claim was rejected at design time. Evidence stays scoped to a claim/sense, and origin stays distinct from attestation; this was not an implemented validator that later failed.
- The suite is intentionally focused on types, required fields, references, Unicode/data preservation and real behavior. It is not an exhaustive invalid-input matrix. The user's exact test discipline is preserved in the [audit contract](../field-audit/contract.md#test-evidence-policy).
