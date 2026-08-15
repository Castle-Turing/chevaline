#!/usr/bin/env python3
"""orchestrate.py — Ada's "orchestrator" extension.

Referenced by chevaline.toml's [[extensions]] entry with id
"orchestrator". Extensions are identified, not invoked, by the spec
(SPEC.md §3.7); how a harness exposes this — slash command, hook, manual
run — is adapter-defined and out of scope here.

This is a stub for the examples/ada reference profile. A real version
would fan a task out across several agent sessions and collect results.
"""

import sys
from dataclasses import dataclass


@dataclass
class Subtask:
    description: str


def fan_out(task: str, n: int = 3) -> list[Subtask]:
    # Placeholder: a real version would split `task` into subtasks and
    # launch a session per subtask.
    return [Subtask(description=f"{task} (part {i + 1}/{n})") for i in range(n)]


def main(argv: list[str]) -> int:
    task = " ".join(argv[1:]) or "unspecified task"
    for subtask in fan_out(task):
        print(f"would launch session for: {subtask.description}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
