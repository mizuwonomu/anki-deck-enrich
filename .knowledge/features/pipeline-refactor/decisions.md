# Pipeline refactor decisions

### decisions.md  (why — the expensive part)

**Chosen approach + why**

- Chose one shared configuration/CLI/normalization/validation/export pipeline with source-specific mapping adapters because archive handling, validation, protected publication and package construction should not be rewritten for every APKG. Adapter applicability follows actual note-type semantics and conversion rules; another filename alone does not require another adapter. The implementation now uses one finite registered Tango adapter; this is not arbitrary-deck support. Anchor: 2026-10-21 shared job contract and independent recheck; this workspace intentionally has no Git branch/commit anchor.
- Selected repository-root `configs/` for operational YAML because users and future workers need a stable configuration entrypoint. Per-run effective-config snapshots remain provenance. YAML declares supported settings; it does not generate mappings or execute a transformation DSL. The existing frozen Tango YAML files remain historical evidence until their migration/disposition is recorded.
- Chose to separate source/run bindings from common control flow because current native IDs, fingerprints, adapter/version checks and Tango imports limit reuse. Field interpretation, conversion rules and applicability remain adapter responsibilities; source/run paths, selected identities and fingerprints belong at the typed configuration/binding boundary. Fixed test literals remain independent regression oracles and are not indiscriminately moved into runtime YAML.
- Chose removal of executable job-local scripts from the active `jobs/` tree after their responsibilities and evidence have a destination because one-off launchers/probes/report writers and copied source trees obscure the production entrypoints. Reusable behavior belongs in `jp_deck/` or meaningful tests; commands and rationale belong in knowledge. Documentation cannot replace executable validators or the artifacts proving an earlier run.
- Retained accepted source/input/enriched/package artifacts and historical manifests as the refactor baseline because they provide independent parity and provenance checks. Scripts pinned by historical manifests must be archived/dispositioned with preserved bytes and a location index before their active copies are removed. Do not rewrite an old manifest to imply that it reviewed new refactor code.

**Assumptions it rests on**

- Normalized input and enriched JSON retain their current schemas and semantics; source gloss is context, not a Vietnamese expected answer.
- The supported exporter remains exactly five notes/cards with unique expressions, an existing first collocation, current learner projection and source headword linkage. Arbitrary batch sizes, media migration, new APKG format support and a general plugin system are outside this refactor.
- Compatible source formats can share reader infrastructure, but the current reader's supported modern database layout does not establish support for every APKG version.
- New sources still require researcher-owned semantic mapping evidence and implementer-owned adapter/config/test work where needed. Existing Tango research is reused for this organizational refactor rather than repeated.

**Failed approaches**

- Tried: use the directory containing a job-local YAML as the normalization write boundary → Failed because: before the refactor, outputs had to descend from `config.config_path.parent`, preventing root YAML from publishing into a sibling run directory → Avoid when: tying authorization to config placement. The accepted correction authorizes only explicitly named targets and retains resolved protection/collision/force checks; independent real CLI tests verify the separated directories. **Cross-cutting configuration/publication boundary.**
- Tried: leave long-lived test inputs/configs/expectations under dated job directories → Failed because: at inventory time, source/output tests depended on those job paths, so broad cleanup was a test/runtime dependency change → Avoid when: treating job contents as disposable merely because their worker finished. The accepted migration moved consumed fixtures first, then archived and verified every removed script byte. **Cross-cutting fixture/evidence boundary.**

Earlier runtime defects and their accepted remedies remain owned by [source-normalization decisions](../source-normalization/decisions.md); this document does not duplicate those findings.

**Nuances agreed with the user**

