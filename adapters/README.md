# Adapters

An adapter reads a Chevaline profile repo and renders it into one
harness's native config, per the adapter contract in SPEC.md §4:
validate, render idempotently, honor composition modes, report what it
skips, and never write outside the harness's own config locations.

Each adapter lives in its own directory here, named for the harness it
targets (e.g. `claude-code/`). To add one, create a new directory with a
README describing what it renders and how, and — once implemented — the
renderer itself. The standard does not prescribe an implementation
language or how an adapter runs (one-shot, shell-init hook, dotfiles-
manager plugin); see SPEC.md §4 for the full contract.
