# Chevaline — vision

Chevaline is an open, plain-text, harness-agnostic standard for expressing a
**resident's** (a person's) agentic-development workflow preferences —
portable across every project and every tool they use, not scoped to any
single codebase.

The name is from Neal Stephenson's *The Diamond Age*: Chevaline is Nell's
mechanical horse — a companion bound to one rider that folds up and travels
with her across every territory she enters. That is the shape of this
standard: personal agent configuration that travels with you across every
project.

## The gap

Adjacent things exist, each missing a piece:

- **AGENTS.md** solves harness-agnostic instructions, but is
  *project*-scoped — it speaks to "any agent working on this codebase," not
  "this person, across everything they do."
- **EditorConfig** is cross-tool, but formatting-only and project-scoped.
- **Dotfiles managers** (chezmoi, yadm, dotbot) are the right structural
  precedent — one canonical source, rendered per-tool — but there is no
  standardized *content* for agent workflow in that ecosystem.
- **Per-harness global config** (`~/.claude/`, `~/.codex/`) acknowledges the
  user-level/project-level split, but each is single-harness and proprietary.
- **`~/.agents`-style efforts** (dotStandards `.agents`, dot-agents) are the
  closest neighbors — user-scoped and cross-tool — but early-stage and
  without the governance-vs-preference composition model that shapes this
  schema. Tracked in [standards.md](standards.md).

Nothing sits fully at the intersection: user-owned *and* harness-agnostic
*and* content-standardized *and* explicit about composing with project
governance. Chevaline is that intersection.

## The two-axis distinction

- **Axis 1 — project governance.** How contributions land in a *specific*
  project. Projects can be as opinionated as they want here; contributors
  opted in by contributing rather than forking. Chevaline never overrides
  this axis.
- **Axis 2 — resident preference.** How a person wants *their own* agent
  instances to behave, everywhere. This is the only axis Chevaline serves.

The axes coexist per-project, not in a hierarchy. Wherever both axes could
plausibly have an opinion, the schema carries an explicit **composition
mode** rather than an implicit assumption. There is deliberately no
"override" mode: the strongest stance a resident can express is *insist* —
"surface the conflict to me" — never "ignore the project."

## Principles

1. **User-owned.** A Chevaline profile is a git repo the resident controls,
   adopted the way dotfiles are adopted — by pointing tooling at it, not by
   installing a package or registering with a service.
2. **Harness-agnostic.** Every schema field must be justifiable as something
   more than one harness's adapter could render. No field exists to serve a
   single tool's quirk.
3. **Declarative core, executable edges.** The manifest is plain declarative
   text, but the standard leaves room for referenced executable content
   (scripts a resident uses to orchestrate their own agents) — closer to a
   dotfiles manager than to EditorConfig.
4. **Adapters are renderers.** An adapter reads a Chevaline repo and emits a
   harness's native config. The standard specifies the input contract and
   stays silent on how adapters run. Adapters must not silently drop what
   they cannot render.
5. **Honor prior art.** Chevaline exists because nothing else sits at its
   intersection — not because the neighbors are wrong. Where an existing or
   emerging convention already expresses something the schema needs, map to
   it rather than compete with it: render *into* native and shared surfaces
   (AGENTS.md-style instruction channels, each harness's own config), build
   *on* standard formats and practices (TOML, SemVer, JSON Schema), and
   track the neighbors so convergence is deliberate. Concretely: every
   schema field must answer "why isn't this an existing standard?", and
   [standards.md](standards.md) is the living ledger of adjacent standards,
   Chevaline's stance toward each, and audits of the spec against this
   principle. A field that duplicates something the ecosystem has since
   standardized is a bug, not a feature.

## Non-goals

- Chevaline is the standard — schema, docs, reference adapters. It is not
  anyone's personal configuration.
- It does not express project governance (axis 1) and never overrides it.
- It has no dependency on any other project, including Castle Turing (the
  org it lives under); anyone can adopt it for unrelated work.
