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

## Process: audit *and* discovery

Re-auditing only re-examines standards already listed here, so on its own it
can never catch the failure that matters most — a standard we never knew
about. That failure has already happened twice: the `~/.agents` ecosystem
and Agent Skills were both found by accident, after the spec had shipped
fields that overlapped them.

So this ledger has two obligations, not one:

- **Audit** — re-check every entry's verdict when the spec version bumps or
  a tracked standard moves.
- **Discover** — a dated search pass for standards *not* yet listed, run at
  every minor spec bump and no less than quarterly. Record the date and the
  ground covered below even when it turns up nothing, so gaps in the sweep
  are visible rather than assumed.

Ground to re-sweep each pass: agent instruction conventions, user-level
config surfaces for any newly popular harness, agent capability/packaging
formats, permission and authority vocabularies, and anything occupying the
personal-cross-tool-profile niche.

| Discovery pass | Ground covered | Found |
|---|---|---|
| 2026-08-15 | prior-art survey for v0.1 | AGENTS.md, EditorConfig, dotfiles managers, per-harness config |
| 2026-08-15 | adjacent-standards sweep for v0.2 | `~/.agents` ecosystem, MCP tool annotations, Taplo/SchemaStore |
| 2026-08-15 | prompted by "are we reinventing Pi?" | **Agent Skills**, Pi |
| 2026-08-16 | prior art for the RFC process itself, before proposing to standardise it | LLM-as-reviewer literature (peer-review domain) |

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

## Agent Skills (`SKILL.md`) — stance: build on

An open standard for packaging a reusable agent capability, published by
Anthropic on 2025-12-18 and specified at
[agentskills.io/specification](https://agentskills.io/specification)
([repo](https://github.com/anthropics/skills)). A skill is a directory
containing a required `SKILL.md` — YAML frontmatter plus Markdown body —
and optional `scripts/`, `references/`, and `assets/` subdirectories.
Frontmatter is `name` and `description` (required), with optional
`license`, `compatibility`, `metadata`, and the experimental
`allowed-tools`. Agents load it progressively: metadata at startup, body on
activation, bundled files on demand. A reference validator (`skills-ref`)
exists.

Adoption is the widest of anything in this ledger: Microsoft and OpenAI
shipped support within 48 hours of publication, and it crossed 32 tools by
March 2026 — Claude Code, Cursor, Codex CLI, Gemini CLI, Copilot, JetBrains
Junie, AWS Kiro, Goose, and Google Antigravity among them.

**The nuance that decides our stance:** the specification standardizes the
*package format* and says nothing about where skills live on disk or how a
person installs the ones they want everywhere. There is no user-level
versus project-level distinction in it at all — discovery is left entirely
to implementations. That omission is precisely Chevaline's niche, so the
two are complementary rather than competing: Agent Skills defines the unit,
Chevaline says which units a *resident* carries and renders them into each
harness's skill location.

**Verdict: gap.** `[[extensions]]` (SPEC §3.10) invents an
`id`/`run`/`description` triple for referencing executable content and
defers an invocation protocol to future work — while an adopted standard
for exactly that already exists. This is Principle 5's "a field that
duplicates something the ecosystem has standardized is a bug" firing
against our own schema. Fix: `[[extensions]]` should reference skill
directories in `SKILL.md` format rather than define a parallel one, which
also collapses the "extension invocation protocol" open question instead of
answering it. Reopened in SPEC §3.10 and §5; not yet redesigned.

**Second finding, for the authority section.** The `allowed-tools` field
carries values like `Bash(git:*) Bash(jq:*) Read` — the pattern-scoped
permission syntax that SPEC §3.9 currently lacks and that the compass
review flagged as a gap. There is now prior art for that syntax inside an
open standard, so §3.9's eventual pattern support should match it rather
than invent a third spelling.

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
| Pi | `prompts` resource in settings | `~/.pi/agent/settings.json` |

[Pi](https://github.com/badlogic/pi-mono/blob/main/packages/coding-agent/README.md)
(earendil-works/pi) is a harness, not a competing standard — it belongs in
this table for the same reason Claude Code does. Its
[settings](https://pi.dev/docs/latest/settings) carry model and
`thinkingBudgets`, plus `packages`, `extensions`, `skills`, `prompts`, and
`themes` as declared resources. Two observations worth keeping:

- **Pi resolves the axis question the opposite way we do.** It reads a
  global `~/.pi/agent/settings.json` and a project `.pi/settings.json`,
  and "project settings override global settings." Plain override is the
  mode Chevaline deliberately excluded (SPEC §2.2). That does not
  invalidate our reasoning — Pi's project file is closer to axis-1
  governance, where winning is defensible — but it does mean
  `layer`/`defer`/`insist` is the unusual claim in this ecosystem and has
  to earn its keep rather than be assumed.
- **Its merge rule matches ours.** "Nested objects are merged" while
  values replace — the same semantics SPEC §2.1 fixed for environment
  overlays, arrived at independently.

Also note that personal Pi config repos already exist in the wild
([one example](https://github.com/LEUNGUU/pi-agent-config), described as
"personal configuration … for cross-environment sync"). That is Chevaline's
thesis emerging on its own, and confined to a single harness — evidence the
demand is real and the gap is real.

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

## LLM-as-reviewer research — stance: build on (process, not schema)

Not a standard and not about agent configuration, but it is prior art for
`docs/rfcs/`, whose reviewers are mostly models. The relevant body of work
is in scholarly peer review rather than engineering RFC process, and it has
already named failure modes this project was addressing by intuition:

- Documented biases include prestige framing, **assertion-strength
  sensitivity** (confidently stated claims draw softer criticism), rebuttal
  sycophancy, and prompt-injection vulnerability —
  [When Your Reviewer is an LLM](https://arxiv.org/html/2509.09912v1),
  [LLM-as-a-Reviewer](https://arxiv.org/pdf/2605.25415).
- **Humans and models weight differently:** humans emphasise novelty and
  clarity, model reviewers emphasise empirical rigour and technical detail
  — so "is this the right problem at all" is systematically under-served
  and must be asked for explicitly.
- Structured review schemas (dimension-tagged findings, explicit confidence)
  are established practice —
  [ReviewEval](https://arxiv.org/pdf/2502.11736),
  [survey](https://arxiv.org/pdf/2501.10326).
- [FactReview](https://arxiv.org/pdf/2604.04074) grounds review in
  execution-based claim verification, which is the same instinct as this
  project's evidence rule and its `Verified` field.

**Verdict: adheres, with an action taken.** The reviewer-question guidance
in `docs/rfcs/README.md` now cites these rather than asserting the failure
modes from first principles. Action outstanding: nobody here has read this
literature properly, only its abstracts — which is itself a reason not to
standardise our own process yet (see below).

**On making the RFC process a standard of its own.** Tempting, and premature
by this project's own rules: zero sweeps have been completed, it has been
exercised on one project, and a body of adjacent research exists that we
have not read. Standardising a process before running it once is precisely
the failure the process was created to prevent. Revisit when the process
has survived several sweeps across at least two unrelated projects — the
same two-users test every schema field has to pass.

## Dotfiles managers (chezmoi, yadm, dotbot) — stance: build on

The structural precedent (one canonical repo, rendered per-tool) and the
intended answer to machine-local overlays/secrets (SPEC §5): point at
them, don't rebuild them. A Chevaline profile should be manageable *by* a
dotfiles manager with no friction.

**Verdict: adheres** (nothing in v0.1 conflicts; keep it that way).
