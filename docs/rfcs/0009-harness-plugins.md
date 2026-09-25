# RFC 0009 — Harness plugins as a declared unit

- **Status:** Accepted — 2026-09-24, resident direction to implement;
  landed as SPEC §3.11 and §4.2 alongside this RFC. The implementation
  answers the store-location open question interimly (XDG data dir,
  `$XDG_DATA_HOME/chevaline/plugins/<id>/<pin>`); that and the other
  open questions below remain open pending the evidence run.
- **Raised:** 2026-09-23, from a resident trying to install one plugin
  (ponytail) across every harness they use
- **Affects:** SPEC §3.10, §4, §5; relates to RFC 0007

## Summary

Between RFC 0007's two categories — capabilities packaged as Agent
Skills, and workflows admitted as unmodeled — sits a third unit this
spec cannot express: the **harness plugin**. A plugin bundles skills
*plus lifecycle hooks plus per-harness packaging* in one repository,
and is installed through each harness's own mechanism (a marketplace,
a config entry, a hooks file). Propose a `[[plugins]]` section: a
pinned source, optional per-harness applicability, additive
composition, and an explicit authority binding for the install itself.
Adapters materialize one pinned checkout and render each harness's
native enablement from it.

## Problem

A resident wants ponytail — a rule-injection plugin published for a
dozen harnesses from one repo — active everywhere they work. The
manifest has nowhere to put that:

- `[[extensions]]` (§3.10) is an `id`/`run`/`description` triple for
  local scripts. It has no external source, no pin, and no notion of
  per-harness installation.
- RFC 0007's redesign points `[[extensions]]` at Agent Skills
  directories. A skill cannot carry what makes a plugin a plugin: hooks
  are *behavioral* — they fire on lifecycle events and re-inject rules
  every turn, unprompted — where a skill loads on demand. Ponytail's
  entire mechanism is its hooks; its skills are the accessories.

There is also a second failure the declaration must solve, discovered
empirically the same day: **"installed" is per-surface, not per-user.**
Installing a plugin interactively in Claude Code does not make it load
in SDK-driven sessions — the Agent SDK loads plugins only through an
explicit per-invocation option, not through setting sources — so a
launcher such as emcee dispatches sessions the resident believes are
governed by the plugin and are not. No sequence of manual installs
closes that gap, because the launcher needs to be *told* what to pass.
Only a declaration that both adapters and rendered launcher directives
read from can make "install X everywhere" mean everywhere.

## Proposal

Illustrative, not normative:

```toml
[[plugins]]
id = "ponytail"
source = "https://github.com/dietrichgebert/ponytail"
pin = "<commit sha>"                # a commit, required
harnesses = ["claude-code", "opencode"]   # optional; default: every
                                          # harness whose adapter runs
compose = "layer"                   # additive shape, §2.2: layer | defer | insist
```

Obligations, in the shape of §4:

1. **One checkout, pinned.** The adapter (or a shared tool the adapters
   call) materializes the source at the pin, once, in a declared
   location. The pin is the supply-chain control: a plugin executes
   code inside every session, so "track the default branch" is not an
   expressible option.
2. **Native enablement per harness.** Each adapter renders its
   harness's own mechanism against that checkout — for Claude Code, a
   plugin path or a settings enablement under the existing sidecar
   ownership; for opencode, a `plugin` entry in the global config. The
   checkout serving every harness is the point: no per-marketplace
   state to drift, one pin to audit.
3. **Launcher directives.** Where the profile already renders standing
   prose for budget and gates, a declared plugin adds one more
   directive: when launching a tool that dispatches sessions through an
   SDK, pass the plugin through that tool's plugin surface, because the
   harness-level install does not reach it.
4. **Authority.** Materializing or re-pinning a checkout is an
   `exec.install`-class action under §3.9 and composes as such. An
   adapter MUST NOT fetch or update plugin content more silently than
   the resident's authority for `exec.install` allows.
5. **Report the unexpressible.** A harness with no plugin surface, or a
   declared plugin with no packaging for a listed harness, is reported
   per §4 item 5, never silently skipped.

`compose` follows the additive row of §2.2 (`layer` default): a project
mandating its own plugins does not displace the resident's, a `defer`
plugin yields where the project has an opinion, and `insist` surfaces
the conflict.

## Consequences

