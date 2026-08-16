# RFC 0008 — Effective configuration and `profile.modify`

- **Status:** Draft
- **Raised:** 2026-08-16, external review
- **Affects:** SPEC §2, §3.9, §4

## Summary

Name **effective configuration** as a first-class spec term — the result of
resolving declared preferences against environment, project governance, and
available runtime capabilities. Add a `profile.modify` authority class so
that a system proposing changes to a resident's own profile is itself
governed by that profile.

## Problem

The spec defines a resolution order (§2) and requires adapters to explain
it (§4), but never names the thing resolution produces. That makes it
awkward to say what a resolver outputs, what an adapter renders from, or
what an `explain` command is explaining.

Separately, a system that watches a resident work and proposes profile
changes — noticing they always approve worktree creation, say, and
suggesting the authority level relax — needs to know whether it may apply
that automatically. That is an authority question about the profile itself,
and the profile has no vocabulary for it.

## Proposal

**Term.** Three kinds of state, of which Chevaline owns two:

- **Declared** — what the manifest says. Authoritative.
- **Effective** — declared, resolved against environment, project
  governance, and runtime capabilities. What actually applies here, now.
- *Inferred* — private hypotheses learned from behavior. **Explicitly not
  Chevaline's.** A system may form them; the standard's job is only to be a
  good target for a proposed diff, which a declarative manifest already is.

**Authority class.** Add `profile.modify`, governing changes to the
resident's own profile. The natural posture is that cosmetic changes
(communication preferences) may eventually be self-adjusting while budget,
publishing authority, and permission changes stay approval-gated — which is
exactly the kind of distinction the existing action-class vocabulary
already expresses, applied recursively.

## Consequences

- Gives the resolver (`tools/chevaline.py`) a defined output contract
  rather than an ad-hoc one.
- Makes "automatic customization" legible: any change arrives as a diff
  against declared state, gated by declared authority, rather than as
  invisible behavioral drift.
- Interacts with RFC 0002: if authority splits into decision and report,
  `profile.modify` gets both, and "propose silently" versus "propose and
  interrupt" become expressible.

## Open questions

- Should `profile.modify` be scoped per-section (`profile.modify.budget`
  versus `profile.modify.instructions`), given the posture differs sharply
  between them?
- Does effective configuration need to be serializable and diffable as a
  stable artifact, or is it always transient?
- Who audits an applied self-modification, and where is it recorded?

## How this gets decided

The resolver produces effective configuration and explains it; that part is
settled by the artifact existing and being legible. `profile.modify` needs
a real proposal loop — a system that observes, proposes a diff, and is
correctly gated — before the class earns its place. Until then it is a
plausible field with no evidence behind it.
