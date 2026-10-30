# APKG packaging contract

### Boundary and construction

[packaging.py](../../../jp_deck/packaging.py) takes the fixed validated M1 records and [rendered fields](../anki-rendering/contract.md), builds a genanki Model/Note/Deck/Package, and writes APKG plus external preview/audit files. It does not open or modify the user's Anki collection. The runtime used for this milestone is Python 3.13.5 with genanki 0.13.1; [pyproject.toml](../../../pyproject.toml) and [uv.lock](../../../uv.lock) define dependencies.

Since the 2026-10-18 refactor, `build(config, *, force=False)` consumes explicit typed settings/paths/constraints from the CLI [configuration boundary](../configuration/contract.md). Packaging does not read YAML. The shipped YAML retains all effective M1 identities and safeguards; field/template/render/audit policy stays in code.

### Anki structure and identity

- Exactly 5 notes / 5 cards, one model and one front/back template. No reverse cards, extra collocation cards or media.
- Ordered note fields: Expression, FrontCollocation, BackContent. Model.fields and Note.fields must share this order.
- Deck: 日本語語彙 — Vietnamese MVP, ID **1348730325**. Model: JP Vocabulary M1 — Japanese to Vietnamese, ID **1661854647**.
- The template question uses the first two fields; the answer uses FrontSide followed by BackContent. No debug/raw JSON fields are added.
- Model/deck IDs are namespaced and stable. GUIDs derive from stable input_id, not mutable text. A fixed write epoch stabilizes native note/card row IDs for the fixed input order. These choices apply to this MVP namespace, not to the original deck.
- One populated MVP deck contains every card. Genanki's empty Default metadata entry (ID 1) is allowed, giving two deck metadata entries but zero Default cards.
- The produced archive uses genanki's legacy collection.anki2 plus empty JSON media map. The project does not implement modern Anki's alternative package/media protocol itself.

### Build and artifact behavior

Existing named outputs are refused unless --force is explicit. Validation/rendering happen before package creation. The builder stages files, audits the APKG read-only, writes preview/local audit, builds a second package to compare native identity snapshots, then replaces only the three named outputs. Unrelated output files are not removed. Individual file replacement is not a transaction covering all three artifacts.

The [CLI](../../../jp_deck/__main__.py) accepts --config plus --input, --source-input, --output-schema, --input-schema, --output-dir and --force. Default config is repository `configs/mvp.yaml`; its output directory is `artifacts/config-refactor-yaml/revision-1/`. Explicit CLI path flags override YAML. A separate inspection build can use:

~~~sh
.venv/bin/python -m jp_deck \
  --config configs/mvp.yaml \
  --output-dir /tmp/jp-deck-config-inspection
~~~

Do not use --force on an accepted historical directory as a routine verification step. The latest delivered artifact and its provenance are linked in the [log](log.md).

### Evidence and import boundary

The [audit contract](../field-audit/contract.md) defines package checks; [test_packaging.py](../../../tests/test_packaging.py) exercises a real build and reads stored SQLite fields. The repeat check establishes native identity stability, not byte-identical ZIP files or successful client import.

User access is through the actual local APKG/WSL Explorer path, not an invented public download URL. The user performs import/reimport. Original-deck note mapping, scheduling preservation and client-specific update behavior are not established by matching the MVP's IDs; remaining project limits are in [tracker](../../tracker.md#outstanding-limitations).


### Accepted Tango v2 stage and final delivery (2026-10-20)

`python -m jp_deck build --config PATH` now accepts the reviewed complete version-2 stage config and existing path overrides/force through the [output boundary](../source-normalization/contract.md#accepted-output-stage-boundary-gate-2). It validates normalized/enriched/native linkage and target protection, then passes explicit `AppConfig` to this unchanged builder. Legacy invocation/version 1 remains compatible; fixed fields/templates/learner projection and `audit.py` are unchanged.

The separate final Tango namespace uses model ID `1661854648`, deck ID `1348730326`, GUID namespace `jp-deck/tango-source-normalization-2026-10-20/note/v1`, and fixed epoch `1792454400.0`. Final binding records exact config/revision/hashes. Delivery contains APKG/preview/audit paths and fingerprints. Final E2E verified five notes/cards, direct ZIP/SQLite/native relationships, existing audit and complete repeat identity/preview after independent Gate 2 acceptance. This is an offline delivery; user Anki import/preview/update behavior remains unverified.
