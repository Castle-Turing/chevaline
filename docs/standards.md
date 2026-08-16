# Standards ledger

The enforcement mechanism for vision.md Principle 5 ("Honor prior art").
One entry per adjacent standard: what it is, Chevaline's **stance** toward
it, and an **audit verdict** for the current spec. Stances:

- **build on** — Chevaline uses it directly.
- **render into** — adapters emit into it; it's an output surface.
- **track** — not usable yet, but convergence is expected; watch it.
- **diverge** — Chevaline deliberately does its own thing, with a reason.

Verdicts: **adheres** / **gap** (with the fix) / **justified divergence**
(with the reason). Re-audit whenever the spec version bumps or a tracked
standard moves. Last audited: 2026-08-15, against spec v0.2 draft.

## AGENTS.md — stance: render into + track

Open Markdown convention for agent instructions, stewarded by the Agentic
AI Foundation (Linux Foundation); read by 30+ harnesses. Today it is
**project-scoped only** — exactly the axis-1 half of the two-axis split —
so it is not a substitute for Chevaline. Two open proposals matter to us:

- [issue #91](https://github.com/agentsmd/agents.md/issues/91): a global
  `~/.config/agents/AGENTS.md`. If this lands, it becomes the *preferred
  render target* for §3.6 instructions — one write serves every
  AGENTS.md-reading harness, and per-harness instruction rendering becomes
  the fallback, not the default.
- [issue #135](https://github.com/agentsmd/agents.md/issues/135): spec
  versioning + frontmatter; affects how adapters should delimit rendered
  regions in Markdown.

Some harnesses already read a user-level AGENTS.md natively (Codex:
`~/.codex/AGENTS.md`) — adapters should prefer that channel where it
exists.

**Verdict: adheres, with an action.** §3.6 instructions are portable prose
rendered into native channels, which is the right shape. Action: the
adapter contract should name AGENTS.md-compatible channels as the
preferred instruction target where a harness offers one.

## `~/.agents`-style profiles — stance: track (closest neighbors)

Efforts in Chevaline's own niche, found 2026-08-15; all early-stage:

- [dotStandards `.agents`](https://dotstandards.info/standards/agents/) —
  `~/.agents/profile/user.md` etc. for cross-tool user identity/knowledge.
- [dot-agents](https://www.dot-agents.com/)
  ([specs](https://github.com/seflless/dot-agents/tree/main/specs)) — "one
  config, every AI agent," unifying Cursor/Claude Code/Codex/OpenCode
  under `~/.agents/`.
- [dotagents.io](https://dotagents.io/) — project-scoped `.agents/` dir;
  axis 1, not our niche, listed to avoid confusion.

None appears to carry Chevaline's composition model (the axis-1/axis-2
distinction and layer/defer/insist), which remains the differentiator.

**Verdict: gap.** The v0.1 prior-art survey missed these. Fix (done in the
same commit as this ledger): acknowledge them in vision.md; open question
in SPEC §5 on interop — at minimum, whether Chevaline adapters should
also render into `~/.agents/` layouts, and whether any of their vocabulary
is worth adopting before v0.2 freezes field names. Needs a closer manual
read of their specs.

## Per-harness user config surfaces — stance: render into

The adapter output targets, as of mid-2026:

| Harness | Instructions | Settings/permissions |
|---|---|---|
| Claude Code | `~/.claude/CLAUDE.md` | `~/.claude/settings.json` |
| Codex CLI | `~/.codex/AGENTS.md` | `~/.codex/config.toml` (`approval_policy`) |
| Cursor | User Rules (`~/.cursor`) | — |
| Gemini CLI | `~/.gemini/GEMINI.md` | `~/.gemini/settings.json` |

**Verdict: adheres.** This is what the adapter contract exists for.

## Permission/authority taxonomies — stance: diverge (justified)

No cross-tool standard exists. Nearest things: Codex's `approval_policy`
(`untrusted | on-request | never`) — the closest shipping analogue to
§3.9's `silent`/`reported`/`approval` and an obvious adapter mapping — and
MCP tool annotations (`readOnlyHint`, `destructiveHint`, …), which are
advisory metadata about *tools*, not a resident-side authority grant, so
not adoptable as our vocabulary. NIST/CAISI has a rumored agent-interop
profile (Q4 2026, unconfirmed).

**Verdict: justified divergence.** §3.9 fills a real vacuum. Adapters
should map to native enforcement (Codex `approval_policy`, Claude Code
permission rules) rather than reimplementing it; revisit if a real
standard emerges.

## TOML / Taplo / SchemaStore — stance: build on

TOML v1.0 manifest; Taplo is the de facto validator and reads JSON Schema
via a `#:schema` directive, with SchemaStore.org filename-based
auto-detection.

**Verdict: adheres.** Concrete path for the SPEC §5 "schema formalization"
item: publish a JSON Schema for `chevaline.toml` and submit it to
SchemaStore so editors validate profiles with zero setup.

## SemVer — stance: build on (deliberate choice)

Spec versioning is not uniform across neighbors (EditorConfig: SemVer;
MCP: date-based; AGENTS.md: unversioned), so this is a choice, not an
inherited convention.

**Verdict: gap (fixed).** v0.1 didn't state its versioning policy; SPEC.md
now declares SemVer 2.0.0 for the spec version.

## Dotfiles managers (chezmoi, yadm, dotbot) — stance: build on

The structural precedent (one canonical repo, rendered per-tool) and the
intended answer to machine-local overlays/secrets (SPEC §5): point at
them, don't rebuild them. A Chevaline profile should be manageable *by* a
dotfiles manager with no friction.

**Verdict: adheres** (nothing in v0.1 conflicts; keep it that way).
