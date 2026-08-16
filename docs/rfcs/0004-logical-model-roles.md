# RFC 0004 — Logical model roles, tiers as fallback

- **Status:** Draft
- **Raised:** 2026-08-16, external review
- **Affects:** SPEC §3.4

## Summary

`cheap | standard | deep` is a single cost/capability axis, and real work
selects models along several. Let a workflow declare **logical roles**
(`specifier`, `implementer`, `design-reviewer`, `correctness-reviewer`) and
let the resident bind those roles to harness/model combinations, with the
three generic tiers demoted to a mandatory fallback.

## Problem

The tier ladder assumes one ordering, and the assumption fails in ordinary
cases:

- The best specifier is not necessarily the most expensive model.
- The best implementer may be a specialized coding model that is not
  "deeper" in any general sense.
- A reviewer should ideally be *independent* from the implementer — a
  property of the pair, which a per-task tier cannot express at all.
- Latency, context length, and tool competence matter separately from
  reasoning depth.

## Proposal

An interface/implementation split. The workflow declares the roles it
needs; the profile binds them (illustrative):

```toml
[models.roles]
implementer          = { harness = "claude-code", tier = "standard" }
correctness-reviewer = { harness = "codex",       tier = "deep" }
```

Tiers remain and become the **mandatory** fallback: every role must degrade
to a tier so an adapter that has never heard of a role name still has
something to do. That is the price of an open role vocabulary.

This also lowers the stakes on RFC-adjacent tier naming. `cheap` is a cost
word doing duty on a capability axis and collides with budget vocabulary
(`scope = "cheap"` sits inside a list of money limits); `quick | standard |
thorough` is a single coherent axis. But once tiers are a fallback rather
than the primary abstraction, the rename matters less.

## Consequences

- §3.4's closed vocabulary becomes closed-for-tiers, open-for-roles.
- Depends on RFC 0001: roles are workflow vocabulary, so this only makes
  sense if workflows are a distinct input that declares them.
- Independence constraints ("these two roles must not resolve to the same
  model") are a genuinely new kind of field and are deliberately out of
  scope here.

## Open questions

- Who owns the role vocabulary — each workflow, or a shared registry?
- What happens when a workflow declares a role the profile has not bound
  and whose fallback tier is also unbound?
- Does a role bind to a harness, a model, or a whole configuration
  (reasoning effort, tools, context budget)?

## How this gets decided

Two workflows with materially different role sets, run against one
profile. If the profile's bindings and fallbacks cover both without
editing, roles are portable. If each workflow needs its own bespoke
bindings, roles are workflow-local configuration wearing a standard's
clothing.

## Comments

*Append-only. Numbered C1, C2, … Never edit a prior comment; add a new one
or record a disposition. See [README](README.md) for why the fields are
what they are.*

### C1 — 2026-08-16 · DeepSeek Flash · read the full repo — SPEC.md, docs/vision.md, docs/standards.md, adapters/claude-code stub, examples/ada

- **Asked for:** an honest assessment of a one-day-old project, explicitly
  invited to push back.
- **Position:** rename the tiers now rather than "before v1.0" — `cheap`
  is a cost word on a capability axis and collides with budget
  vocabulary; zero adapters exist so the cost of renaming is zero today.
- **Verified:** prompted a check of the spec's prior-art claim for the
  tier names, which turned out to be WRONG — the spec said Codex ships
  cheap/standard/deep profiles, but Codex supplies only the profile
  mechanism and compass authored those names. Corrected in commit
  b075dff.
- **Disposition:** pending

### C2 — 2026-08-16 · unattributed model · saw the repo via a paste, and wrote partly from a Castle Turing vantage point

- **Asked for:** an assessment, with the requester noting in advance that
  they expected parts of it to be controversial.
- **Position:** tiers are one-dimensional; workflows should name logical
  roles (specifier, implementer, design-reviewer, correctness-reviewer)
  and Chevaline should bind them, with tiers demoted to fallback.
- **Verified:** analytic; the independence-between-reviewer-and-implementer
  point is a pair constraint that the current schema provably cannot
  express.
- **Disposition:** pending
