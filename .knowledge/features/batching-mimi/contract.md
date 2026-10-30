# Batching and aggregation contract

Approved 2026-10-23 as the translation-to-aggregate design and implemented in [aggregation](../../../jp_deck/aggregation.py) and [batching](../../../jp_deck/batching.py); [aggregation tests](../../../tests/test_aggregation.py) exercise it through the real entrypoints. The rationale lives in [decisions](decisions.md) and the design history in the [execution narrative](log.md).

## Batch acceptance

The orchestrator freezes batch acceptance only after verifying reports. Acceptance binds at least:

- Job/batch identity, frozen manifest/input paths/hashes and exact ordered assigned IDs
- Contract/schema fingerprints applicable to output validation and review
- Enriched output path, complete-file SHA-256, artifact revision and expected record revisions by `input_id`
- Validation report path/hash, method/command, passing result and the output hash that was validated
- Review report path/hash, reviewed output hash, reviewed revisions, scope, verdict and outstanding findings

A worker's self-declared `accepted: true` flag or `worker_done` event does not replace this gate. Changing output bytes or revisions makes the previous binding stale; recomputing a hash from a candidate does not prove that the candidate was reviewed. A review `pass` certifies only its assigned scope.

## Membership, cardinality and order invariants

Let `P` be the frozen ordered sequence of all selected IDs, `B_i` the ID sequence for batch i in the manifest, `O_i` the `input_id` sequence in enriched output batch i, and `A` the aggregate's ID sequence.

| Invariant | Required condition |
| --- | --- |
| Per-batch membership/order | `O_i = B_i` for every batch |
| Per-batch cardinality/uniqueness | `len(O_i) = len(B_i) = len(set(O_i))` |
| Disjoint membership | For distinct batches, `set(O_i)` and `set(O_j)` have an empty intersection |
| Exact union | The union of all `set(O_i)` equals `set(P)`, with no missing/foreign IDs |
| Aggregate cardinality/uniqueness | `len(A) = len(P) = len(set(A))` |
| Aggregate order | `A = P = concat(B_i)` in manifest order |
| Payload preservation | The aggregate record for each ID equals the complete record in its accepted batch |

Cardinality is a count; disjointness is a property of ID sets. A correct row count can still hide one missing and one duplicated ID, so check sequences, sets and multiplicities against the records actually read; deduplicating through a set/dictionary before validation hides errors. A correct global union is insufficient: swapping records between batches preserves union/count while violating assignments, so compare each `O_i` with `B_i` before merging. Identity comes from project/native IDs bound through the input manifest, not expression text; records with distinct IDs and equal expressions are both retained. Batch size is a maximum and a short final batch is valid; nothing hard-codes a dataset size.

## Deterministic aggregation

1. Read the frozen manifest, check schema/provenance and derive the required batch set from the manifest
2. Require exactly one accepted output per batch; reject missing, duplicate or foreign batches and stale artifact/review bindings
3. Read actual enriched records, validate schema/references, exact membership/order, revisions and review coverage; check multiplicities before indexing/merging
4. Check disjointness, exact union and cardinality against `P`; expectations come from the independently frozen manifest
5. Merge records in manifest order, preserving payloads; worker completion order and directory listing order never determine output
6. Validate the aggregate against the normalized master and the per-`input_id` revision map; record its hash and provenance mapping each ID/output row to its batch, source artifact/hash and revision
7. Stage artifacts and validate persisted files before publication; preserve protected paths, prevent overwrite/collision/symlink alias violations and never report success when a gate fails
8. Use only the validated aggregate/hash for rendering, building and package audit

Given the same accepted inputs and serialization contract, aggregate JSONL order, bytes and hash are reproducible; this does not imply byte-identical APKG ZIP files across builds. The aggregate has its own artifact revision while each `record.revision` is preserved, so batches accepted at different revisions merge under the revision map; legacy scalar `constraints.revision` configs remain supported.

Errors identify job/batch ID, file, line/output row, `input_id` and field path where known; membership errors name missing/foreign/duplicate IDs or the position of an order mismatch. Validation failure preserves accepted artifacts and never produces a delivery marked successful.

## Evidence boundaries

Unit tests establish invariants; CLI/integration tests establish execution paths and failure behavior; real-data acceptance establishes that actual accepted translations pass through the complete flow. Synthetic batch tests do not prove translation, review or a real-deck build. Linguistic review keeps its per-batch scope; package audit covers the complete dataset. Live Anki import/reimport, scheduling and media migration remain separate, unverified checkpoints.
