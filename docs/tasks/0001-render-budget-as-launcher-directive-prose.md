Title: Render [budget] into the CLAUDE.md region as launcher-directive prose

The claude-code adapter currently renders nothing for `[budget]`. It
routes the section to the render report's NOT ENFORCED list
(`report_unrenderable`, `adapters/claude-code/adapter.py:440`) on the
reasoning that no Claude Code setting can halt a model call at a spend
threshold. The reasoning is true; the conclusion — render nothing —
conflates *enforcing* a policy with *stating* it. A session reading the
rendered `~/.claude/CLAUDE.md` is often the launcher of other metered
workloads and composes their invocations, including spend caps those
runtimes really do enforce. Policy that is only in a render-time report
is invisible to every such session.

This has already cost real money. The resident's profile declares a
25 USD per-task-run cap for their emcee environment; the rendered
CLAUDE.md contained no occurrence of "budget" at all; managing sessions
therefore launched sprints without `--budget`; emcee's internal 10 USD
default bound instead, and three tasks died at it (emcee run journals,
2026-09-02/03) — two later completed at 14–17 USD when given headroom.
Full record: RFC 0003 comment C2
(`docs/rfcs/0003-budget-enforcement-model.md`).

## The change

Teach `render_region` (`adapter.py:185`) to emit a budget section into
the marker-delimited CLAUDE.md region whenever the profile declares
`[budget]`. Model it on the existing authority prose (the "Standing
authority expectations" section built around `adapter.py:217`), which is
the precedent: the `reported` level's telling-half has no settings
surface either, so the adapter renders standing prose for it.

Settled decisions — deviations are fine but report them (see below):

1. The section states the resolved base budget: each limit's scope,
   window, amount, and unit, plus `on_exceed`. Amounts are rendered
   literally; a profile change means a re-render, same as every other
   section.
2. The section carries a standing directive to the reader as launcher,
   to the effect of: when composing an invocation of any tool or harness
   that accepts a spend cap (for example `emcee --budget`), pass the
   applicable amount from this section; absence of the flag means the
   tool's own default silently wins.
3. The section states plainly that this is declared policy, not runtime
   enforcement — nothing in this harness halts a call at the threshold.
   Honesty stays; invisibility goes.
4. Environment overrides: `resolve_profile` strips environments out of
   `effective`, and a global render must stay context-independent
   (byte-identical regardless of cwd — see the adapter README's
   "Environments and a global render"). So render, after the base
   budget, one line per *declared* `[[environment]]` whose budget
   differs, with its selector, e.g. "under ~/projects/emcee*: 25 USD
   per session (task run)". Pull these from the raw manifest, not from
   the resolved config, precisely so matching does not affect output.
5. `report_unrenderable` keeps reporting budget, reworded: stated as
   prose in CLAUDE.md, still not runtime-enforced on this harness.
6. Update `adapters/claude-code/README.md`: the mapping table's
   `[budget]` row and the "### Budget" section both currently promise
   "no surface"; make them describe the prose surface and its limits.

## Tests

Extend `adapters/claude-code/test_adapter.py` in its existing style:

- a profile with `[budget]` renders the section, including a declared
  environment override, and the render is identical whatever `--cwd`;
- re-rendering an unchanged profile is byte-identical (existing
  invariant must keep holding with the new section);
- removing `[budget]` from the profile un-renders exactly that section;
- the render report still lists budget under NOT ENFORCED with the
  reworded text.

## Sources of truth, in order

- `adapters/claude-code/adapter.py` — the code being changed; read
  `render_region`, `report_unrenderable`, and how the authority prose
  is assembled before writing anything.
- `adapters/claude-code/README.md` — the adapter contract as documented;
  it must end up agreeing with the code.
- `SPEC.md` §3.5 and §4.1 — what a non-enforcing adapter owes the
  resident.
- `docs/rfcs/0003-budget-enforcement-model.md`, comment C2 — why this
  change exists and the incident evidence.

## Out of scope

- An emcee adapter (delegated enforcement via `--budget`) — separate
  work, do not start it here.
- Any SPEC.md or RFC 0003 change. This task needs nothing from that RFC
  to land; it only supplies evidence for it.

## Report your judgment calls

Where these instructions were ambiguous or you deviated, say so
explicitly in the PR description — those reports have repeatedly
surfaced real defects.
