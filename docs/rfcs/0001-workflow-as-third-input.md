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

## Reviewer questions

1. **Kill question.** "How this gets decided" sets its own falsification
   test: if either of the two workflows needs profile edits to run, the
   seam is wrong. Suppose that happens — workflow and resident preference
   turn out entangled rather than independent. Given that the proposal
   already narrows Chevaline's identity to "portable resident policy and
   preference" on the strength of this seam existing, what is left to
   build once the axis it just carved out turns out not to exist?
2. **Least certain.** The open questions ask what stops a workflow that
   declares roles and gates from quietly becoming axis-1 governance for
   anyone who adopts it. Is there an actual mechanism to prevent that, or
   does moving workflow out of the profile just relocate the
   governance-creep risk one layer down rather than remove it?
3. **Check this claim.** The workflow package format is left deliberately
   unspecified, on the premise that "there is not yet enough evidence
   about what a portable workflow schema should contain." Check whether an
   existing format — GitHub Actions workflows, Temporal, LangGraph, or
   n8n — already expresses compass's review → auto-fix → re-review loop
   (round-capped at three, then a human gate) well enough that
   `[workflow] use = "…"` should point at one of those rather than an
   undefined new package format.
4. **Right problem?** Even granting that workflow and preference are
   separable in principle, is *selecting* a workflow something a static
   profile should pin at all, or is it a per-task decision made fresh each
   time — in which case `[workflow] use = "…"` solves a problem no one
   actually has?

## Comments

*Append-only. Numbered C1, C2, … Never edit a prior comment; add a new one
or record a disposition. See [README](README.md) for why the fields are
what they are.*

### C1 — 2026-08-16 · unattributed model · saw the repo via a paste, and wrote partly from a Castle Turing vantage point

- **Asked for:** an assessment, with the requester noting in advance that
  they expected parts of it to be controversial.
- **Position:** development needs a third independent input, the workflow
  recipe ("how this kind of work proceeds"), plus runtime capabilities as
  a fourth; Chevaline should narrow to portable resident policy and select
  workflows rather than define them.
- **Verified:** the argument is structural, not a factual claim; the
  supporting observation that `[[gates]]`/`[[extensions]]` are the weakest
  sections is independently confirmed by Reviewer C's compass mapping.
- **Disposition:** pending
