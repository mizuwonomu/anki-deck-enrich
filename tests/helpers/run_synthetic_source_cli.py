"""Run production Tango stages with temporary, synthetic source hash bindings."""

from __future__ import annotations

import sys
from pathlib import Path

from jp_deck.config import load_stage_config
from jp_deck.__main__ import main
import jp_deck.sources.tango_n1_mimi.adapter as tango_adapter

arguments = list(sys.argv[1:])
if not arguments or "--config" not in arguments:
    raise SystemExit("synthetic source CLI wrapper requires a stage and --config")
stage = arguments[0]
config_path = Path(arguments[arguments.index("--config") + 1])
config = load_stage_config(config_path, stage=stage)
if config.source is None:
    raise SystemExit("synthetic source CLI wrapper requires the finite production Tango profile")

# The real adapter functions remain in use. Only their immutable accepted-snapshot
# constants are rebound to the fabricated APKG/contract for this child test process.
tango_adapter.SOURCE_SHA256 = config.source.sha256
tango_adapter.MAPPING_SHA256 = config.source.mapping_contract_sha256
tango_adapter.TARGET_DECK_ID = config.source.deck_ids[0]
tango_adapter.SUPPORTED_NOTE_TYPE_ID = config.source.note_type_ids[0]
tango_adapter.MAPPING_VERSION = config.source.mapping_contract_version

raise SystemExit(main(arguments))
