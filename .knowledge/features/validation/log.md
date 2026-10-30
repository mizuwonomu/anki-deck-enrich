# Validation implementation record

### How it was actually done

The initial input/output contracts were established before packaging. The input research state kept user-supplied lexical content separate from enrichment; the [enrichment contract](../enrichment/contract.md) assigned language judgement to the translator and bounded evidence checks to a reviewer.

M1 then implemented a strict loader for the unchanged five-word revision. Parsing, schema checks, source linkage, ordered identity/revision checks and local sense/evidence/pointer resolution became distinct code checks. No silent repair was introduced to make the earlier translation findings disappear. The final presentation change left this validator and the source/schema artifacts unchanged.

### Outcome and evidence

| Evidence | What it establishes |
| --- | --- |
| Historical validation artifact and bounded review | Earlier revision-1 structural/reference review; separate from the later Python exporter suite. |
| Initial implementation result | Python 3.13.5 execution, schema/reference checks and the original 23-test suite. |
| Audit-fix follow-up | Independent 24-test suite after one meaningful sense-association regression was added. |
| Final projection review | Fresh 24/24 passing tests, zero failures/skips, with validation/source/schema unchanged during issue-text removal. |

This documentation task inspected the current implementation and the retained execution reports. It did not rerun the runtime suite or promote schema validity into linguistic certification. Later work should start from this contract, the current code and the [tracker](../../tracker.md), rather than the historical statement that no exporter exists.

### 2026-10-18 configuration migration

The loader and in-memory validation now consume explicit configured constraints; shipped fingerprint, ordered IDs, revision/schema checks and all semantic/schema assertions remain intact. Independent final refactor recheck ran the full suite: 36 passed, zero errors/failures/skips, including consumer probes for changed fingerprint/order/schema constraints. Inputs and both JSON Schemas remain byte-identical. Configuration mechanics and execution provenance are recorded in the [configuration package](../configuration/log.md).

### 2026-10-20 standalone source-input validation

Accepted Gate 1 adds strict five-record input/schema/identity/source-map/raw checks and structured stage CLI diagnostics in `input_validation.py`. Dataset count is enforced without optional IDs/profile, per-record eligibility helpers remain reusable, and nested sidecars are typed before relationship access. Complete report-path protection prevents input/schema/source overwrite.

Independent recheck passed 57/57 tests with zero failures/errors/skips and 40 real CLI commands, including F1–F4 regression reproductions and adverse source composition. Orchestrator final validate-input passed on the released input/YAML with exact current code/data bindings. This is input-stage acceptance only; the existing enriched-output validator is unchanged and standalone validate-output/output integration remains Phase 2. See the [source-normalization contract](../source-normalization/contract.md).


## 2026-10-20 — Tango output-stage accepted and final E2E passed

The shared v2 validate-output/build extension was independently accepted after F1–F3 correction/recheck: 70/70 enabled tests and 26 independent CLI commands. Existing v1/API, renderer/audit, schemas, baseline tests and historical artifacts remain preserved. Separate final E2E re-normalized/validated actual Tango r3, built/audited five notes/cards and compared complete repeat native identities/preview. Gate 2, independent recheck, final E2E, delivery and limitations. No live Anki import or linguistic-attestation certification.
