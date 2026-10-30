# Anki Deck Enrich

🇬🇧 **English** | 🇻🇳 [Tiếng Việt](docs/README.vi.md)

Enrich Japanese vocabulary Anki decks with Vietnamese explanations and traceable dictionary evidence.

## Problem

Most shared Japanese vocabulary decks stop at a word and its gloss. That is enough to recognise a word, but not to use it:

- **Word and meaning only.** One short gloss per card, with no explanation of nuance or register.
- **No collocations.** You learn a noun but not which verbs and particles naturally go with it.
- **No examples.** Without a sentence in context, it is hard to tell when the word actually fits.
- **No synonyms or related words.** Near-synonyms are learned in isolation, and the limits of their interchangeability are never stated.
- **No antonyms.** The opposite-meaning pair that would anchor the word is missing.
- **No easily confused words.** Look-alike or sound-alike words are not contrasted, so they keep getting mixed up.

Enriching cards by hand is slow, and enriching them with an LLM alone produces confident text with no way to check where it came from.

## Solution

jp-deck is a **multi-agent pipeline**: agents do the language and research work, and deterministic code checks and builds everything around it.

| Agent | Responsibility |
| --- | --- |
| Orchestrator | Splits the work into batches, dispatches each agent with a work packet, tracks state and freezes a batch only after its validation and review pass |
| Researcher | Surveys a new deck's fields and writes the mapping contract for its adapter |
| Implementer | Writes the adapter code and tests from that contract |
| Translator | Enriches one batch: Vietnamese senses and explanations, collocations, examples, related terms and confusables |
| Reviewer | Independently checks one exact artifact (code or a translated batch) and returns `pass`, `needs_revision` or `needs_human_review` |

Agents do not hand work over through chat history. Each one reads a work packet and writes files (JSONL records, JSON reports with hashes), so a new session can resume from persisted state. A batch that needs changes goes back to its translator; one that needs human judgement goes to the user. Batches run independently of each other.

Around the agents, code does the deterministic parts:

- **Source adapter.** Reads the original `.apkg`, maps its fields to a strict input schema and freezes the selected notes into batches with a manifest.
- **Traceable evidence.** Claims carry evidence references to [JMdict](https://www.edrdg.org/wiki/Main_Page.html), [Tatoeba](https://tatoeba.org/en/), [Weblio](https://www.weblio.jp/) or [Tsukuba Web Corpus](https://tsukubawebcorpus.jp/en/). Anything not verified is recorded as an uncertainty instead of being presented as fact.
- **Validation.** JSON Schema plus code checks for IDs, order, revisions, hashes and source linkage at every stage. A batch is accepted only when the exact reviewed artifact is bound to its review.
- **Aggregation and build.** Accepted batches are merged in manifest order, rendered to Anki HTML and packaged with [genanki](https://github.com/kerrickstaley/genanki) into an audited offline `.apkg`.

Built with Python 3.13, `jsonschema`, PyYAML and `genanki`. Every stage is a CLI command driven by an explicit YAML config.

## Project structure

![jp-deck pipeline](docs/assets/jp-deck-pipeline.png)

> [!NOTE]
> Three phases: **Input Field Mapping** (adapter, normalization, frozen batches), **Deck Enrich Phase** (per-batch translator and reviewer agents, then aggregation) and **Build and Delivery** (render, audit, package). The scheduler box shows the intended concurrency policy; today, batches are dispatched outside this CLI.

### Before and after enrichment

![A card before and after enrichment](docs/assets/jp-deck-before-after.png)

> [!NOTE]
> Left: the original card (word, reading, gloss). Right: the same note after enrichment, with Vietnamese explanation, collocations, examples, related terms and confusables, each linked to its source. The example uses fabricated data, not the original deck.

## Quick start

Requires Python 3.13+. Install dependencies with `uv sync` (then prefix the commands below with `uv run`), or `pip install genanki==0.13.1 "jsonschema>=4.18,<5" PyYAML==6.0.3`.

### Try the synthetic demo

The demo builds a five-note deck from fabricated, already-enriched records, so no Anki deck is needed:

```sh
python -m jp_deck validate-output --config configs/synthetic-demo.yaml
python -m jp_deck build --config configs/synthetic-demo.yaml --output-dir /tmp/jp-deck-demo
```

`/tmp/jp-deck-demo/` then holds `synthetic-vocabulary.apkg`, `preview.html` (open it in a browser) and `audit.json`. Run the test suite with `python -m unittest discover -s tests`.

### Run on a real deck

1. **Place the deck** in `datasets/`, for example `datasets/my-deck.apkg`. `datasets/`, `jobs/`, `artifacts/` and `configs/*.yaml` (except the demo) are git-ignored, so real data and run outputs stay local.
2. **Write a config** at `configs/my-deck.yaml`, starting from `configs/synthetic-demo.yaml`. Add a `source` block (APKG path and SHA-256, adapter ID, mapping contract, deck and note-type IDs, selection order and count), `normalization` output paths and a `batching` section with `batch_size` and `output_dir`. Paths are relative to the YAML file. For a new deck, the implementer agent can write this config together with the adapter, directly from the researcher's mapping contract.
3. **Run the stages** in order:

   ```sh
   python -m jp_deck normalize        --config configs/my-deck.yaml   # APKG -> normalized JSONL + source map
   python -m jp_deck validate-input   --config configs/my-deck.yaml
   python -m jp_deck prepare-batches  --config configs/my-deck.yaml   # frozen batches + manifest
   # agents enrich and review each batch; the orchestrator writes its acceptance
   python -m jp_deck validate-batches   --config configs/my-deck.yaml
   python -m jp_deck aggregate-output   --config configs/my-deck.yaml
   python -m jp_deck validate-aggregate --config configs/my-deck.yaml
   python -m jp_deck build              --config configs/my-deck.yaml   # APKG + preview + audit
   ```

> [!IMPORTANT]
> Only one source adapter is registered (`tango-n1-mimi-n1-v1`), and it accepts one exact deck snapshot pinned by hash. Any other deck needs the researcher and implementer agents to add an adapter first. The enrichment step itself runs through the agents, not the CLI. Validation and packaging check structure and provenance, not language quality: a passing build does not certify a Vietnamese explanation. Live Anki import, reimport and scheduling are not verified, and no real deck or translated data is included in this repository.

## Current status

- **Tested at pilot scale only.** The full flow, from source deck to agent enrichment, review, aggregation and an audited APKG, has run on one 45-note pilot split into 2 batches (25 + 20). Runs with many batches or a full deck have not been tried yet.
- **No automated orchestration yet.** Agents are dispatched per batch by hand and each CLI stage is run manually. The scheduler in the pipeline diagram (concurrency and session policy) is a proposal, not an implemented script.
- **No antonyms yet.** The output schema supports synonyms, near-synonyms, related terms and confusables, but not antonyms.
