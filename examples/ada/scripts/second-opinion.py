#!/usr/bin/env python3
"""second-opinion.py — Ada's "second-model-review" gate.

Referenced by chevaline.toml's [[gates]] entry with id
"second-model-review", bound to the "merge" moment. A harness adapter
that supports running gate scripts invokes this before letting a merge
through; a harness without that mechanism is expected to satisfy the gate
some other native way instead.

This is a stub for the examples/ada reference profile — it does not call
a real model. A real implementation would diff the pending change, send
it to a second model for review, and exit non-zero to block the merge on
a substantive objection.
"""

import sys


def get_second_opinion(diff: str) -> str:
    # Placeholder: a real version would call out to a second model here.
    return "no objections"


def main() -> int:
    diff = sys.stdin.read() if not sys.stdin.isatty() else ""
    opinion = get_second_opinion(diff)
    print(f"second-opinion: {opinion}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
