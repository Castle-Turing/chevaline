# RFC 0001 — Workflow recipes as a third input

- **Status:** Draft
- **Raised:** 2026-08-16, external review
- **Affects:** vision.md (two-axis framing), SPEC §3.7 gates, §3.10 extensions

## Summary

Chevaline's two-axis model (project governance, resident preference) is
missing a third independent input: the **workflow recipe** — how a *kind of
work* proceeds, e.g. specify → implement → review → repair. A fourth input,
**runtime capabilities**, is a fact rather than a policy but constrains how
the others resolve. Chevaline should own resident preference, *select* a
workflow rather than define one, and treat capabilities as an input to
resolution.

## Problem

A workflow is portable independently of both who runs it and where it runs.
Two residents can share a TDD recipe while differing entirely in budget and
authority; one resident can switch recipes between a bugfix and a feature
while their preferences hold constant. That independence is the test for a
separate axis, and it is met.

The symptom is already visible in the spec: `[[gates]]` and
`[[extensions]]` are the two weakest sections, and both are weak for the
same reason — they are trying to be workflow without a workflow model. The
compass review made this concrete. compass's SDLC loop (review → auto-fix →
re-review, round-capped at three, then a human gate) reduces under
`[[extensions]]` to a path pointing at a script, losing every semantic that
made it worth describing.

`[[gates]]` has a second, related defect. Its event vocabulary
(`merge | commit | push | session-end`) mixes two planes: `merge` is a
repository/CI event while `session-end` is a local session event, and
per-tool-call events — where the most valuable behaviors actually bind —
are absent entirely.

## Proposal

Narrow Chevaline's stated identity from "agentic-development workflow
preferences" to **portable resident policy and preference**: how I want
agents to behave, what they may spend, when they must ask, and how my
preferences compose with a project's rules.

Add a selector, not a language (illustrative):

```toml
[workflow]
use = "…"          # a reference to a workflow package
```

Deliberately leave the package format unspecified. The seed document asked
for a way to *reference* executable content, not to define an orchestration
language, and there is not yet enough evidence about what a portable
workflow schema should contain.

Split `[[gates]]` along the same seam: "I always want a second-model review
before merging" is resident policy and stays; the mechanics of running that
review are workflow and leave.

## Consequences

- vision.md's two-axis framing becomes a four-input framing, with
  Chevaline owning one of them and composing against the others.
- `[[extensions]]` narrows to portable capabilities (see RFC 0007).
- The gate event vocabulary problem is inherited here rather than fixed
  independently, since what remains of `[[gates]]` determines which events
  still need naming.
- Runtime capabilities need somewhere to live in resolution — likely as
  input to the resolver rather than as a manifest section, since they
  describe the machine, not the resident.

## Open questions

- Does a workflow selector belong in the profile at all, or is choosing a
  workflow a per-task decision that no static config should pin?
- If a workflow declares roles (RFC 0004) and gates, what stops it from
  quietly becoming axis-1 governance for anyone who adopts it?
- Whose runtime capability surface is authoritative when two harnesses
  differ?

## How this gets decided

Two materially different workflows — the author's and another resident's,
which already differ substantially — executed against the same profile. If
both run without the profile changing, the seam is in the right place. If
either requires profile edits to accommodate its shape, the seam is wrong
and workflow is not as separable as claimed.
