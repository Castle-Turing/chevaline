# Chevaline specification — v0.2 (draft)

Chevaline is a directory convention plus a manifest schema. A **profile** is
a git repo implementing this spec. A **resident** is the person the profile
belongs to. A **harness** is an agentic dev tool (Claude Code, Codex, Cursor,
…). An **adapter** renders a profile into a harness's native config.

## 1. Repo layout

```
chevaline.toml      # the manifest (required)
instructions/       # freeform prose the resident wants injected (optional)
scripts/            # executable content referenced by the manifest (optional)
```

Only `chevaline.toml` is required. All paths in the manifest are
repo-relative; a manifest that references a missing path is invalid.

The manifest is TOML: comment-friendly, unambiguous types, no
indentation-sensitivity, already idiomatic in dotfiles ecosystems.

## 2. Composition

Chevaline has **two** composition dimensions, and conflating them is the
easiest way to misread this spec:

1. **Environment resolution** (§2.1) — within axis 2, which of the
   resident's own values apply *here*. A profile is one repo, but a resident
   works in situations that differ (personal machine vs. employer, one
   billing account vs. another).
2. **Axis composition** (§2.2) — how the resulting resident preference sits
   alongside a project's own governance (axis 1).

**Resolution order is fixed: environments resolve first, producing the
effective axis-2 values; axis composition then applies those against project
governance.** An adapter that composes against a project before resolving
environments will apply the wrong values.

### 2.1 Environment resolution

Environments are declared in §3.2 and merged onto the base manifest in
declaration order — a later matching environment wins over an earlier one.

Merge semantics, which must not be guessed at:

- **Tables merge recursively.** `[environment.work.models]` naming only
  `cheap` overrides that tier and leaves `standard` and `deep` inherited
  from the base.
- **Scalars and arrays replace wholesale.** There is no element-wise array
  merge; an environment that sets `budget.limits` replaces the base's entire
  list rather than appending to it. Arrays have no stable identity to merge
  on, and a rule that guessed would be worse than one that is blunt.

Two rules make this fail-safe:

- **The base is the conservative floor.** Write the safe value at the base
  and let environments raise it explicitly. If no environment matches, the
  resident lands on the restrictive setting, never the permissive one.
- **Unknown selectors fail closed.** If an environment's `when` block uses a
  selector the adapter does not recognize, that environment MUST NOT match,
  and the adapter MUST report it (§4). Silently ignoring a selector would
  make an environment match in situations the resident excluded.

Environments are axis-2 only. A `when.path` or `when.git_org` selector may
*reference* a project, but what it selects is still the resident's own
preference — it binds nobody else and is not project governance.

### 2.2 Axis composition modes

Any preference that a project's own governance (axis 1) could also have an
opinion about carries an explicit `compose` key. Modes, defined once and
used everywhere:

- **`layer`** (default) — the preference adds on top of whatever the project
  requires. Project gates still run; this one runs too.
- **`defer`** — apply only if the project has no opinion of its own in this
  area; otherwise the project's convention is used and this preference is
  ignored.
- **`insist`** — if the project's convention conflicts, do not silently
  yield *or* override: surface the conflict to the resident and wait.

There is deliberately no `override` mode. A resident preference never
overrides project governance; `insist` — "stop and tell me" — is the
strongest expressible stance.

How an adapter *detects* a project opinion is harness-specific and out of
scope for v0.2; the modes define the required behavior once a conflict is
known.

Sections that carry no `compose` key are axis-2 only, because axis 1 has no
standing to have an opinion: instructions (§3.6) describe the resident,
authority (§3.9) can only tighten, and budget (§3.5) is the resident's own
wallet.

## 3. Manifest schema

### 3.1 Header

```toml
spec = "0.2"            # Chevaline spec version this profile targets

[resident]
name = "Ada"            # optional; adapters may interpolate into rendered config
```

