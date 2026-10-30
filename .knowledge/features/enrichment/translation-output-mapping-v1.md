# Translation output mapping contract v1

## Scope and authority

Contract version: `jp-deck-translation-output-mapping/v1`.

This supplement defines the output placement and evidence/review boundary for Kanji/root explanations in new translation assignments. Read it together with the [base enrichment contract](contract.md) and `schemas/output.schema.json`. Job packets must name this supplement and its SHA-256 alongside the base contract. Existing accepted jobs retain their original frozen contract bindings and review scope.

Base enrichment contract SHA-256: `57c156492512965fd46d12aa8fe948024fbb132799e22f298434dae39fb9c8b4`.

## Kanji/root output mapping

- Write Kanji decomposition, Sino-Vietnamese roots and etymological explanations as Vietnamese plain text in `senses[i].explanation_vi` for the relevant sense, using the existing output schema.
- These explanations remain part of the sense explanation; no additional output property or Anki field is required.
- The translator may produce this content from its own linguistic knowledge. Web lookup and source citations are not required for this content. Do not fabricate sources or `evidence_refs`.

## Review boundary

Kanji/root explanations covered above are translator-owned and outside the reviewer's verification scope. The reviewer must not independently fact-check or search the web for this content, or require source citations for it. Missing citations for this content alone are not a finding and must not lower the verdict or trigger `needs_human_review`.

Structural checks on the field and any references that are present still apply. All other assigned language, collocation and source checks retain their existing scope.
