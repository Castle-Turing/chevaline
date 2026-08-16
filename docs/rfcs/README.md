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

## Comments

Comments go in an append-only `## Comments` section at the bottom of the
RFC itself — plain text in the repo, not in a hosting service's comment
threads. Same reasoning as the rest of the project: a clone should contain
the whole argument, and nothing here should depend on a service being up or
an account existing. If an RFC's comments outgrow the proposal, move them
to a sibling `NNNN-comments.md` and link it.

Realistically most reviewers will be models. That is workable, but model
review fails differently from human review, and the record format exists to
compensate:

- **A comment is uninterpretable without knowing what was asked.** Models
  follow framing. "Find problems with this" and "does this look good?"
  produce different reviews of identical text, and only one of them is
  worth much. Record the ask.
- **Agreement between reviewers is not evidence.** Models trained on
  overlapping data make overlapping mistakes. Five reviews converging on
  the same point is one point, not five, and may be one shared blind spot.
  Never count votes.
- **Confident and wrong is the normal failure.** This project has already
  shipped two of them — a claim about Codex's profile names that turned out
  to be one project's local convention, and an unverified characterisation
  of another standard's merge model. Every comment records what was
  actually checked.
- **A review that finds nothing is data about the reviewer**, not about the
  RFC. Record those too, so a reviewer with a pattern of finding nothing is
  visible.

### Record format

```markdown
### C1 — 2026-08-16 · <reviewer> · <how it saw the repo>

- **Asked for:** what the reviewer was actually prompted to do
- **Position:** the substance, in a line or two
- **Verified:** which claims were checked and how; which remain unchecked
- **Disposition:** pending
```

`<reviewer>` should carry a model name and version where known, and say
`unattributed` where not — a comment from an unnamed model six months ago
cannot be weighed later. `<how it saw the repo>` matters: a reviewer given
a paste of one file is in a different position from one that read the tree
and ran the tests.

## The sweep

Comments accumulate; dispositions happen in batches. **Sweep at every minor
spec bump, and alongside the quarterly discovery pass in
[`../standards.md`](../standards.md)** — reusing a cadence the project
already keeps rather than inventing a second calendar.

Each open comment leaves the sweep with one disposition:

- **adopted** — the RFC text changed; say what changed.
- **rejected** — with the reason recorded. Rejections stay in the file.
- **deferred** — a real question that only an adapter or a workflow can
  settle. Given the evidence rule, **this should be the most common
  outcome**, and a sweep that adopts or rejects everything is a sweep that
  is guessing.
- **spawned** — it was a different proposal wearing a comment's clothing;
  name the new RFC.

A disposition is **exactly one** of those five words, immediately followed
by prose giving the reason. There is deliberately no "partially adopted"
value: a comment whose points were taken unevenly is recorded as `adopted`
with an explicit statement of what was *not* taken, so that the vocabulary
stays greppable and the exclusions stay visible. If a single comment
routinely needs several dispositions, it was really several comments and
should be split when it is recorded.

Solicit review at defined moments — when an RFC changes materially, or when
evidence arrives — rather than continuously. Model reviewers are cheap
enough that the binding constraint is sweep capacity, and an unswept
backlog is worse than no comments.

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
