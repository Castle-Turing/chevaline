# claude-code adapter

**Status: not yet implemented.** This is a stub describing the intended
design, not working code.

## What it will do

Given the path to a Chevaline profile, this adapter will render it into
Claude Code's native global config: `~/.claude/CLAUDE.md` and
`~/.claude/settings.json`. Per the adapter contract in SPEC.md §4, it
will validate the manifest against its declared spec version, render
idempotently, honor each field's composition mode, and print a report of
anything it could not express in Claude Code's config surfaces rather
than dropping it silently.

Idempotent, non-clobbering re-rendering works differently for the two
targets, because they don't share a format. `CLAUDE.md` is prose with
comments, so the adapter can wrap its output in marker comments and only
touch what's between them. `settings.json` is JSON, which has no comment
syntax to hold a marker — SPEC.md §4 item 3 requires a comment-less format
to instead record the keys it owns in a **sidecar manifest** alongside the
rendered file (e.g. `~/.claude/settings.chevaline.json`, a flat list of
the JSON paths this adapter last wrote), and touch only those keys on
re-render, leaving everything else the resident wrote by hand alone.

## Mapping

| Manifest section          | Claude Code surface                              |
|----------------------------|---------------------------------------------------|
| `[[instructions]]`         | `~/.claude/CLAUDE.md` (marker-delimited region)   |
| `[authority]`              | `~/.claude/settings.json` `permissions`           |
| `[harnesses]`              | Used to decide whether this adapter runs at all   |
| `[[environment]]`          | Resolved before rendering; never rendered itself  |
| `[models]`                 | Partial — `settings.json` `model` takes one tier  |
| `[budget]`                 | No config surface — needs a hook (see below)      |
| `[[gates]]`                | TBD — likely a hook, if `run` is set               |
| `[sessions]`                | TBD — no direct Claude Code settings equivalent yet |
| `[[extensions]]`           | TBD — candidate: slash commands or hooks           |

Rows marked TBD have no settled Claude Code config surface yet; the
rendering report will call these out as skipped until one is designed.

`[[environment]]` is not a render target: per SPEC.md §2, environments
resolve *first*, and this adapter renders the resulting effective values.
It must be able to report which environment matched and which selector
decided it — and, per SPEC.md §3.2, whether that environment matched via
its own `when` block or via explicit activation (selecting it by `name`,
bypassing `when` entirely).

`[models]` maps only partially. Claude Code's `settings.json` carries a
single default `model`, so one tier renders directly and the others have
no global surface — per-subagent model pinning is the closest fit. The
rendering report should name the tiers it could not express.

`[budget]` is this adapter's instance of the renderer-vs-mechanism problem
in SPEC.md §5: no Claude Code setting expresses "halt before the next
model call," so a rendered config alone cannot satisfy §4.1. The intended
implementation is a `PreToolUse` hook that reads session usage and blocks
when a limit is exhausted. Until that exists, the adapter MUST report
budget as unenforced rather than presenting the profile as enforced.
