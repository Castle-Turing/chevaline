# claude-code adapter

The reference adapter for Claude Code. Given a Chevaline profile, it
renders the resolved (effective) configuration into Claude Code's
user-level config, per the adapter contract in SPEC.md §4.

```
python3 adapters/claude-code/adapter.py render <profile-dir> [--dry-run]
```

Run `--dry-run` first: it prints the full render report — what will be
written, what yields to hand-written config, what is skipped, and what is
**not enforced** — without touching anything. The same flags as
`tools/chevaline.py resolve` control the environment-resolution context
(`--cwd`, `--hostname`, `--git-org`, `--environment`).

## Targets and ownership

| File | Mechanism |
|---|---|
| `~/.claude/CLAUDE.md` | Marker-comment-delimited region; text outside the markers is never touched. A damaged marker pair aborts the render rather than guessing. |
| `~/.claude/settings.json` | JSON has no comments to hold a marker, so ownership lives in a **sidecar manifest** (SPEC §4 item 3). |
| `~/.claude/settings.chevaline.json` | The sidecar: the scalar keys and the individual list entries the adapter wrote. On re-render it removes what it owned, writes what the profile now wants, and re-records ownership. |

Non-clobbering consequences, all tested in `test_adapter.py`:

- A scalar the resident set by hand (e.g. an existing `model`) is never
  overwritten — the conflict is reported and the hand-written value wins.
- A permission entry the resident added by hand survives re-renders.
- Removing a field from the profile un-renders exactly what the adapter
  owned for it, nothing else.
- Running twice with an unchanged profile is byte-identical.

## Mapping

| Manifest section | Claude Code surface |
|---|---|
| `[[instructions]]` | `CLAUDE.md` region (harness-filtered, concatenated in order) |
| `[authority]` | `settings.json` `permissions` + `CLAUDE.md` prose (see below) |
| `[models]` | `standard` tier → `settings.json` `model`; other tiers reported as unexpressed |
| `[harnesses]` | Decides whether this adapter runs at all (`prefer` without `claude-code` → decline) |
| `[[environment]]` | Resolved before rendering, never rendered; the report names what matched and why |
| `[budget]` | `CLAUDE.md` prose: declared limits plus a standing launcher directive — **still reported as NOT ENFORCED** (see below) |
| `[[gates]]` | `CLAUDE.md` prose for gates carrying a `run` script: the declaration plus a standing directive conditioned on the gate's `compose` mode, with the path resolved against the profile root — **still reported as skipped**, because nothing fires it (see below). A gate without `run` renders nothing and is reported unsatisfied |
| `[sessions]`, `[[extensions]]` | No settled surface; reported as skipped |

### Authority

Chevaline's levels fold two dimensions together (RFC 0002): whether to
ask, and whether to tell. Claude Code permission rules express only the
first, so the adapter splits them:

- `silent` → `permissions.allow` rule
- `reported` → `permissions.allow` rule, **plus** a standing instruction in
  the `CLAUDE.md` region ("do it, then say you did") — the telling half has
  no settings surface
- `approval` → `permissions.ask` rule
- `default` → not expressible; Claude Code's own prompting stands in, which
  is at least as strict, as §3.9's implicit `restrict` composition permits.
  Reported as unexpressed either way.

The action-class → rule table (`ACTION_RULES` in `adapter.py`) is
best-effort and heuristic: Bash rules match by command prefix, which is
advisory rather than a security boundary, and no fixed list covers every
package manager. The render report repeats this caveat on every run rather
than presenting the mapping as exhaustive.

### Budget

This is a **non-enforcing adapter** in the sense of SPEC §4.1. It renders
configuration; it has no runtime hook that can stop a model call when a
limit is exhausted, and no Claude Code setting expresses one. Every render
that includes a `[budget]` therefore reports it as NOT ENFORCED,
prominently. The intended future mechanism is a `PreToolUse` hook reading
provider-reported usage; until that exists this adapter will keep saying
the cap does not bind here.

Not enforcing is not the same as not stating, though: a session reading
the rendered `CLAUDE.md` is often the *launcher* of other metered
workloads, and composes their invocations — including spend caps those
runtimes really do enforce (RFC 0003 comment C2 records the incident where
policy left only in the render report cost real money). So `[budget]`
renders into the `CLAUDE.md` region as prose, on the same surface the
`reported` authority level already uses:

- the declared base limits — each one's scope, window, amount, and unit,
  plus `on_exceed`, rendered literally (a profile change means a
  re-render, like every other section);
