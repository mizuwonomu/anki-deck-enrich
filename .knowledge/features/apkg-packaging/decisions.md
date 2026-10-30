# APKG-packaging decisions

### Chosen approach + why

- **Use genanki instead of authoring SQLite/ZIP records.** M1 needs a reproducible, headless conversion from existing JSONL into a separate deck. The library already constructs the interdependent model/field/template/note/card/deck data. Hand-written replacement of field placeholders or zipping arbitrary SQLite would not establish those relationships. Anki Desktop text import/export was researched as a manual alternative; it was not an attempted implementation that failed (research, [approved research checkpoint](../enrichment/log.md)).
- **Keep native identities stable within a dedicated namespace.** Mutable field-based GUIDs would make revised text look like new notes. Stable input-derived GUIDs and namespaced model/deck IDs preserve the intended MVP identity, while a fixed write epoch makes row IDs repeatable for the fixed ordered batch. This supports inspection of reimport assumptions without claiming original-deck/history preservation.
- **Allow genanki's empty Default metadata.** “One deck” means one populated learning deck. The library initializes an empty native Default entry; removing it by editing SQLite or using its reserved ID for the MVP would violate stronger construction/identity boundaries. Audit therefore distinguishes metadata-entry count from card-bearing deck count (2026-10-17, recorded clarification, result).
- **Use staging and explicit overwrite.** A bad input/audit should fail before replacing accepted output. Only this build's named artifacts are replaced; a developer must intentionally request replacement. The final projection uses revision-1-final so the earlier user-reviewed files remain evidence.
- **Keep provenance/audit outside the deck.** Learners need useful source attribution, not the build manifest, internal IDs or raw JSON. The APKG carries only the required Anki structure and learner fields; hashes, local diagnostic counts and checks stay in the accompanying audit.
- **Name job packages by task meaning.** The user observed result JSON accumulating in the root MVP job. Implementation, code review and the final projection now have semantic job directories; moving reports preserved package bytes rather than rebuilding as part of a documentation chore (2026-10-17, user direction).

### Assumptions it rests on

- genanki 0.13.1 runs on the project's Python 3.13.5; this was later exercised, not inferred solely from release metadata.
- The same five records/order and MVP namespace remain in use. A different dataset, model shape or generalized identity scheme needs another contract.
- Offline ZIP/SQLite/HTML checks are distinct from the user's Anki import/reimport. A local path is not a hosted download.

### Failed approaches

- Tried: require literally one deck metadata entry from the standard genanki writer → Failed because: it initializes empty Default metadata as well as the namespaced populated deck → Avoid when: equating metadata entries with exported learning decks. Keep the library output and inspect card membership; do not use reserved ID 1 or hand-edit SQLite merely to satisfy an inaccurate count (clarification and audit).
- Tried: run offline uv lock checking with the default cache in the review sandbox → Failed because: the sandbox could not write the home cache → Avoid when: treating a tool-cache permission failure as an application/test failure. The reviewer used a temporary UV_CACHE_DIR and the lock check passed without skipping tests (initial review evidence).

### Cross-cutting delivery failures

These affected worker delivery, not the validity of APKG data. They are retained because repeating them can stall future packaging work.

- Tried: call Orca through Windows/WSL while the sandbox disallowed the bridge → Failed because: the launcher returned UtilBindVsockAnyPort socket failed 1 before guide/runtime access → Avoid when: assuming a CLI failure means a worker started. The user enabled sandbox access and the same selected CLI subsequently worked; no alternate executable or duplicate writer was used.
- Tried: launch Pi in an Orca terminal whose metadata named jp_deck, including a later inline cd command → Failed because: the observed startup TUI still showed rag-project → Avoid when: trusting terminal metadata alone as working-directory proof. A launcher script that explicitly changed cwd and PWD produced the expected jp_deck startup. The underlying Orca command-routing mechanism was not independently established, so do not relabel this as a proven shell-profile defect. The original `jobs/apkg-m1-implementer/launch-pi.sh` is now preserved through the archive index; its job record remains unchanged.
- Tried: reuse a settled Pi terminal and check the run without the worker's explicit terminal handle → Failed because: check returned consumer_fenced and the worker stopped without worker_done, while Orca still showed the new dispatch active → Avoid when: copying historical IDs or using implicit consumer identity after reuse. The exact internal generation mechanism was not traced. Auto-review first rejected abandonment over possible writer liveness; the user then explicitly authorized abandoning that dispatch and retrying the **same task** with fresh Pi context. Explicit worker-handle commands and current preamble IDs were carried into later assignments (observed stop, approval, attempt ledger).

### Rejected proposals and user nuances

The user-supplied APKG document described legacy storage and contained a fld/flds discrepancy; research checked the real schema and retained the distinction from modern formats. This was source correction, not an executed modern-format failure. Direct AnkiConnect/collection integration, original-deck migration and public hosting were not implemented as part of this milestone.
