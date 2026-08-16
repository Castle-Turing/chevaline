# RFC 0002 — Two-dimensional authority: decision × report

- **Status:** Draft
- **Raised:** 2026-08-16, external review; the missing `deny` was raised
  earlier by the compass review
- **Affects:** SPEC §3.9

## Summary

`silent | reported | approval` conflates two independent things: whether an
action may happen, and how conspicuously it is surfaced. Split them into a
`decision` axis (`allow | ask | deny`) and a `report` axis
(`silent | receipt | interrupt`).

## Problem

Read the current ladder carefully and it does not describe one scale:

- `silent` — allowed, no receipt.
- `reported` — allowed, with a receipt.
- `approval` — not allowed until approved.

The first two differ in *reporting* while agreeing on permission; the third
differs in *permission*. Consequences:

- **"Allowed, but interrupt me" is inexpressible.** So is "denied, and do
  not bother telling me."
- **There is no unconditional `deny`.** The ladder tops out at "ask," so a
  resident cannot say "never." compass denies reads of `.env`, `*.pem`, and
  `~/.ssh/**` outright; Chevaline cannot represent that at all.
- **The composition rule rests on a broken ordering.** SPEC §3.9 declares
  `silent < reported < approval` a total order and resolves cross-axis
  conflicts by taking the stricter value. "Stricter" is only meaningful on
  the permission axis; on the reporting axis it is not obvious that louder
  is stricter, and the current ordering silently assumes it.

## Proposal

Illustrative:

```toml
[authority.actions."vcs.push"]
decision = "ask"        # allow | ask | deny
report   = "receipt"    # silent | receipt | interrupt
```

With a scalar shorthand so the common case stays terse — `"vcs.push" =
"ask"` expanding to `decision = "ask"` with the default report level, so
that adding this dimension does not double the length of every profile.

Composition then has a clean meaning: project, resident, and platform
constraints combine to the **most restrictive decision** (`allow < ask <
deny`), while `report` is the resident's own call, since it governs their
attention rather than anyone's permission.

## Consequences

- Fixes the missing `deny` as a side effect rather than bolting a fourth
  rung onto a ladder with no room for it.
- Repairs the §3.9 strictness ordering, which is currently incomplete.
- Interacts with RFC 0007: Agent Skills' `allowed-tools` field uses
  `Bash(git:*) Read` syntax, which is the pattern-scoped form §3.9 also
  lacks. If both land, they should share one spelling.

## Open questions

- Is `report` genuinely resident-only? A project might reasonably require
  that certain actions be conspicuous in a shared log.
- Does `deny` need to distinguish "refuse" from "refuse and abort the
  session"?
- Should the default `report` level vary by `decision`, or be one value?

## How this gets decided

Rendering against two harnesses with materially different permission
models. Claude Code's `allow`/`deny`/`ask` lists map to the decision axis
cleanly but have no reporting concept; Codex's `approval_policy` is a
session-wide mode rather than a per-action grant. If both adapters can
render the decision axis and honestly report the reporting axis as
unsupported, the split is real. If one adapter finds itself inventing a
reporting concept the harness does not have, the axis may not be portable.
