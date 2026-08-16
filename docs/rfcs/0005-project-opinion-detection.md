# RFC 0005 — Project-opinion detection: four states

- **Status:** Draft
- **Raised:** 2026-08-16, external review
- **Affects:** SPEC §2.2, §5

## Summary

`layer`, `defer`, and `insist` have good semantics *once a conflict is
known*. Discovering whether a project has an opinion is the hard part, and
the spec currently treats "we could not tell" as "there is nothing there."
Require adapters to distinguish four states, and forbid the silent collapse
of unknown into absent.

## Problem

§2.2 defines `defer` as "apply only if the project has no opinion of its
own in this area." With unreliable detection, that degenerates into "apply
always" — a fail-open default.

This is an internal inconsistency, not merely a gap. §2.1 states that an
environment whose selector an adapter does not recognize must **not** match,
because silently ignoring a selector would make an environment apply in
situations the resident excluded. That is exactly the reasoning that §2.2
fails to apply to project detection, two sections earlier in the same
document.

The underlying difficulty is real: a prose `AGENTS.md` or `CLAUDE.md`
cannot be reliably merged with TOML, and there is no machine-readable
project governance format to read instead.

## Proposal

Adapters must resolve project opinion into one of four states, and report
which:

1. **No project policy found** — searched, found nothing.
2. **Compatible policy found** — found, and it agrees.
3. **Conflict found** — found, and it disagrees.
4. **Policy exists but cannot be interpreted** — found something on the
   subject and could not parse an opinion from it.

State 4 must never be reported as state 1. Its handling should follow
`compose`: under `defer`, an uninterpretable policy means the resident
preference does *not* silently apply; under `insist`, it surfaces.

## Consequences

- Removes the fail-open path from `defer`, at the cost of making `defer`
  more conservative in practice — which is the correct direction.
- Gives the resolver's `explain` output a concrete thing to say about
  composition rather than only about environments.
- Reduces §5's "project-opinion detection" from an open question to a
  detection-mechanism question.

## Open questions

- Which files count as looking for an opinion? `AGENTS.md`, per-harness
  project config, `.editorconfig`, CI configuration?
- Is a heuristic reading of prose ever acceptable, or does anything short
  of machine-readable governance land in state 4 by definition?
- Should Chevaline propose a machine-readable axis-1 format, or is that
  someone else's standard to write?

## How this gets decided

Run the resolver against a set of real repositories with varied
governance — one with a strict `AGENTS.md`, one with none, one with prose
that gestures at a policy without stating it. Count how often state 4 is
reached. If it is the common case, `defer` is not viable as specified and
needs a different default.