- one line per declared `[[environment]]` carrying a budget, labeled with
  when it applies — pulled from the raw manifest, not the resolved config,
  so environment matching never changes the rendered bytes. Each line
  states **only the fields that environment declares**, and the section
  states the composition rule rather than pre-composing: environments
  compose in declaration order (SPEC §2.1), so where several apply, the
  values in force are the last declared value of each field, not any
  single line as written.

  Neither merging each line onto the base nor accumulating them works
  here. Accumulating renders a cumulative prefix, correct only if every
  earlier environment also matched, and costs the context-independence
  the section is built for. Merging onto the base erases per-field
  provenance: after an earlier environment raises the limit, an
  environment declaring `on_exceed` alone composes to the raised limit
  while one declaring `on_exceed` *and* the base limits composes to the
  base — different caps, identical text under a base merge. Stating what
  each environment declares, field by field, is what makes the
  composition rule performable by the reader;
- **when** each environment applies, including explicit activation on
  every line. `--environment NAME` bypasses `when` entirely (SPEC §3.2),
  so a line naming only the selector would tell a session that activated
  the environment by name to use the base cap. Multiple predicates are
  joined with "and", never a comma list: every predicate in a `when` block
  must hold, and a comma reads as alternatives. A selector the resolver
  does not know renders as never matching automatically, since the
  resolver fails such an environment closed (SPEC §2.1) and prose reading
  like a live condition would be the one place in the pipeline treating it
  as usable;
- a standing directive to the reading session: when composing an
  invocation of any tool that accepts a spend cap (for example
  `emcee --budget`), work out which environments apply, compose them in
  the declared order, and pass the result — because an absent flag means
  that tool's own default silently wins;
- a plain statement that this is declared policy, not runtime
  enforcement — nothing in this harness halts a call at the threshold.

### Gates

Same statement-vs-enforcement split as budget, one section over. Claude
Code's user-level settings expose no hook surface that fires on a gate's
`on` event (`merge`, `push`, and so on), so this adapter cannot make a
gate *run* — but the session reading the rendered `CLAUDE.md` is very
often what drives the workflow the gate binds to: it opens PRs, launches
harnesses that open PRs (some of which expose exactly the hook surface
this harness lacks), and prepares everything a human later merges. A gate
that exists only in a render-time report is invisible to every such
session, and that invisibility has already cost a merge its review
(task 0002 records the incident).

So every `[[gates]]` entry that carries a `run` script renders into the
`CLAUDE.md` region as standing prose:

- the gate's `id`, `on` event, and `description`;
- the `run` script as a path resolved against the profile root — the
  manifest-relative form is useless to a reader outside the profile;
- a standing directive: before performing the `on` action — or setting in
  motion work that ends in it, such as opening a PR or launching a
  harness that opens PRs — apply the gate and surface what it finds, and
  when a launched tool accepts a post-PR or review hook, pass the script
  there rather than running it by hand afterwards;
- **what the gate's `compose` mode directs, spelled out per mode** rather
  than glossed. Only `layer` means "run it unconditionally". A `defer`
  gate runs only where the project has no gate of its own on the same
  event; an `insist` gate runs, but a conflicting project convention
  stops the session to surface it rather than yielding or overriding
  (SPEC §2.2). One unconditional `Run` line for all three would direct a
  session to run a deferred gate the project should have displaced, and
  to run an insisted gate straight through the conflict it exists to
  catch. A `compose` value the adapter does not know — the validator
  rejects these, so it means the profile outran the adapter — renders as
  unevaluable with an instruction not to run the script on the strength
  of the section;
- a plain statement that this is declared policy, not runtime
  enforcement — no hook in this harness fires a gate automatically.

A gate with no `run` script renders nothing — there is nothing actionable
to state — and stays in the report as unsatisfied. Every gate, rendered
or not, stays in the report's skipped list: prose is a statement surface,
not native enforcement.

Unlike the budget section, gates render from the *resolved* config: an
environment overrides gates only by replacing the whole array (SPEC
§2.1), so there is no per-environment override idiom to render
declaratively. An environment that does contribute to the gates array
makes the render context-dependent, and the report flags it as such (see
below).

### Environments and a global render

`~/.claude` is global, but `path`/`git_org` selectors vary per project.
That is fine while matched environments only override sections whose
render does not depend on resolution. If a matched environment
contributes to a resolution-dependent surface (instructions, authority,
models, gates), the report flags it as a context-dependent render so the
resident knows project-specific values leaked into global config. The
budget section is immune by construction: it renders from the raw
manifest — base limits plus every *declared* environment override,
labeled with its selector — so its bytes are identical whatever context
the render runs in.
