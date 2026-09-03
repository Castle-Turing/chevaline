Title: Render [[gates]] into the CLAUDE.md region as standing prose
Requires: 0001-render-budget-as-launcher-directive-prose
Requires-Because: both restructure render_region and report_unrenderable in
adapters/claude-code/adapter.py, plus the README mapping table and the
adapter tests; stacking avoids a mechanical conflict, and this brief tells
the worker to match 0001's budget section shape, which only exists once
0001's branch does.

The claude-code adapter currently renders nothing for `[[gates]]`. It
routes the section to the render report's skipped list
(`report_unrenderable`, `adapters/claude-code/adapter.py:458`) on the
reasoning that Claude Code has no native hook surface for a gate's
lifecycle event in user-level settings. The reasoning is true; the
conclusion — render nothing — is the same statement-vs-enforcement
conflation task 0001 records for `[budget]`. The skip message itself
concedes the point: "the gate's own `run` script remains the mechanism,
invoked by whatever drives the workflow" — and the session reading the
rendered `~/.claude/CLAUDE.md` is very often what drives the workflow.
It opens PRs, launches harnesses that open PRs (some of which expose a
hook surface built for exactly this), and prepares everything a human
later merges. A gate that exists only in a render-time report is
invisible to every such session.

This has already cost a merge its review. The resident's profile
declares `gates.cross-vendor-review` (`on = "merge"`, a `run` script
that reviews a branch with a different vendor's model). The rendered
CLAUDE.md contained no occurrence of "gate" at all; a managing session
launched an overnight harness run without wiring the hook, hand-opened
a second PR without review, and the first PR merged un-gated
(Castle-Turing/dovetail PR #1, 2026-09-03) — the resident caught it by
asking where the review was. The retroactive review then found two
confirmed P2 defects on merged main, one violating the module's central
documented guarantee; a pre-merge gate would have surfaced both.
Dispositions and evidence are on dovetail PRs #1 and #2.

## The change

Teach the adapter to emit a gates section into the marker-delimited
CLAUDE.md region whenever the profile declares a `[[gates]]` entry that
carries a `run` script. The precedent is the authority prose (the
"Standing authority expectations" section), whose `reported` level
likewise renders standing prose for the half no settings surface can
express; task 0001 applies the same pattern to `[budget]`, and this
task completes the set.

Settled decisions — deviations are fine but report them (see below):

1. For each gate: its `id`, `on` event, `description`, and `compose`,
   plus a standing directive to the effect of: before performing the
   `on` action — or setting in motion work that ends in it, such as
   opening a PR or launching a harness that opens PRs — run the gate's
   `run` script and surface its findings; when launching a tool that
   accepts a post-PR or review hook, pass the script there rather than
   running it by hand afterwards.
2. The rendered directive must name a path the reader can actually
   execute. `run` is profile-relative in the manifest; resolve it
   against the profile root at render time, the same way the render
   already knows where it is reading from.
3. The section states plainly that this is declared policy, not runtime
   enforcement — no hook in this harness fires it automatically.
   Honesty stays; invisibility goes.
4. A gate with no `run` script keeps its current treatment (reported
   unsatisfied; nothing actionable to render).
5. `report_unrenderable` keeps reporting gates, reworded: stated as
   prose in CLAUDE.md, still not natively enforced on this harness.
6. Update `adapters/claude-code/README.md`: the mapping table row
   currently lumps `[[gates]]` with `[sessions]` and `[[extensions]]`
   under "no settled surface"; give gates its own row describing the
   prose surface and its limits. Sessions and extensions are untouched.

## Tests

Extend `adapters/claude-code/test_adapter.py` in its existing style:

- a profile with a `run`-carrying gate renders the section, with the
  resolved script path;
- a gate without `run` renders nothing and stays in the report as
  unsatisfied;
- re-rendering an unchanged profile is byte-identical;
- removing the gate un-renders exactly that section;
- the render report still lists the gate under skipped with the
  reworded text.

## Sources of truth, in order

- `adapters/claude-code/adapter.py` — read `render_region`,
  `report_unrenderable`, and the authority-prose assembly before
  writing anything. If task 0001 has landed, its budget section is the
  nearest sibling; match its shape.
- `docs/tasks/0001-render-budget-as-launcher-directive-prose.md` — the
  sibling brief and the argument this one leans on.
- `adapters/claude-code/README.md` — the adapter contract; it must end
  up agreeing with the code.
- `SPEC.md` §4.1 — what a non-enforcing adapter owes the resident.

## Out of scope

- Rendering `[sessions]` or `[[extensions]]` — same class of question,
  separate decisions, not decided here.
- Any `[[gates]]` schema change, and RFC 0001's open question of moving
  gate mechanics out of the profile — this task renders what the schema
  already says, nothing more.
- Harness-side hook wiring (that belongs to whatever launches the
  harness, guided by the rendered prose).

## Report your judgment calls

Where these instructions were ambiguous or you deviated, say so
explicitly in the PR description — those reports have repeatedly
surfaced real defects.
