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

### Reviewer questions

Every RFC carries a `## Reviewer questions` section. If a comment is
uninterpretable without knowing what was asked, then leaving the ask to
whoever happens to paste the file into a model is leaving the most
important variable to chance. The RFC supplies the framing.

The obvious hazard is that the author writes the questions, which is the
defendant writing the jury instructions. Guards, most of them borrowed from
the research on LLM reviewers rather than invented here (see
[`../standards.md`](../standards.md)):

- **Include a kill question.** At least one question whose answer could
  mean *abandon this*, not *revise this*. An RFC with no such question is
  soliciting improvements to a conclusion already reached.
- **Do not let the kill question merely restate `How this gets decided`.**
  The author wrote that test too, so a question anchored to it asks the
  reviewer to confirm the author's own account of what would be fatal —
  capture one level up. Observed on the first pass: six of eight kill
  questions opened by quoting the RFC's own falsification test. At least
  one question per RFC should attack a *premise* the RFC does not treat as
  in doubt.
- **Ask about what you are least sure of**, not what you are proudest of.
  The `Open questions` section is the natural source.
- **State the proposal in its weak form when asking.** Model reviewers are
  sensitive to assertion strength — confident phrasing measurably softens
  criticism — so a question that leads with how well-reasoned the proposal
  is will get agreement regardless of merit.
- **Name specific factual claims and ask for them to be checked against a
  source.** Unprompted, reviewers answer from memory, which is where this
  project's known errors have come from.
- **Ask whether this is the right problem at all.** Human and model
  reviewers weight differently: humans emphasise novelty and framing, model
  reviewers emphasise technical rigour and internal consistency. The
  "should this exist" dimension is the one that gets systematically
  under-served, so ask for it explicitly.
- **Do not ask what the RFC already answers.** That tests reading, not
  judgement.

**Distribute rather than pool.** Given that agreement between reviewers is
not evidence, asking five reviewers the same four questions buys less than
asking them different ones. Coverage is worth more than a robustness check
on a single answer, because the correlated-error failure makes the
robustness check unreliable anyway.

Reviewer questions target the *design and its claims*. They do not settle
the RFC — `How this gets decided` does that, with evidence. Review's job is
to save you from gathering evidence on a broken design, not to substitute
for the evidence.

### Generating a review packet

`tools/rfc-review.py` turns an RFC into a self-contained packet ready to
paste to a model reviewer: framing, what the reviewer is and is not
seeing, the RFC body, its assigned questions, and the comment template.

    python3 tools/rfc-review.py 0003

Comments are excluded by default (`--with-comments` restores them) because
prior comments anchor later reviewers into agreeing with them.
`--split N` divides the questions round-robin across N packets so
different reviewers see different questions, per "distribute rather than
pool" above.

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
