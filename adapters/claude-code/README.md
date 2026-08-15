# claude-code adapter

**Status: not yet implemented.** This is a stub describing the intended
design, not working code.

## What it will do

Given the path to a Chevaline profile, this adapter will render it into
Claude Code's native global config: `~/.claude/CLAUDE.md` and
`~/.claude/settings.json`. Per the adapter contract in SPEC.md §4, it
will validate the manifest against its declared spec version, render
idempotently into marker-delimited regions (so hand-written config above
and below the markers is never clobbered), honor each field's composition
mode, and print a report of anything it could not express in Claude
Code's config surfaces rather than dropping it silently.

## Mapping

| Manifest section          | Claude Code surface                              |
|----------------------------|---------------------------------------------------|
| `[[instructions]]`         | `~/.claude/CLAUDE.md` (marker-delimited region)   |
| `[authority]`              | `~/.claude/settings.json` `permissions`           |
| `[harnesses]`              | Used to decide whether this adapter runs at all   |
| `[[gates]]`                | TBD — likely a hook, if `run` is set               |
| `[sessions]`                | TBD — no direct Claude Code settings equivalent yet |
| `[[extensions]]`           | TBD — candidate: slash commands or hooks           |

Rows marked TBD have no settled Claude Code config surface yet; the
rendering report will call these out as skipped until one is designed.
