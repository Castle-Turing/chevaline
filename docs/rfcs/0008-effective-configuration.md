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

## Note: this RFC probably wants splitting

Writing the reviewer questions exposed a structural problem. The kill
question and the right-problem question collapse into the same challenge,
because this RFC bundles two proposals of very different maturity:

- **Naming effective configuration** is close to settled — the resolver
  already produces the artifact, so the term describes something that
  exists.
- **`profile.modify`** is admittedly speculative, governing a category of
  system that nothing currently implements.

They need different evidence and will disposition independently, which by
the project's own rule — several dispositions means it was several items —
means they should be separate RFCs. Left bundled for now because splitting
churns numbering, links, and an existing comment record; worth doing before
either half moves out of Draft.

## Reviewer questions

1. **Kill question.** "How this gets decided" concedes that
   `profile.modify` needs a real proposal loop — a system that observes,
   proposes a diff, and is correctly gated — before the class earns its
   place, and that until then it is "a plausible field with no evidence
   behind it." If no such system ever materializes, should
   `profile.modify` be dropped from the spec rather than carried as an
   authority class governing a capability nothing exercises?
2. **Least certain.** The open questions ask whether effective
   configuration needs to be serializable and diffable as a stable
   artifact, or is always transient. If it is always transient, does
   naming it as a first-class spec term change anything an adapter
   actually does, or is this a definition with no operational
   consequence?
3. **Check this claim.** Check whether comparable configuration-resolution
   systems — `kubectl` (merged/applied config), Terraform (plan/state), or
   chezmoi (target state) — already have an established name for exactly
   this resolved-output concept, and whether "effective configuration" is
   consistent with that prior art or reinvents a term other systems
   already settled.
4. **Right problem?** RFC 0008 itself admits nothing today proposes
   automatic diffs against a resident's profile. Is `profile.modify`
   closing a real gap, or is it governance designed in advance for a
   category of system that may never exist, at the cost of complexity
   every adapter now has to carry?

## Comments

*Append-only. Numbered C1, C2, … Never edit a prior comment; add a new one
or record a disposition. See [README](README.md) for why the fields are
what they are.*

### C1 — 2026-08-16 · unattributed model · saw the repo via a paste, and wrote partly from a Castle Turing vantage point

- **Asked for:** an assessment, with the requester noting in advance that
  they expected parts of it to be controversial.
- **Position:** distinguish declared, inferred, and effective
  configuration; whether a system may auto-apply a proposed profile
  change is itself an authority decision.
- **Verified:** analytic.
- **Disposition:** adopted — the declared/effective distinction and the
  `profile.modify` class were carried into this RFC. Not adopted: inferred
  preferences, judged out of scope for the standard, since a system may
  form them but the standard's only job is to be a good target for the
  diff they produce.
