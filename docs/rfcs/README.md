# Chevaline RFCs

Substantive changes to the spec go through an RFC before they go into
`SPEC.md`. This exists because of a failure mode the project has already
demonstrated twice: a good argument arrives, it is obviously right, and it
gets written straight into the spec — where it becomes normative before
anything has tried to implement it.

The spec is a set of claims about what adapters can do. An RFC is where a
claim lives while it is still a claim.

## Status values

- **Draft** — proposed, argued, not agreed.
- **Accepted** — agreed in principle; may or may not be in `SPEC.md` yet.
- **Implemented** — in `SPEC.md` *and* exercised by at least one adapter.
- **Rejected** — declined, with the reason kept.
- **Superseded** — replaced; names its replacement.

Note that **Accepted is not Implemented**. A proposal only earns
Implemented when something has actually run it, per the evidence rule
below.

## The evidence rule

Every RFC must state, in a "How this gets decided" section, what would
settle it. Vague answers ("we'll see how it feels") are not acceptable;
name the artifact and the observation.

The project's standing falsification test, from which most of these
inherit:

> A field earns its place when it survives **two materially different
> adapters and two materially different workflows.** Anything that only
> works for one harness, or only for its author's way of working, has not
> been shown to be portable — it has been shown to be a preference.

Until the resolver (`tools/chevaline.py`) and at least two adapters exist,
almost everything here stays Draft. That is the intended state, not a
backlog to burn down.

## Relationship to the standards ledger

[`../standards.md`](../standards.md) tracks *external* prior art and audits
the spec against it. RFCs track *internal* proposals. When a discovery pass
finds a standard that convicts a field, the ledger records the verdict and
an RFC carries the redesign.

## Index

| # | Title | Status |
|---|---|---|
| [0001](0001-workflow-as-third-input.md) | Workflow recipes as a third input | Draft |
| [0002](0002-two-dimensional-authority.md) | Two-dimensional authority: decision × report | Draft |
| [0003](0003-budget-enforcement-model.md) | Budget enforcement capability and aggregation | Draft |
| [0004](0004-logical-model-roles.md) | Logical model roles, tiers as fallback | Draft |
| [0005](0005-project-opinion-detection.md) | Project-opinion detection: four states | Draft |
| [0006](0006-profile-privacy.md) | Profiles are private by default | Draft |
| [0007](0007-extensions-and-skills.md) | Extensions, Agent Skills, and the workflow boundary | Draft |
| [0008](0008-effective-configuration.md) | Effective configuration and `profile.modify` | Draft |

Gaps that are not yet proposals — MCP server declarations, a subagent
roster, scheduling for unattended runs — remain in `SPEC.md` §5 until
someone has an actual design to argue for.
