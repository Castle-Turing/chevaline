# Chevaline

*Seed document from a design conversation in the Castle Turing repo
(2026-08-15); the project is being bootstrapped from it. The name is settled:
**Chevaline**, after Nell's mechanical horse in The Diamond Age — a loyal
companion bound to one rider that folds up and travels with her across every
territory. Personal agent config that travels with you across every project.
(The org, Castle Turing, is named from the same book.)*

## Mission

Define an open, plain-text, harness-agnostic standard for expressing a
*resident's* (a person's) agentic-development workflow preferences —
portable across every project and tool they use, not scoped to any single
codebase. The distribution mechanism is a git repo, the same convention as
dotfiles: adopting the standard means pointing your tooling at a repo that
implements it, not installing a package or registering with a service.

This project is the standard itself: schema, docs, and reference adapters.
It is not anyone's personal configuration. A separate, later project will
hold the author's own instance of it — not built here, not in this session.

## The gap this fills

A prior-art survey turned up adjacent things, each missing a piece of this:

- **AGENTS.md** — an emerging open convention, read by multiple harnesses
  (Codex, Cursor, Jules, others). Solves harness-agnostic instructions, but
  is *project*-scoped: it's checked into a repo and speaks to "any agent
  working on this codebase," not "this person, across everything they do."
- **EditorConfig** — cross-tool, but formatting-only and project-scoped.
- **Dotfiles managers** (chezmoi, yadm, dotbot) — the right structural
  precedent: one canonical source, rendered per-tool, portable across
  machines. But there's no standardized *content* for agent workflow in
  that ecosystem — each user's dotfiles are just a pile of tool-specific
  configs, with no shared schema.
- **Per-harness global config** (Claude Code's `~/.claude/CLAUDE.md` +
  `settings.json`, Codex's `~/.codex/` config) — acknowledges a user-level
  vs. project-level split, but each is single-harness and proprietary to
  that tool's config format.

Nothing sits at the intersection: user-owned *and* harness-agnostic *and*
content-standardized. That intersection is this project.

## The two-axis distinction

This distinction was hard-won in the originating conversation — don't
re-derive it, and don't let the schema blur it:

- **Axis 1 — framework/project governance.** How contributions land in a
  *specific* project. A project can be as opinionated as it wants here —
  name specific tools, mandate a specific review process — because the
  population it binds (people contributing to that project) already opted
  in by choosing to contribute rather than fork. This axis is not this
  project's concern and this standard should never try to override it.
- **Axis 2 — resident/operator preference.** How a person wants *their own*
  agent instances to behave, across every project they touch. Portable,
  harness-agnostic, needs a per-harness adapter to materialize into
  whatever config file a given harness actually reads. This is the only
  axis this project serves.

The two axes coexist per-project, not in a hierarchy — a resident's
preferences layer alongside a project's governance, they don't replace it.
Any schema field that could plausibly be expressed at *either* axis (see
"review/gate preferences" below) needs an explicit composition rule, not an
implicit assumption that axis 2 is the only policy in play.

## Fixed decisions

Treat these as constraints, not open questions:

- Distribution unit is a git repo (dotfiles convention), not a package
  registry or hosted service.
- This project is hosted under the `Castle-Turing` GitHub org, but must
  stand alone — no code or build dependency on Castle Turing in either
  direction. Someone who has never heard of Castle Turing should be able to
  adopt this standard for their own unrelated projects.
- Wesley's personal instance of this standard is a *separate* repo, built
  in a separate session, after this project has a real shape. Do not build
  personal config here.

## Starting menu

A prompt for what the schema probably needs to express — not a spec. The
actual design work, including whether these are the right categories,
belongs to this session.

- **Harness ordering/fallback** — which harness(es) the resident prefers,
  in what order.
- **The resident's own review/gate preferences** — e.g. "I always want a
  second-model opinion before merging." Flagged explicitly: this can
  collide with a project's own governance gates (axis 1), so the schema
  needs a *composition* rule — does a resident preference layer on top of
  what a project already requires, or override it? — rather than assuming
  the resident's preference is the only gate in play. This composition
  question isn't unique to review gates; it likely recurs anywhere axis 1
  and axis 2 both plausibly have an opinion (session-isolation convention
  is another candidate). Treat it as a first-class question in the schema,
  not something resolved field-by-field as it happens to come up.
- **Session-isolation convention** — e.g. worktree-per-session.
- **An authority taxonomy for the resident's own dev actions** —
  silent / reported / approval-gated, echoing Castle Turing's OS-level
  authority-taxonomy concept (vision.md, "decide the authority taxonomy
  early") applied one layer down, to the resident's own development work
  rather than to email/calendar/attention.
- **A way to reference executable content, not just declarative
  preferences** — e.g. a Python script the resident uses to orchestrate
  their own agents. This pushes the standard past pure config
  (EditorConfig-style) toward something closer to a plugin/extension model
  (dotfiles-manager-style: arbitrary scripts a renderer can invoke). The
  schema needs room for this rather than assuming everything reduces to a
  flat preference field.

## Castle Turing's touchpoint (bounded)

Castle Turing's private layer will document an optional slot for pulling in
a resident's repo that implements this standard, with sensible defaults if
the resident doesn't supply one. That's the only place the two projects
touch. This project has no dependency on Castle Turing's code, modules, or
conventions — it must work for someone who has never seen that repo.

## Non-goals for this session

- No personal-config content (Wesley's own preferences) — that's a later,
  separate repo.
- No hard-coupling the schema to any single harness's quirks (Claude Code,
  Codex, or otherwise) — every field should be justifiable as something a
  *different* harness's adapter could also render.
- No resolving the axis-1/axis-2 composition question fully in one sitting
  — naming it clearly in the schema is enough for a first pass.

## Suggested first actions

1. Settle the schema's actual shape. (The name is settled: Chevaline.)
2. Draft a short vision doc, if that structure is useful — Castle Turing's
   own `docs/vision.md` is a reasonable model but not a requirement.
3. `git init`, `gh repo create --org Castle-Turing <name> --public`, initial
   scaffold and first commit.
