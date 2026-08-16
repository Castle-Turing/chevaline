# RFC 0007 — Extensions, Agent Skills, and the workflow boundary

- **Status:** Draft
- **Raised:** 2026-08-15 (Agent Skills discovery); corrected 2026-08-16
  after external review
- **Affects:** SPEC §3.10, §5

## Summary

`[[extensions]]` should reference [Agent Skills](https://agentskills.io/specification)
(`SKILL.md`) directories rather than invent an `id`/`run`/`description`
triple. But adopting skills does **not** dissolve the invocation-protocol
question, as an earlier version of this argument claimed — it dissolves it
for *capabilities* and leaves *workflows* unmodeled.

## Problem

Agent Skills is an open standard, published 2025-12-18, read by 32+
harnesses. It specifies a directory with a required `SKILL.md` (YAML
frontmatter `name`, `description`, plus optional `license`,
`compatibility`, `metadata`, `allowed-tools`) and optional `scripts/`,
`references/`, and `assets/`. `[[extensions]]` defines a parallel format for
the same purpose and, under Principle 5, cannot justify it.

What Agent Skills does *not* specify is where skills live or how a person
installs the ones they want everywhere — no user-level scope, no discovery
locations. That omission is Chevaline's niche, which makes the two
complementary rather than competing.

**The correction.** A skill is not a workflow language. It can package
"review a pull request" or "operate a git worktree." It cannot represent
roles, ordered or parallel steps, artifacts passed between steps, retry
limits, human gates, or success and escalation conditions. A workflow can
of course be *hidden inside* a skill's script — but then nothing can
inspect, explain, or customize it, and it becomes an opaque program wearing
a standard's packaging. compass's SDLC loop is exactly this shape: review →
auto-fix → re-review, round-capped at three, then a human gate.

## Proposal

Two moves, not one:

1. **`[[extensions]]` references skill directories** in `SKILL.md` format;
   adapters install them into each harness's skill location. This is the
   part Chevaline adds to Agent Skills.
2. **Workflow stays unmodeled and is admitted as such** (RFC 0001). A
   profile may *select* a workflow package without this spec defining that
   package's format.

If both land, `[[extensions]]` narrows to portable capabilities and stops
pretending to carry orchestration.

## Consequences

- §5's "extension invocation protocol" question is retired for
  capabilities and reopened, narrower, for workflows.
- Agent Skills' `allowed-tools` (`Bash(git:*) Read`) is prior art for the
  pattern-scoped authority syntax §3.9 lacks; RFC 0002 should match that
  spelling rather than invent a third.
- Profiles gain a question they did not have: bundle skill directories
  in-repo, reference them by path or URL, or both.

## Open questions

- Does a gate's `run` script (§3.7) also become a skill, or stay a plain
  entrypoint?
- Do referenced skills need pinning, and if so to what — a commit, a
  version in `metadata`?
- Installing a skill from a reference is a supply-chain action. Does that
  need its own authority class?

## How this gets decided

Install the same skill set through two adapters into two harnesses with
different skill directories. If both work from one declaration, the
reference model holds. Separately: attempt to express compass's SDLC loop
as a skill. The prediction is that it cannot be done without hiding the
loop in a script, and confirming that is what justifies leaving workflow
out.

## Reviewer questions

1. **Kill question.** "How this gets decided" predicts that expressing
   compass's SDLC loop as a skill cannot be done without hiding the loop
   in a script, and treats confirming that as what justifies leaving
   workflow unmodeled. If a skill actually can express a round-capped
   review → auto-fix → re-review loop with a human gate — via
   `allowed-tools` plus a script whose steps stay inspectable rather than
   opaque — does the workflow-boundary argument in this RFC and in RFC
   0001 collapse?
2. **Least certain.** The open questions flag that installing a skill
   from a reference is a supply-chain action and ask whether that needs
   its own authority class. Is referencing arbitrary skill directories in
   `[[extensions]]` meaningfully different, risk-wise, from any other
   dependency a project already pulls in — or does it need a distinct
   authority gate this RFC does not propose?
3. **Check this claim.** Re-read the Agent Skills specification at
   agentskills.io/specification directly — an earlier draft of this RFC
   already overstated what adopting SKILL.md would dissolve and had to be
   corrected per C2. Confirm there is genuinely no orchestration or
   control-flow affordance in `SKILL.md` — no sequencing, retry, or gate
   concept — that would undercut the claim that skills cannot represent
   workflow.
4. **Right problem?** Given Agent Skills is already read by 32+ harnesses
   on its own, should Chevaline reference skills in the spec at all, or is
   skill installation entirely a harness concern that a resident-policy
   standard should stay out of?

## Comments

*Append-only. Numbered C1, C2, … Never edit a prior comment; add a new one
or record a disposition. See [README](README.md) for why the fields are
what they are.*

### C1 — 2026-08-16 · DeepSeek Flash · read the full repo — SPEC.md, docs/vision.md, docs/standards.md, adapters/claude-code stub, examples/ada

- **Asked for:** an honest assessment of a one-day-old project, explicitly
  invited to push back.
- **Position:** `[[extensions]]` is a known-bad section whose fix is
  already identified; shipping v0.2 with a section the ledger itself
  convicts makes the spec stale on day one.
- **Verified:** confirmed that nothing depends on the draft — no git tags
  and no releases exist, so the change cost is zero.
- **Disposition:** pending

### C2 — 2026-08-16 · unattributed model · saw the repo via a paste, and wrote partly from a Castle Turing vantage point

- **Asked for:** an assessment, with the requester noting in advance that
  they expected parts of it to be controversial.
- **Position:** adopting SKILL.md is right for capabilities but a skill
  is not a workflow language — it cannot represent roles, ordered or
  parallel steps, artifacts between steps, retry limits, human gates, or
  escalation conditions.
- **Verified:** checked directly against the Agent Skills specification
  at agentskills.io/specification, which confirms both that it
  standardizes the package format and that it specifies no discovery
  locations or user-level scope. This corrected an earlier overstatement
  by Reviewer C that adopting SKILL.md would "dissolve" the
  invocation-protocol question.
- **Disposition:** pending

### C3 — 2026-08-16 · Claude Opus 5 · read this RFC, docs/rfcs/README.md, the repo README and CLAUDE.md — arriving from the Castle Turing repo, having just written a project skill there

- **Asked for:** not a review of this RFC. The resident had asked for a
  skill to be installed in Castle Turing, then pointed here saying the
  SKILL.md question was live, and asked whether the resulting observation
  was worth filing. So: one empirical datapoint offered against an
  existing argument, not an independent assessment of the proposal.
- **Position:** the capability/workflow split is missing a third
  category, and it is probably the common one. The skill I wrote
  (`implement-brief`, Castle Turing PR #25) is a workflow by this RFC's
  own criteria — ordered steps, artifacts passed between them (a
  decision log, commits, a PR), a human gate (`/code-review` before the
  PR), a retry loop, and escalation conditions. It contains **no
  script**. The whole thing is prose in the `SKILL.md` body, so none of
  the opacity this RFC warns about applies: every step is legible to
  anyone who opens the file.

  It is still not workflow, and the reason is worth naming precisely,
  because it is *not* the reason the RFC currently gives. Nothing can
  enforce the ordering, nothing can machine-read that a human gate
  exists, and the retry cap is literally the word "until." A model may
  skip any step silently and the packaging cannot tell. So the failure
  mode is not opacity — it is that **inspectable is not the same as
  structured**, and a prose workflow in a skill body looks governed
  while being entirely unenforced. I would argue that is more dangerous
  than the hidden-script case the RFC names, because the hidden script at
  least announces that something is being hidden.

  This strengthens the workflow-boundary argument rather than collapsing
  it, and it suggests reviewer question 1's framing may be too narrow:
  it asks whether a script *"whose steps stay inspectable rather than
  opaque"* would collapse the argument. Inspectability turns out not to
  be the load-bearing property.

  **Second, unrelated to workflow — on axis purity.** The same skill
  mixes both axes: project governance (a specific repo's read order,
  hard rules, CI commands, local conventions) and resident preference
  ("CI green is not always sufficient evidence — when a change generates
  an artifact, read the artifact"; keep a decision log; make the smallest
  reasonable call and log it rather than stalling). Only the second half
  is portable, and the mixture is why it can only live at project scope.
  If `[[extensions]]` references skill directories, a resident's profile
  may end up pointing at skills that are not axis-pure, and this RFC's
  "Open questions" does not currently ask what happens then. A useful
  tell, offered without confidence: the portable half was the part
  learned from experience, and the project-scoped half was the part a
  codebase imposed.

- **Verified:** the skill exists and was written before this comment, so
  the observation is from an attempt rather than from reasoning about
  one — Castle Turing PR #25, `.claude/skills/implement-brief/SKILL.md`.
  The workflow features listed above are checkable in that file.

  **Not verified, and this matters given C2:** I did **not** read
  agentskills.io/specification. Everything above about what `SKILL.md`
  can and cannot express is taken from this RFC's own characterisation,
  which C2 says it checked. So this comment cannot corroborate that
  check, and **reviewer question 3 remains open.** If the RFC's
  characterisation is wrong, this comment inherits the error.

  Also, per the README's rule that agreement between reviewers is not
  evidence: this comment reaches broadly the same conclusion as C2, and
  that convergence should be given no weight — same model family,
  overlapping training, and I read C2 before writing. The only part
  worth anything here is the built artifact, which C2 did not have.
- **Disposition:** pending