The spec is versioned per [SemVer 2.0.0](https://semver.org) — a
deliberate choice, since neighboring specs differ (EditorConfig uses
SemVer, MCP uses dates, AGENTS.md is unversioned). `spec` may omit the
patch component; `"0.2"` means `0.2.x`.

### 3.2 Environments

An environment is a named overlay on the base manifest, selected by a
`when` block. It exists because some preferences are situational — a
resident's token budget at work is not their budget at home — while most
preferences should travel unchanged.

```toml
[environment.work]
when.git_org = "acme"           # predicates AND together
when.path = "~/work/**"

[environment.work.budget]
on_exceed = "halt"
limits = [ { scope = "*", window = "session", amount = 2_000_000, unit = "tokens" } ]
```

Selectors, a closed set:

| Selector | Matches on |
|---|---|
| `path` | glob against the working directory |
| `hostname` | the machine's hostname |
| `git_org` | the owner/org of the repo's git remote |
| `env` | an environment variable, as `"NAME=value"` |

All predicates in a `when` block must hold for the environment to apply. An
environment with no `when` block never matches automatically and can only be
activated explicitly by an adapter.

`env` is the universal escape hatch. A resident whose environments really
track a *credential* — a work API key vs. a personal one — sets the variable
alongside the key in the shell profile or direnv file where the key already
lives, rather than putting anything credential-shaped in a profile repo that
is public by convention.

An environment may override any section below except the header. Prior art
for this pattern is well established and Chevaline deliberately borrows
rather than invents: git's `[includeIf "gitdir:…"]` solves the same
work-vs-personal split by directory, chezmoi and yadm vary by hostname and
class, and AWS and kubectl both pair named contexts with an env-var
selector. What Chevaline does *not* borrow is a templating language — the
selector set stays closed and declarative on purpose.

### 3.3 Harness preference

```toml
[harnesses]
prefer = ["claude-code", "codex"]   # ordered; first available wins
```

Names are lowercase kebab-case identifiers. v0.2 does not maintain a
registry; adapters match their own name and ignore the rest. An empty or
absent list means "no preference."

### 3.4 Models and tiers

Residents care about cost and capability tiers, not model identifiers.
Identifiers churn — the tier does not — so Chevaline expresses preferences
against **tiers** and confines model identifiers to a single binding per
environment.

```toml
[models]                                  # base
cheap    = "claude-haiku-4-5"
standard = "claude-sonnet-4-5"
deep     = "claude-opus-4-5"

[environment.work]
models = { cheap = "qwen2.5-coder", deep = "llama-3.3-405b" }
```

The tier vocabulary is `cheap`, `standard`, and `deep`, plus `x.`-prefixed
custom tiers that adapters may ignore. Three tiers reflects real
convergence: Codex ships `cheap`/`standard`/`deep` profiles and the
haiku/sonnet/opus split is the same shape.

A tier maps to **whatever knob the harness actually has**, which is why it
is the portable unit and a model identifier is not. Where a harness offers
several models, a tier selects one. Where it offers a single model, a tier
may instead select a reasoning-effort level or a provider endpoint — Codex's
own `cheap` profile does exactly this, holding the model fixed and dropping
reasoning effort. Adapters MUST map tiers to their native mechanism and MUST
report (§4) when they cannot.

### 3.5 Budget

A ceiling on what the resident's agents may consume, enforced rather than
reported.

```toml
[budget]
on_exceed = "halt"                  # halt | warn
limits = [
  { scope = "*",             window = "session", amount = 2_000_000, unit = "tokens" },
  { scope = "deep",          window = "day",     amount =   500_000, unit = "tokens" },
  { scope = "claude-opus-*", window = "day",     amount =        20, unit = "USD"    },
]
```

- **`scope`** — `*` for the aggregate, a tier name from §3.4, or a glob
  against model identifiers for the genuinely model-specific case. A glob
  also survives model churn better than an exact identifier.
- **`window`** — `session` or `day`.
- **`amount`** — a positive number.
- **`unit`** — `tokens`, an [ISO 4217](https://www.iso.org/iso-4217-currency-codes.html)
  currency code, or an `x.`-prefixed custom unit. There is **no default**:
  an omitted unit is invalid, so that no currency is privileged by the
  schema and no profile silently means dollars.
- **`on_exceed`** — `halt` stops before the next model call; `warn` reports
  and continues. Both exist because real credit systems have both.

Three semantics that must not be guessed at:

**The resolved budget MUST contain at least one `scope = "*"` limit.**
Per-tier limits alone sum to something unbounded, and a model bound to no
tier would escape entirely. The aggregate limit is what guarantees nothing
ever runs uncapped.

The requirement binds the budget *after* environment resolution, not each
literal block. Because `limits` is an array it replaces wholesale (§2.1), so
an environment that overrides `limits` must restate its own aggregate limit
— inheriting the base's is not possible. A resolved budget with no
aggregate limit is an invalid profile, and an adapter MUST refuse it rather
than run uncapped: this is the one place where the fail-safe rule is
enforced by validation instead of by convention.

**Overlapping limits are conjunctive.** Every limit whose `scope` matches is
live simultaneously, and the *first one exhausted* triggers `on_exceed`. A
tier limit does not replace the aggregate. This is the opposite of the
most-specific-wins resolution used for authority classes (§3.9), and the
difference is deliberate: budgets are quotas, and real quota systems bind
every applicable one at once.

**Token counts are provider-reported.** Tokenizers differ across model
families, so a token is only comparable within a provider. Adapters MUST use
the provider's own usage reporting and MUST NOT substitute a client-side
estimate. It follows that a token limit is only meaningful when the models
in scope are homogeneous — a resident mixing tiers under one aggregate token
cap is measuring very little, and should scope limits per tier or use a
currency unit instead.

Budget is axis-2 only and carries no `compose` key: a project has no
standing to spend the resident's money or quota.

### 3.6 Instructions (portable prose)

Much of what residents put in per-harness global config today is prose —
communication style, review taste, standing habits. Chevaline makes that
prose portable:

```toml
[[instructions]]
path = "instructions/communication.md"

[[instructions]]
path = "instructions/testing-habits.md"
harnesses = ["claude-code"]         # optional filter; default: all
```

Adapters concatenate applicable blocks, in order, into the harness's native
instruction channel. Where a harness offers an AGENTS.md-compatible
user-level channel (e.g. Codex's `~/.codex/AGENTS.md`), adapters SHOULD
prefer it over a proprietary one; if the AGENTS.md convention gains a
global scope (its issue #91), that becomes the preferred shared target.
Instructions are axis-2 by nature (they describe the resident, not any
project) and carry no `compose` key.

### 3.7 Gates

Standing checks the resident wants on their own work, e.g. "a second-model
opinion before merging."

```toml
[[gates]]
id = "second-model-review"
on = "merge"                        # merge | commit | push | session-end
description = "Get a second model's review before merging"
compose = "layer"
run = "scripts/second-opinion.py"   # optional; otherwise the harness's own
                                    # native mechanism satisfies the gate
```

`on` names the moment the gate binds to, in harness-neutral terms. Gates are
the canonical axis-1 collision case; `compose` is required in spirit even
though it defaults to `layer` — profiles are encouraged to state it.

### 3.8 Sessions

```toml
[sessions]
isolation = "worktree"              # worktree | branch | in-place | container
compose = "defer"
```

`defer` is the sensible default here: many projects already mandate a
contribution flow, and session isolation is exactly the kind of convention a
project may own.

### 3.9 Authority

How much latitude the resident grants their own agents, per action class —
`silent` (just do it), `reported` (do it and tell me), `approval` (ask
first). This echoes an OS-level authority-taxonomy idea one layer down, to
the resident's own dev actions.

```toml
[authority]
default = "reported"

[authority.actions]
"fs.write" = "silent"        # edits within the working tree
"vcs.commit" = "reported"
"vcs.push" = "approval"
"vcs.publish" = "approval"   # PRs, releases, anything outward-facing
"deps.change" = "approval"   # add/remove/upgrade dependencies
"net.fetch" = "silent"       # read-only network access
"exec.install" = "approval"  # installing tools onto the machine
```

v0.2 defines the namespaced classes above as a starting vocabulary; profiles
may add custom `x.`-prefixed classes, which adapters may ignore. Authority is
axis-2 only (it constrains the resident's own agents; it can tighten but
never loosen anything a project or harness already restricts), so it carries
no `compose` key — the effective permission is the *stricter* of the two
axes, always. Strictness is totally ordered:
`silent` < `reported` < `approval`.

### 3.10 Extensions (executable content)

Escape hatch past pure config: scripts the resident uses to orchestrate
their own agents.

```toml
[[extensions]]
id = "orchestrator"
run = "scripts/orchestrate.py"
description = "Fan out a task across several agent sessions"
```

v0.2 deliberately specifies only *identification* (an id, an entrypoint, a
description), not an invocation protocol — how a harness exposes an
extension (slash command, hook, manual run) is adapter-defined. Extensions
exist in the schema now so the standard's shape accommodates them; the
protocol is future work.

> **This section is under review and is the most likely part of v0.2 to
> change.** The [Agent Skills standard](https://agentskills.io/specification)
> already defines a portable format for exactly this — a directory with a
> `SKILL.md` (YAML frontmatter plus instructions) and optional `scripts/`,
> `references/`, and `assets/` — and it is read by 32+ harnesses. Under
> Principle 5, `[[extensions]]` has to justify defining a parallel
> `id`/`run`/`description` triple, and it currently cannot.
>
> What Agent Skills does *not* specify is where skills live or how a person
> installs the ones they want across every tool: it standardizes the unit,
> not the resident's collection of them. That gap is Chevaline's, which
> makes the two complementary. The expected resolution is that
> `[[extensions]]` references skill directories in `SKILL.md` format and
> adapters install them into each harness's skill location — which dissolves
> the invocation-protocol question rather than answering it. Not yet
> redesigned; see `docs/standards.md`.

## 4. Adapter contract

An adapter, given the path to a profile repo, MUST:

1. **Validate** the manifest against the spec version it declares, and fail
   loudly on an invalid profile.
2. **Resolve environments before rendering**, in the order fixed by §2, and
   be able to report which environments matched and which selector decided
   it. "Why is my cap this number?" must have an answer.
3. **Render idempotently** into the harness's native config — running twice
   produces the same result, and re-running after a profile change updates
   the rendered output. Rendered regions must be delimited (e.g. marker
   comments) so they never clobber config the resident wrote by hand.
4. **Honor composition modes** as defined in §2.2 for every field that
   carries one.
5. **Report what it skipped.** A field the harness cannot express is
   dropped *visibly* (a rendering report), never silently.
6. **Never write outside** the harness's own config locations.

### 4.1 Budget enforcement

Budget carries stricter obligations than the rest of the schema, because a
cap that silently fails to bind is worse than no cap at all.

- **`tokens` support is mandatory.** Token limits require nothing but the
  usage figures a provider already returns, so every adapter can enforce
  them.
- **Currency support is optional, and must show its work.** Enforcing a
  currency limit requires a pricing table, which is external data that goes
  stale. An adapter that supports currency units MUST disclose the pricing
  table and assumptions it used when reporting spend.
- **No conversion between units, ever.** An adapter MUST NOT convert between
  currencies, or between tokens and currency. If a profile declares a limit
  in a unit the provider does not bill in, the adapter reports that it
  cannot enforce it.
- **Unenforceable means loud, not silent.** If an adapter cannot enforce a
  declared limit, it MUST report that prominently and MUST NOT present the
  profile as enforced. Running uncapped while appearing capped is the
  failure mode this section exists to prevent.

## 5. Open questions (tracked, not resolved in v0.2)

- **Renderer vs. mechanism** — §4 assumes every preference renders into a
  native config file, but budget disproves it: no harness config expresses
  "halt before the next model call," so enforcement needs a runtime
  component (compass built a localhost proxy for exactly this). The standard
  has no vocabulary for "this field requires a mechanism, not a rendering."
- **Tier naming** — `cheap` is a cost word doing duty on a capability axis,
  and it reads oddly for a self-hosted tier whose marginal cost is zero.
  `light`/`standard`/`deep` may age better. Decide before v1.0 freezes names.
- **Project-opinion detection** — a harness-neutral way for adapters to know
  a project has an axis-1 stance (needed for `defer`/`insist` to be more
  than best-effort). Candidate: recognize AGENTS.md and per-harness project
  config as opinion signals.
- **Adopt Agent Skills for `[[extensions]]`** (supersedes the former
  "extension invocation protocol" question). Rather than specify arguments,
  environment, and lifecycle ourselves, reference `SKILL.md` directories and
  let adapters install them. Open sub-questions: whether a gate's `run`
  script also becomes a skill or stays a plain entrypoint; whether a profile
  bundles skill directories in-repo, references them by path, or both; and
  whether §3.9 authority should adopt the `allowed-tools` pattern syntax
  (`Bash(git:*) Read`) instead of inventing a third spelling for the same
  idea.
- **Harness name registry** — §3.3 disclaims a registry, but exact-string
  matching in §3.6 and §4 creates one by convention. A non-normative list of
  known names ("claude-code", "codex", …) would reduce typo-drift.
- **Secrets/machine-locals** — profiles are public-shaped git repos; whether
  the standard needs a convention for machine-local overlays. §3.2's `env`
  selector covers credential-keyed *selection*; machine-local *values* are
  still unaddressed, and dotfiles managers may simply be the answer.
- **Schema formalization** — a JSON Schema for `chevaline.toml` once the
  field set stabilizes, validated via Taplo and submitted to SchemaStore.org
  for zero-setup editor validation.
- **`~/.agents` ecosystem interop** — early efforts exist in the same niche
  (dotStandards `.agents`, dot-agents; see `docs/standards.md`). Before
  v1.0 freezes field names: should adapters also render into `~/.agents/`
  layouts, and is any of their vocabulary worth adopting?
