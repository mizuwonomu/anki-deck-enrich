# Validation contract

The current dataset/batch membership and normalized-content boundary follows the [batching extension](../batching-mimi/decisions.md). Historical standalone-stage fixed-five/unique-expression requirements below describe earlier acceptance rather than current universal dataset checks.

### Boundary

[validation.py](../../../jp_deck/validation.py) separates readable JSONL, per-record JSON Schema checks, dataset semantics, and the frozen M1 build gate. It validates data and references; it does not choose Vietnamese wording or certify dictionary truth. The downstream [rendering contract](../anki-rendering/contract.md) decides what becomes learner content.

### Inputs and invariants

- Source notes follow [input.schema.json](../../../schemas/input.schema.json): id, expression, reading and meaning_vi. The initial gloss is input context, not a reference answer.
- Enriched records follow [output.schema.json](../../../schemas/output.schema.json), Draft 2020-12, schema_version 0.1.0. Required fields, types, enums, optional/null shapes and additional-property restrictions come from that file, not a second schema copied into this document.
- The shipped M1 configuration constrains the loader to the frozen content of revision-1.jsonl, raw-byte SHA-256 **6c5e688bb5f512636425703417f3e6c0832d13c01c80df0a967cd7949e458d6f**. A byte-identical copy at another input path is valid; the filename is not the gate. Output IDs must be mvp-001 through mvp-005 in that order, with revision 1. This is a bounded exporter, not an arbitrary-vocabulary CLI.
- JSONL is UTF-8 with one object per line. Blank lines, malformed JSON and non-object values fail; values are not silently normalized or repaired.
- Both schemas are checked before use; record validation uses a format checker. Structural validation precedes semantic field access.
- Source IDs are unique. Each enriched input_id resolves to a source note; its headword expression and reading match that source exactly. Source input order is not used as identity.
- Enriched record IDs are unique; object IDs are unique within each applicable collection. Examples, collocations, related terms and confusables resolve their sense_id locally.
- evidence_refs source IDs, origin_source_ids and measured-frequency source IDs resolve locally. JSON Pointers resolve to existing targets, including uncertainty paths. Pointer existence is not proof that the referenced claim is true or renderable.
- Enriched strings cannot contain Anki's U+001F field separator. A nullable frequency means no measurement, not a count of zero.

### Interfaces and errors

read_jsonl returns original bytes and decoded records. validate_records checks schemas and semantics on in-memory records with explicit expected-ID/revision/schema-version arguments. load_and_validate_dataset receives explicit DatasetConstraints and applies them before returning records, input hash and source records. It does not load YAML or retain duplicate M1 defaults; the [configuration boundary](../configuration/contract.md) supplies the shipped constraints. Lower-level flexibility does not establish arbitrary-batch export support.

ValidationError identifies a record and JSON path when those are available. Encoding/JSONL failures instead identify the file, byte or line; a record ID may not exist yet. Parsing happens before the fingerprint comparison, so a malformed input can fail before a hash diagnostic.

### Preservation and verification

Validation reads source artifacts without rewriting them. The final decision to omit uncertainties[].issue_vi from Anki does not remove that field from JSONL, weaken its schema, or skip uncertainty-pointer validation.

Tests and mutation cases are in [test_validation.py](../../../tests/test_validation.py). Test additions follow the shared [test-evidence policy](../field-audit/contract.md#test-evidence-policy). Executed evidence and its scope are recorded in the [log](log.md); project-wide open limits belong in [tracker.md](../../tracker.md#separate-existing-limitations).

### Standalone input-stage validation (Gate 1 accepted 2026-10-20)

[input_validation.py](../../../jp_deck/input_validation.py) adds the source-input boundary described by the [source-normalization contract](../source-normalization/contract.md). It keeps the existing output validator above unchanged. Dataset-level validate-input requires exactly five records independently of optional expected IDs/profile/package, while reusable per-record helper checks can validate individual source projections.

When a native source profile is configured, source-map/raw structure and primitive types are checked before relationship access; records and source identities are compared against the read-only source snapshot. Normalized hash, ordered IDs, unique expressions and exact map/raw/card/deck bindings are verified. Declared input/schema/config/source/sidecar paths are protected from report publication. New CLI controlled failures carry JSON diagnostics and exit 2 rather than a traceback for malformed sidecars.

[Source-stage tests](../../../tests/test_source_normalization.py), independent recheck and the acceptance manifest govern this accepted input milestone. That historical Gate 1 evidence covers input validation. The accepted standalone output-stage extension below provides separate software/output evidence; input validation alone does not establish translation or packaging readiness.


### Standalone enriched-output stage (Gate 2 accepted 2026-10-20)

[output_validation.py](../../../jp_deck/output_validation.py) combines complete normalized-input validation with existing enriched schema/reference semantics. Exactly five unique source IDs/expressions, one enriched result per assigned ID, equal source/assigned sets, configured enriched order, revision/schema and exact headword linkage are required. Declared normalized/enriched hashes use effective paths; configured native profile/map/raw linkage is checked read-only before output/build acceptance.

`validate-output --config PATH` returns JSON stdout with counts, actual hashes and bound paths and publishes no files. Explicit build additionally enforces finalized settings/hashes, protected targets and existing renderer preconditions. Invalid UTF-8 schemas name the actual effective schema; missing-collocation build errors retain the effective enriched file and available record/path. Expected runtime failures use JSON stderr/exit 2; argparse/help remains conventional.

[New tests](../../../tests/test_output_stages.py) and the independent recheck preserve all old assertions and supply source/contract-independent native/template/card oracles. The accepted 70-test suite and actual final artifact E2E are separate evidence. See the Gate 2 manifest and final E2E.