- The initial extraction changed only knowledge. The subsequently authorized refactor moved source semantics into `jp_deck/sources/tango_n1_mimi/`, promoted root YAML/stable fixtures and archived 111 job scripts with original hashes. Independent recheck accepted the corrected submission and the separate final same-Luna 76-test/fixture rerun passed; exact closure evidence belongs to tracker/job state.
- Shared stage/config/reader/export flow selects a finite adapter without Tango sample bindings in common modules. The adapter retains source semantics and applicability; source/run paths, selected identities and fingerprints remain typed config bindings. “Generalize” does not mean deriving independent regression expectations from runtime config.
- `normalization.py` consumes an existing typed config and delegates semantic conversion; it does not infer arbitrary field meanings or emit the operational YAML.
- Raw selected native text/identity and the four-key translator-input projection remain separate artifacts. Preserve the original source while changing infrastructure or paths.
- Canonical `.knowledge/` belongs to the orchestrator. Researcher/implementer/reviewer workers read their exact role file and return scoped artifacts. Independent technical review remains distinct from translation/source attestation; lifecycle delivery errors do not become linguistic or software success claims.
- The user explicitly rejected speculative defensive code/bloat. Independent review found no fallback implementation, compatibility shim, dynamic discovery or added dependency. One inherited effective-filename diagnostic gap was reproduced, then corrected at existing read/schema/linkage boundaries using existing error types; no alternate parser or new framework was added.

## Post-refactor extraction and runtime boundaries

**Chosen approach + why**

- Kept the accepted implementation/evidence immutable during this documentation-only extraction because documentation cleanup is not sufficient authorization to silently change source bindings, sidecar semantics or test oracles. Current source inspection and the missing-contract probe are anchored to accepted `submission-2.json` SHA-256 `b7b54e6556b0798a1b712bb7f6a330718d2a4540249cf316e5989081403105ee` (2026-10-21). Git HEAD/branch probes return exit 128, so no Git commit/branch anchor is available.
- The canonical Markdown copy was introduced to give the existing provenance pin a stable path while preserving the accepted contract bytes. That explains the placement, not a semantic need for Markdown at runtime: field conversion is implemented by the adapter. The user's updated preference is to remove the canonical source-Markdown authoring requirement; agreed source semantics can remain in an implementation/research packet and executable adapter/tests without making a human document a production prerequisite.
- Describe the technical pipeline as deterministic for fixed source/config/schema and persisted enriched data because executable readers, validation, rendering and export enforce those contracts. Keep linguistic production separate because translation/review is performed by agents/humans and schema conformance does not establish meaning or attestation. The accepted E2E reused frozen enriched r3; it did not regenerate translation.

**Assumptions it rests on**

- Baseline artifacts are regression evidence, not a requirement to author a new `.knowledge/sources/<source>/mapping-contract` for every deck. Removing this existing artifact dependency is a separate runtime/config/sidecar/test migration; merely deleting or moving the file does not implement that migration.
- Technical repeatability assumes the same declared source and input bytes, YAML, schemas, adapter implementation and relevant runtime dependencies. Native identities/content parity is the accepted criterion; byte-identical ZIP archives and deterministic new language generation are not implied.
- Independent fixed expectations remain useful when production scope changes. Calling five cards a baseline does not itself remove the current validators/exporter's five-record checks or the single registered snapshot-specific Tango profile.

**Failed approaches**

- Tried: make only the configured Markdown path nonexistent in a temporary config while leaving the real document and all other paths intact → Failed because: read-only `validate-output` still reads/hashes that artifact and exits 2 before output acceptance → Avoid when: treating a source-contract document as independently deletable prose. **Cross-cutting configuration/provenance boundary.**
- Tried: identify translation/full agent execution as an implemented CLI stage → Failed because: current dispatch registers only `normalize`, `validate-input`, `validate-output` and `build`; translation is an external producer of the persisted JSONL → Avoid when: equating a successful frozen-artifact E2E with deterministic fresh translation. **Cross-cutting input/output evidence boundary.**
- Tried: interpret the five-card baseline as a fixture-only restriction → Failed because: input/output dataset validation, adapter applicability and package audit still enforce fixed cardinality in runtime code → Avoid when: claiming arbitrary-deck/batch support from the retained baseline suite.

**Nuances agreed with the user**

- The user does not want canonical per-source mapping Markdown to become required authoring work. Removing that requirement must remove the actual gate/metadata dependencies; adding an ignored-missing-file fallback or another document layer would preserve the wrong design.
- Preserve adapter/version identity, source/native/raw linkage, independent fixtures and historical acceptance while changing the active provenance contract in any future migration. Do not rewrite old accepted manifests or replace fixed test expectations with whatever the current config returns.
- This extraction changes only the four canonical documentation files. No Markdown contract deletion, runtime migration, cardinality expansion, fresh translation, test-suite rerun, staging or commit was performed. Open limitations and the fresh probe's remaining diagnostic issue belong only to the tracker.
