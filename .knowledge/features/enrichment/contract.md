# Enrichment MVP contract v0

## Scope and flow

User-supplied input JSONL → translator output JSON → bounded reviewer report → user review. The input schema is `schemas/input.schema.json`; the translator schema is `schemas/output.schema.json`. JSON is the primary review artifact. The user approved this scope and bounded review policy on 2026-10-16.

Do not inspect APKG or require Anki metadata during this MVP. Later, code may extract/map real decks and package JSON-derived fields/templates/media as APKG. Anki identity and scheduling preservation remain a separate unverified milestone.

## Roles and paths

The four role instructions are `.knowledge/roles/orchestrator.md`, `.knowledge/roles/translator.md`, `.knowledge/roles/reviewer.md`, and `.knowledge/roles/implementer.md`. Every dispatched agent must be explicitly told to read its role and this contract. Role and model selection are separate. The orchestrator coordinates sessions through artifacts, not assumed shared memory.

## Data semantics

- One source record has `id`, `expression`, `reading`, `meaning_vi`. Keep it unchanged; source meaning is not ground truth.
- One enriched record has `schema_version`, `input_id`, positive `revision`, `headword`, `senses`, `examples`, `collocations`, `related_terms`, `confusables`, `sources`, and `uncertainties`.
- `headword` contains proposed expression/reading/POS. Kana is text, not audio. Optional collections use `[]`, not invented content. At least one sense is required for a completed output; if no sense can responsibly be proposed, report a blocked item instead of fabricating an output.
- `evidence_refs` entries name a local `source_id` and a JSON Pointer `claim_path` identifying the exact statement supported. Source presence never validates all fields in an object. References with an invalid source or target are errors.
- Source records contain provider, underlying source (nullable if unavailable), URL, locator (entry/sentence ID or corpus query), access date, and an observation. An observation is a concise report of what was seen, not necessarily a quotation. Source license/attribution can be recorded when known; do not invent them.
- Examples carry an origin (`quoted`, `adapted`, `generated`) independently of attestation. `origin_source_ids` are required and nonempty for quoted/adapted examples; these record provenance, not automatic validation of a translation. Generated examples may still have separate evidence for usage.
- A collocation's nullable `frequency` object represents a measured count with corpus scope, query, and source. Absence of a count means no measured-frequency claim, not a zero count.
- `uncertainties` contain a JSON Pointer and a concrete unresolved issue. Record unsupported strong nuance/substitution/frequency claims or proposed source corrections needing review; not every translator-authored explanation needs independent web proof.
- IDs must be unique within each object collection; `input_id` must match an assigned source input; sense IDs and source IDs must resolve locally. Unchanged items retain IDs across revisions. These are semantic checks beyond JSON Schema.
- Reviewer output is separate and bound to the reviewed artifact/revision; its documented contract is in `.knowledge/roles/reviewer.md`. Translator output has no self-awarded review verdict.

## Approved source and review policy

The translator owns Vietnamese nuance and interpretation. Reviewer checks structure and the assigned collocations, not stylistic conformity to another model. A concrete sense/context error or source contradiction may be reported for translator correction.

| Source | Use | Evidence boundary |
| --- | --- | --- |
| [JMdict / EDRDG](https://www.edrdg.org/wiki/Main_Page.html) | Writing, reading, POS, sense and usage-label checks | Does not prescribe Vietnamese wording or independently prove nuance/substitutability. Record entry/sense and data version when available. |
| [Tatoeba](https://tatoeba.org/en/) | Example sentences and linked translations | Community content needs contextual inspection; sentence existence is not proof of popularity or perfect translation. Record sentence ID, author/license if available. |
| [Weblio Japanese](https://www.weblio.jp/) / [Japanese-English](https://ejje.weblio.jp/) | Dictionary phrases and contextual examples when accessible | Record the underlying dictionary/corpus shown. No measured frequency inferred from example availability or service-wide example counts. |
| [Tsukuba Web Corpus / NLT](https://tsukubawebcorpus.jp/en/) | Collocation patterns and corpus counts | Restrict quantitative claims to this corpus; automated linguistic analysis can err. No assumed public API. |

- One directly supporting source for the same sense/construction is enough. Stop once support is found.
- At most two new search queries per assigned collocation, cumulatively across sessions/retries for that item. Inspect existing evidence first. An inaccessible source or unsuccessful search yields `unverified`, not `incorrect`.
- Attested usage and measured frequency are separate. Do not search further merely to justify a popularity adjective. If a claim exceeds its evidence, qualify or flag that claim.
- No routine multi-source triangulation or rewriting translator nuance. Nuance objections require a concrete issue, evidence, and a requested action; translator owns the wording of revisions.
- Report structure and attestation results separately. A bounded pass does not establish exhaustive linguistic truth.

## Research evidence and limitations

These are worker-reported findings from the 2026-10-16 source research, not a tested integration:

- JMdict: a concrete entry was viewed; [XML documentation](https://www.edrdg.org/jmdict/jmdict_dtd_h.html) and downloads are documented.
- Tatoeba: a sentence page was viewed; [public API](https://api.tatoeba.org/) was documented but a direct API query did not succeed in that session. A moderation flag is not a guarantee of correctness.
- TWC: documentation/examples were read, but an interactive query was not exercised. [Terms](https://tsukubawebcorpus.jp/search/en/) raise reuse restrictions; permission to reproduce results in a distributed deck was not established.
- Weblio: direct lookup pages could not be retrieved by the worker. Product information was available, but the sample collocation, API, and reuse terms were not verified. Do not present Weblio as an already-tested integration.

For copied/adapted material, preserve available attribution and licensing information; source access does not establish redistribution rights. Relevant references: [EDRDG license](https://www.edrdg.org/edrdg/licence.html), [Tatoeba terms](https://tatoeba.org/en/terms_of_use), and the NLT terms above. Packaging/reuse decisions remain deferred; this is not a legal determination.

## Persistence and open choices

Durable decisions live here and in role/index/tracker files. Handoffs and research-state snapshots stay local under `.knowledge/handoffs/`; they are not required for a cold-start agent to understand this contract. No Git tracking/ignore policy is changed by this document.

Still open: exact CLI invocation/authentication, runtime/job storage implementation, batch/revision budgets per run, machine-readable reviewer schema, and future Anki mapping/package compatibility. None blocks the manual JSONL content MVP.