- §3.10 narrows again. After RFC 0007 takes capabilities and this takes
  plugins, `[[extensions]]` holds only the resident's own local
  scripts — and the name starts to lie. If both land, the honest end
  state is likely `[[skills]]`, `[[plugins]]`, and `[[scripts]]`, with
  `[[extensions]]` retired; that renaming is proposed here only as a
  question, not as part of this RFC.
- §4 gains a new *kind* of obligation. Every current adapter duty is
  local rendering; item 1 above has an adapter fetching remote content
  onto the machine. That is a materially bigger trust footprint and is
  flagged as an open question rather than smuggled in.
- §4 item 6 ("never write outside the harness's own config locations")
  needs a named exception or a named location: a shared checkout store
  is not any harness's config location.
- RFC 0007 is unaffected in substance. Skills remain the right unit for
  capabilities; this RFC exists so that plugins do not get shoehorned
  into a skill-shaped hole. Its open supply-chain question ("does
  installing from a reference need its own authority class?") gets this
  RFC's answer: yes, and the class already exists — `exec.install`.

## Open questions

- **Where does the checkout live?** Vendored into the profile repo (a
  submodule — self-contained, but submodules are their own tax), or a
  cache location the spec names (XDG-style — cleaner, but now the spec
  defines a directory outside both profile and harness config, against
  §4 item 6). Neither is obviously right.
- **Update cadence.** A pin bump is a profile commit, which makes
  updates deliberate and auditable — and means a resident's plugins go
  stale by default. Is stale-by-default the correct posture, or does
  the section need an update-check obligation (report-only) on
  adapters?
- **Availability probing.** `harnesses` defaulting to "all" reads
  well, but a plugin repo only packages for the harnesses its author
  chose. Should the adapter detect packaging (the plugin's own
  manifest layout) and report a mismatch, or is a listed harness with
  no packaging simply the resident's error?
- **The name.** `[[plugins]]` next to `[[extensions]]` is two words
  for adjacent jobs in one document. If this RFC and RFC 0007 both
  land, the sections should be renamed together in one pass.

## How this gets decided

The standing falsification test, instantiated: one declaration of
ponytail in a test profile, installed through two adapters
(claude-code and an opencode adapter that does not exist yet) into two
harnesses, plus one SDK-launched context (an emcee dispatch, once
emcee's plugin passthrough exists — its backlog names this RFC)
receiving the plugin via a rendered launcher directive. The
observation: the plugin's hooks demonstrably fire in all three
contexts — Claude Code interactive, opencode, and the dispatched
session — from the single pinned checkout. If the third context cannot
be reached through rendered prose plus a launcher flag, obligation 3
is decoration and the RFC loses its second justifying failure.

## Reviewer questions

1. **Kill question.** Ponytail itself ships per-harness packaging for a
   dozen harnesses — the plugin *author* already solved cross-harness
   distribution, harness by harness. If plugin authors are the natural
   integration point and each harness has its own install command, is
   a resident-side `[[plugins]]` section anything more than a list of
   URLs next to a shell script? What residual value survives that
   framing — and if the answer is "only the pin and the launcher
   directive," should those live somewhere that already exists instead?
2. **Least sure.** Obligation 1 has adapters fetching remote content,
   which no current adapter duty does, and the checkout-store location
   contradicts §4 item 6 as written. Is there a design that keeps
   plugins declared in the profile but keeps all fetching outside the
   adapter contract — and if not, is the enlarged trust footprint
   acceptable for a config renderer?
3. **Check this claim.** This RFC asserts that the Claude Agent SDK
   loads plugins only through an explicit `plugins` option and that
   setting sources do not carry user-installed plugins into SDK
   sessions. Check that against the current Agent SDK documentation
   (code.claude.com/docs/en/agent-sdk/plugins.md and
   claude-code-features.md) rather than from memory, and say what the
   docs actually guarantee — the RFC's second justifying failure
   depends on it.
4. **Right problem?** The empirical gap that motivated this RFC — a
   launcher's SDK sessions not loading user-level plugins — could be
   read as purely a launcher defect (emcee needs a flag) plus a harness
   defect (SDKs could honor user-level plugin enablement). If both
   fixed their sides, would anything remain for Chevaline to declare
   beyond what RFC 0007 already covers?

## Comments

*Append-only. Numbered C1, C2, … Never edit a prior comment; add a new
one or record a disposition. See [README](README.md) for why the fields
are what they are.*
