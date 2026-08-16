# Chevaline

An open, plain-text, harness-agnostic standard for expressing a person's
agentic-development workflow preferences — portable across every project
and every tool they use. Dotfiles for your agents.

## What it is

Per-harness global config (`~/.claude/CLAUDE.md`, `~/.codex/`) already
splits user-level preference from project-level instruction, but each is
single-harness and proprietary. Project-scoped conventions like AGENTS.md
solve harness-agnostic instructions, but speak to "any agent working on
this codebase," not "this person, across everything they do." Dotfiles
managers (chezmoi, yadm, dotbot) have the right shape — one canonical
source, rendered per-tool — but no shared schema for agent workflow.

Chevaline sits at the intersection: user-owned, harness-agnostic, and
content-standardized. A **profile** is a git repo — the same distribution
model as dotfiles, adopted by pointing your tooling at it, not by
installing a package. An **adapter** renders a profile into a given
harness's native config. See [docs/vision.md](docs/vision.md) for the full
case, including the axis-1/axis-2 distinction between project governance
and resident preference that shapes the schema.

This repo is the standard itself — schema, docs, and reference adapters.
It is not anyone's personal configuration; a resident's own profile is a
separate repo that implements this spec.

## A minimal profile

```toml
spec = "0.3"

[resident]
name = "Ada"

[budget]
on_exceed = "halt"
limits = [ { scope = "*", window = "day", amount = 10, unit = "USD" } ]

[[instructions]]
path = "instructions/communication.md"

[authority]
default = "reported"

[authority.actions]
"vcs.push" = "approval"
```

See [SPEC.md](SPEC.md) §3 for the full schema, and
[examples/ada/](examples/ada/) for a complete profile exercising every
section.

## Repo layout

```
SPEC.md              # the v0.3 manifest specification
docs/vision.md        # the case for this standard, in full
examples/ada/         # a complete fictional reference profile
adapters/             # per-harness adapters (renderers)
```

- [SPEC.md](SPEC.md) — the manifest schema and adapter contract.
- [docs/vision.md](docs/vision.md) — the gap this fills, the two-axis
  distinction, and the principles behind the schema.
- [examples/ada/](examples/ada/) — a fictional profile, valid per the spec.
- [adapters/](adapters/) — reference adapters; see
  [adapters/claude-code/](adapters/claude-code/) for the first one (not yet
  implemented).

## Name

Chevaline is Nell's mechanical horse in Neal Stephenson's *The Diamond
Age* — a companion bound to one rider that folds up and travels with her
across every territory.

## Status

v0.3 draft. The schema, repo layout, and adapter contract are drafted in
SPEC.md; no adapter is implemented yet.
