# Configuration decisions

## Chosen approach and why

2026-10-18: move run/deck settings into one validated YAML file at the CLI boundary and pass explicit typed values into existing consumers. Preserve the accepted five-note batch to isolate configuration plumbing from unfamiliar source-deck extraction. Configuration-relative paths make a selected file's meaning independent of invocation cwd; existing explicit CLI path arguments retain cwd-relative override behavior.

Keep field/template/render/audit policy in code. The migration preserves source content and effective identity settings rather than treating every constant as a user preference. Audit records configuration provenance separately from learner fields. Mutable job state stays in semantic `jobs/` records.

The duplicate GUID namespace in `audit.py` required shared contract v1.1: add an explicit required namespace argument while preserving both per-note and expected-GUID-set checks. Leaving that literal behind would incorrectly reject a package built with an alternative configured namespace. This is dependency plumbing, not reduced audit coverage or a new dataset revision.

## Defects found and resolved during review

- A valid public APKG basename `repeat-check.apkg` aliased the builder's internal repeat package, causing self-comparison and deletion of the deliverable. Put the repeat file in a separate staging subdirectory; independent review verifies distinct files and that injected identity mismatches still prevent publication.
- A finite positive epoch could overflow SQLite native IDs. Validate actual genanki arithmetic and the complete ten-row sequence during configuration loading, including numeric conversion overflow. Independent review tests rejected values and adjacent safe integer/float bounds through the real CLI and reads back safe IDs.

Both defects were resolved in one consolidated implementer correction batch, then independently rechecked. Initial findings and final dispositions remain separate evidence.

## Unchanged scope

No source/enriched data, JSON Schema, learner wording, sense grouping, rendering or diagnostic-display policy changed. The old accepted APKG remains the comparison oracle. Native identity/content equality is established offline; user import/reimport and client behavior remain separate checks. No original-deck extraction or update semantics are inferred from exporter behavior.
