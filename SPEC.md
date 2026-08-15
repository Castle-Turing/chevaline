# Chevaline specification — v0.1 (draft)

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

## 2. Composition modes

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
scope for v0.1; the modes define the required behavior once a conflict is
known.

## 3. Manifest schema

### 3.1 Header

```toml
spec = "0.1"            # Chevaline spec version this profile targets

[resident]
name = "Ada"            # optional; adapters may interpolate into rendered config
```

### 3.2 Harness preference

```toml
[harnesses]
prefer = ["claude-code", "codex"]   # ordered; first available wins
```

Names are lowercase kebab-case identifiers. v0.1 does not maintain a
registry; adapters match their own name and ignore the rest. An empty or
absent list means "no preference."

### 3.3 Instructions (portable prose)

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
instruction channel (e.g. `~/.claude/CLAUDE.md`). Instructions are axis-2 by
nature (they describe the resident, not any project) and carry no `compose`
key.

### 3.4 Gates

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

### 3.5 Sessions

```toml
[sessions]
isolation = "worktree"              # worktree | branch | in-place | container
compose = "defer"
```

`defer` is the sensible default here: many projects already mandate a
contribution flow, and session isolation is exactly the kind of convention a
project may own.

### 3.6 Authority

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

v0.1 defines the namespaced classes above as a starting vocabulary; profiles
may add custom `x.`-prefixed classes, which adapters may ignore. Authority is
axis-2 only (it constrains the resident's own agents; it can tighten but
never loosen anything a project or harness already restricts), so it carries
no `compose` key — the effective permission is the *stricter* of the two
axes, always. Strictness is totally ordered:
`silent` < `reported` < `approval`.

### 3.7 Extensions (executable content)

Escape hatch past pure config: scripts the resident uses to orchestrate
their own agents.

```toml
[[extensions]]
id = "orchestrator"
run = "scripts/orchestrate.py"
description = "Fan out a task across several agent sessions"
```

v0.1 deliberately specifies only *identification* (an id, an entrypoint, a
description), not an invocation protocol — how a harness exposes an
extension (slash command, hook, manual run) is adapter-defined. Extensions
exist in the schema now so the standard's shape accommodates them; the
protocol is future work.

## 4. Adapter contract

An adapter, given the path to a profile repo, MUST:

1. **Validate** the manifest against the spec version it declares, and fail
   loudly on an invalid profile.
2. **Render idempotently** into the harness's native config — running twice
   produces the same result, and re-running after a profile change updates
   the rendered output. Rendered regions must be delimited (e.g. marker
   comments) so they never clobber config the resident wrote by hand.
3. **Honor composition modes** as defined in §2 for every field that
   carries one.
4. **Report what it skipped.** A field the harness cannot express is
   dropped *visibly* (a rendering report), never silently.
5. **Never write outside** the harness's own config locations.

Adapters MAY run as one-shot renderers, shell-init hooks, or dotfiles-manager
plugins; the standard does not care.

## 5. Open questions (tracked, not resolved in v0.1)

- **Project-opinion detection** — a harness-neutral way for adapters to know
  a project has an axis-1 stance (needed for `defer`/`insist` to be more
  than best-effort). Candidate: recognize AGENTS.md and per-harness project
  config as opinion signals.
- **Extension invocation protocol** — arguments, environment, and lifecycle
  for `[[extensions]]` entrypoints, and whether a gate's `run` script follows
  the same protocol (the two fields are the same shape; their relationship is
  currently unstated).
- **Harness name registry** — §3.2 disclaims a registry, but exact-string
  matching in §3.3 and §4 creates one by convention. A non-normative list of
  known names ("claude-code", "codex", …) would reduce typo-drift.
- **Secrets/machine-locals** — profiles are public-shaped git repos; whether
  the standard needs a convention for machine-local overlays (dotfiles
  managers solve this; we may just point at them).
- **Schema formalization** — a JSON Schema / Taplo schema for
  `chevaline.toml` once the field set stabilizes.
