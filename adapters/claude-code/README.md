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
| `[[gates]]`, `[sessions]`, `[[extensions]]` | No settled surface; reported as skipped |

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
- one line per declared `[[environment]]` whose budget differs, labeled
  with its selector — pulled from the raw manifest, not the resolved
  config, so environment matching never changes the rendered bytes;
- a standing directive to the reading session: when composing an
  invocation of any tool that accepts a spend cap (for example
  `emcee --budget`), pass the applicable amount, because an absent flag
  means that tool's own default silently wins;
- a plain statement that this is declared policy, not runtime
  enforcement — nothing in this harness halts a call at the threshold.

### Environments and a global render

`~/.claude` is global, but `path`/`git_org` selectors vary per project.
That is fine while matched environments only override sections whose
render does not depend on resolution. If a matched environment
contributes to a resolution-dependent surface (instructions, authority,
models), the report flags it as a context-dependent render so the
resident knows project-specific values leaked into global config. The
budget section is immune by construction: it renders from the raw
manifest — base limits plus every *declared* environment override,
labeled with its selector — so its bytes are identical whatever context
the render runs in.
