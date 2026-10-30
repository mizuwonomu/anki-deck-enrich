"""Execute the public stage CLI with an explicitly test-scoped synthetic source check."""

from __future__ import annotations

import sys

import jp_deck.batching as batching
from synthetic_batching import validate_master

batching.validate_input_dataset = validate_master

from jp_deck.__main__ import main

raise SystemExit(main(sys.argv[1:]))
