# RFC 0003 — Budget enforcement capability and aggregation

- **Status:** Draft
- **Raised:** 2026-08-16, external review
- **Affects:** SPEC §3.5, §4.1

## Summary

`[budget]` currently states a policy and assumes an adapter can enforce it.
Separate four things that the spec runs together — declared policy,
enforcement capability, current enforcement status, and the usage ledger
enforcement reads from — and let a profile *require* enforcement rather
than merely hoping for it.

## Problem

**The aggregation hole is a correctness bug, not a gap.** §3.5 defines
`window = "day"` without saying whose day, measured across what. If a
Claude Code adapter and a Codex adapter each independently enforce a
$10/day cap, the resident has a $20/day cap. This means the mandatory
`scope = "*"` limit — described in §3.5 as "what guarantees nothing ever
runs uncapped" — does not guarantee that. True aggregate enforcement needs
a shared meter that no single-harness adapter can provide, so the field as
specified is unimplementable by exactly the adapters it was written for.

**Enforcement is assumed rather than declared.** §4.1 says an adapter that
cannot enforce a limit must report loudly, which puts the fail-safe in the
adapter's hands and gives the resident no way to say "then do not run."

**Rendering is not enforcement.** No harness config expresses "halt before
the next model call." A config-file adapter may neither intercept every
model call nor see authoritative usage before the next one. The mandatory
`tokens` support in §4.1 was justified by "providers report usage," which
is true of the provider and not necessarily true of the adapter's vantage
point.

## Found in practice (2026-08-16)

The first real profile resolved through `tools/chevaline.py` exhibited a
second, related fail-open — one the spec guards against in half of its
occurrences and misses in the other half.

The base declared three limits: an aggregate per session, an aggregate per
day, and a tighter per-day cap on the `deep` tier. An environment raised
the two aggregates. Because arrays replace wholesale (§2.1), the resolved
budget contained *only* the environment's two limits: **the per-tier cap
disappeared.** The environment was written to raise a ceiling and silently
removed a constraint.

§2.1 anticipates exactly this for the aggregate — "an environment that
overrides `limits` must restate its own aggregate" — and §3.5 makes that
case a validation error. Neither says anything about sub-limits, and no
rule catches their loss, so the spec guards the fail-open case its authors
thought of and misses the structurally identical one they did not.

This strengthens the case that budget needs richer structure than a flat
replaceable array, and it is independent of the aggregation hole above.

Candidate mitigations: warn when the resolved limit set drops a `scope`
present in the base; give limits stable identity so they can be merged
rather than replaced; or split aggregate limits from scoped limits so the
two compose differently.

## Proposal

Illustrative:

```toml
[budget]
enforcement = "required"     # required | best-effort
aggregate_across = "all"     # all | per-harness
```

`enforcement = "required"` means a runtime that cannot enforce the declared
limits must refuse to run rather than proceed unenforced.
`aggregate_across` makes the scope of a window explicit instead of implied,
and `per-harness` at least stops the spec from claiming an aggregation it
cannot deliver.

Separate, in the adapter contract, the four concerns: the **declared
policy** (manifest), the **enforcement capability** (what this runtime can
do), the **current status** (what is actually in force right now), and the
**usage ledger** (the shared meter, where one exists). A resolver should be
able to report status without pretending it is policy.

## Consequences

- §4.1's mandatory-`tokens` rule needs restating: mandatory *to represent*,
  conditional *to enforce*.
- Cross-harness aggregation implies a shared ledger, which is a runtime
  component and not a rendering — the renderer-vs-mechanism problem in
  §5 becomes concrete here first.
- A profile with `enforcement = "required"` and no capable runtime is a
  refusal-to-start, which every adapter must handle.

## Open questions

- Where does a shared ledger live, and does the standard specify its format
  or merely require one?
- Is `per-harness` aggregation honest enough to offer, or does offering it
  invite exactly the false confidence this RFC exists to remove?
- Does a `day` window need a timezone, and whose?

## How this gets decided

Two adapters running concurrently against one profile with a daily cap.
Measure actual combined spend against the declared limit. If it exceeds
the cap, `aggregate_across` is required rather than optional, and the
shared ledger stops being a design question and becomes a dependency.

## Reviewer questions

1. **Kill question.** If true cross-harness aggregation requires a shared
   meter that no config-file adapter can provide without a running service,
   is a portable budget *standard* viable at all — or should Chevaline
   declare budget policy and explicitly disclaim enforcement?
2. **Least certain.** Is `per-harness` aggregation honest enough to offer,
   or does naming it manufacture exactly the false confidence this RFC
   exists to remove?
3. **Check this claim.** This RFC asserts that no harness config file can
   express "halt before the next model call." Check that against current
   Claude Code settings and Codex configuration documentation — is there a
   native mechanism we have missed?
4. **Right problem?** Providers already offer account-level spend caps and
   dashboards. Is a profile-level budget filling a real gap, or duplicating
   something the providers own and do better?

## Comments

*Append-only. Numbered C1, C2, … Never edit a prior comment; add a new one
or record a disposition. See [README](README.md) for why the fields are
what they are.*

### C1 — 2026-08-16 · unattributed model · saw the repo via a paste, and wrote partly from a Castle Turing vantage point

- **Asked for:** an assessment, with the requester noting in advance that
  they expected parts of it to be controversial.
- **Position:** budget cannot generally be rendered; separate declared
  policy, enforcement capability, current status, and shared usage
  ledger, and let a profile require enforcement. The cross-harness
  aggregation point (two adapters each enforcing $10/day yields $20/day)
  is the sharpest part.
- **Verified:** the aggregation hole was confirmed by inspection of SPEC
  §3.5, which never says across what a window aggregates. A structurally
  similar fail-open was independently found by `tools/chevaline.py` on
  2026-08-16 and is recorded in the body of this RFC.
- **Disposition:** pending
