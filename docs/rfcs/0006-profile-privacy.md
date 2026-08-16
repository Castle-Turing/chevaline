# RFC 0006 — Profiles are private by default

- **Status:** Draft
- **Raised:** 2026-08-16, external review
- **Affects:** SPEC §3.2, vision.md, README

## Summary

The spec currently describes a profile repo as "public by convention," by
analogy with dotfiles. Invert that: the **standard** and its **fictional
examples** are public; **actual profiles** are private by default, with
machine-local and secret material kept outside version control entirely.

## Problem

A profile accumulates employer names, directory paths, hostnames, git
organizations, spending ceilings, model providers, authority decisions, and
behavioral preferences. That is personal operational data, and the dotfiles
analogy imported a publication norm along with the distribution model
without anyone deciding it should.

The stronger argument is not privacy but exposure. A published profile
states which paths an agent may write without asking, which actions never
surface to the resident, and where the spending ceiling sits. That is a map
of the blast radius, published for the convenience of anyone who wants it.
`[authority]` is precisely the section that should not be public.

## Proposal

- Default posture: **private**. Say so in the README and vision, not only
  in a spec aside.
- Public: the standard, the schema, adapters, and clearly fictional
  examples such as `examples/ada/`.
- Secrets and machine-local values stay out of the repo regardless of its
  visibility — a private repo still syncs across machines and still lands
  in backups.

Nothing about distribution changes: private git repos clone, pull, and pin
identically.

## Consequences

- §3.2's rationale for the `env` selector currently rests on the repo being
  public. The selector survives on a better argument — credentials should
  not sit in a synced config file whether or not it is published — but the
  wording needs replacing.
- The "dotfiles convention" framing needs qualifying wherever it appears:
  Chevaline borrows the *distribution* model, not the publication norm.
- Any future profile registry or sharing mechanism inherits a default that
  is now explicitly the opposite of open.

## Open questions

- Should the standard define a redaction convention so a resident can
  publish a shareable subset of their profile?
- Does a team-shared profile (several residents, one employer) want a third
  posture between public and private?
- Should adapters warn when they detect a profile in a public repo?

## How this gets decided

This one does not need an adapter. It needs a review of a real profile —
the author's, once it exists — asking what an adversary would learn from
it. If the answer is "not much," the default can be reconsidered.

## Comments

*Append-only. Numbered C1, C2, … Never edit a prior comment; add a new one
or record a disposition. See [README](README.md) for why the fields are
what they are.*

### C1 — 2026-08-16 · unattributed model · saw the repo via a paste, and wrote partly from a Castle Turing vantage point

- **Asked for:** an assessment, with the requester noting in advance that
  they expected parts of it to be controversial.
- **Position:** a profile carries employer names, paths, hostnames,
  budgets, providers, and authority choices; the standard and fictional
  examples should be public but real profiles private by default.
- **Verified:** no external claim to check. Acted on ahead of the sweep —
  the author's own profile repo was created private on 2026-08-16 on
  this basis.
- **Disposition:** adopted — the privacy posture was applied to
  `whharris/chevaline-whharris` immediately; the SPEC §3.2 wording change
  remains pending.
