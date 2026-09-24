#!/usr/bin/env python3
"""adapter.py — Chevaline reference adapter for Claude Code (SPEC.md §4).

    python3 adapter.py render <profile-dir> [--claude-dir DIR] [--dry-run]
                              [--cwd PATH] [--hostname NAME] [--git-org ORG]
                              [--environment NAME ...]

Renders a Chevaline profile into Claude Code's user-level config:

  ~/.claude/CLAUDE.md               instructions + reporting expectations,
                                    inside marker comments (SPEC §4 item 3)
  ~/.claude/settings.json           authority → permissions; models → model
  ~/.claude/settings.chevaline.json sidecar manifest recording exactly what
                                    this adapter owns in settings.json,
                                    because JSON has no comment syntax to
                                    hold a marker (SPEC §4 item 3)

Standard library only. Requires Python 3.11+ (tomllib, via tools/chevaline.py).

Ownership model for settings.json: the adapter owns only what it wrote.
Scalars it set are recorded by key path; list entries it appended are
recorded per entry. On re-render it removes what it owned, writes what the
profile now wants, and records the new ownership. A key or entry the
resident wrote by hand is never modified; if the profile wants a scalar the
resident already set by hand, the adapter reports the conflict and yields
(SPEC §4 item 3: re-rendering never clobbers hand-written config).

This is a NON-ENFORCING adapter in the sense of SPEC §4.1: it renders
configuration and cannot stop a model call at runtime. Budget limits are
therefore stated as standing prose in CLAUDE.md — the declared policy plus
a directive to pass the applicable cap to tools that do enforce one (task
0001, RFC 0003 C2) — and still reported as UNENFORCED, prominently, on
every render. Gates that carry a `run` script get the same treatment
(task 0002): their declaration plus a standing directive to run the
script before the gate's `on` action, still reported as not natively
enforced, because no user-level Claude Code hook surface fires on a
gate's lifecycle event.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))

import chevaline as ch  # noqa: E402
import plugstore  # noqa: E402

HARNESS_NAME = "claude-code"

# Marker lines for the owned region of CLAUDE.md (SPEC §4 item 3: rendered
# regions must be identifiable; markdown has comments, so markers work here).
BEGIN_MARKER = "<!-- chevaline:begin — rendered by the claude-code adapter; do not edit between markers, edits will be overwritten on re-render -->"
END_MARKER = "<!-- chevaline:end -->"

SIDECAR_NAME = "settings.chevaline.json"

# --------------------------------------------------------------------------
# Authority mapping (SPEC §3.9 → Claude Code `permissions`)
#
# Chevaline's levels have two dimensions folded together (RFC 0002): whether
# to ask, and whether to tell. Claude Code's permission rules express only
# the first. The adapter therefore splits them:
#
#   silent   → allow rule            (don't ask, nothing to say)
#   reported → allow rule + prose    (don't ask; the telling half has no
#                                     settings surface, so it renders as a
#                                     standing instruction in CLAUDE.md)
#   approval → ask rule
#
# The action-class → permission-rule table below is a best-effort, heuristic
# mapping. Claude Code matches Bash rules by command prefix, which is
# advisory, not a security boundary, and no fixed rule list covers every
# package manager or publish command. The render report says so every time
# rather than presenting the mapping as exhaustive (SPEC §4 item 5).
#
# `default` has no Claude Code surface: there is no "default level" knob
# with these semantics, so the harness's own prompting behavior stands in
# for it. That is always at least as strict as `reported`, which authority's
# implicit `restrict` composition permits (SPEC §3.9: stricter wins), but it
# is reported as unexpressed rather than silently blessed.
# --------------------------------------------------------------------------

ACTION_RULES: dict[str, list[str]] = {
    "fs.write": ["Edit", "Write"],
    "net.fetch": ["WebFetch", "WebSearch"],
    "vcs.commit": ["Bash(git add:*)", "Bash(git commit:*)"],
    "vcs.push": ["Bash(git push:*)"],
    "vcs.publish": [
        "Bash(gh pr create:*)",
        "Bash(gh release create:*)",
        "Bash(gh repo create:*)",
    ],
    "deps.change": [
        "Bash(npm install:*)",
        "Bash(pip install:*)",
        "Bash(uv add:*)",
        "Bash(cargo add:*)",
    ],
    "exec.install": [
        "Bash(pipx install:*)",
        "Bash(brew install:*)",
        "Bash(sudo apt install:*)",
        "Bash(sudo apt-get install:*)",
    ],
}

# One-line glosses used when rendering `reported` classes as prose.
ACTION_GLOSS: dict[str, str] = {
    "fs.write": "writing or editing files in the working tree",
    "net.fetch": "read-only network access",
    "vcs.commit": "creating a version-control commit",
    "vcs.push": "pushing to a remote",
    "vcs.publish": "anything outward-facing (PRs, releases)",
    "deps.change": "adding, removing, or upgrading a dependency",
    "exec.install": "installing tools onto the machine",
}

# What a gate's `compose` mode actually directs the reading session to do
# (SPEC §2.2: additive sections take layer/defer/insist, defaulting to
# layer). These are directives, not glosses: only `layer` means "run it
# unconditionally", so a single unconditional instruction would tell a
# session to run a deferred gate the project's own convention should have
# displaced, and to run an insisted gate straight through a conflict it is
# supposed to stop at. `{script}` is the resolved path, `{on}` the event.
COMPOSE_DIRECTIVE: dict[str, str] = {
    "layer": (
        "Run `{script}`. Compose `layer`: it runs in addition to any gate "
        "the project itself requires, so a project gate on `{on}` does not "
        "excuse skipping this one."
    ),
    "defer": (
        "Compose `defer`: run `{script}` only where the project has no gate "
        "of its own on `{on}`. Where the project does, its convention takes "
        "this gate's place and this one is not run."
    ),
    "insist": (
        "Compose `insist`: run `{script}`. If the project's own convention "
        "on `{on}` conflicts with it, do not quietly yield to the project "
        "and do not run over it — stop, surface the conflict, and wait."
    ),
}

# A gate whose `compose` is none of the above. The validator rejects these,
# so reaching this text means the profile outran the adapter (a mode from a
# newer spec version, say). Rendering an unconditional `Run` for a mode
# whose composition rule is unknown is the failure this table exists to
# avoid, so the fallback states the mode is unevaluable and stops.
COMPOSE_UNKNOWN = (
    "Compose `{compose}` is not a mode this adapter can evaluate for a gate "
    "(SPEC §2.2 allows `layer`, `defer`, and `insist` here). Do not run "
    "`{script}` on the strength of this section — treat the gate as "
    "unresolved and ask the resident."
)

# Which tier binds to settings.json's single `model` key. Claude Code's
# global config carries exactly one default model, and the resident's
# day-to-day default is the standard tier; cheap and deep have no global
# surface (per-subagent pinning is the closest fit) and are reported as
# unexpressed (SPEC §3.4: adapters MUST report tiers they cannot map).
MODEL_TIER_FOR_SETTINGS = "standard"


class Report:
    """Accumulates the render report (SPEC §4 items 2 and 5)."""

    def __init__(self) -> None:
        self.environments: list[dict] = []
        self.rendered: list[str] = []
        self.skipped: list[str] = []
        self.conflicts: list[str] = []
        self.unenforced: list[str] = []
        self.notes: list[str] = []

    def print(self, file=None) -> None:
        out = file or sys.stdout
        print("Chevaline → Claude Code render report", file=out)
        print("=====================================", file=out)
        print("Environments considered (declaration order):", file=out)
        if not self.environments:
            print("  (none declared)", file=out)
        for rep in self.environments:
            status = "MATCHED" if rep["matched"] else "did not match"
            print(f"  {rep['name']}: {status} — {rep['reason']}", file=out)
        if self.rendered:
            print("Rendered:", file=out)
            for line in self.rendered:
                print(f"  {line}", file=out)
        if self.conflicts:
            print("Yielded to hand-written config (left untouched):", file=out)
            for line in self.conflicts:
                print(f"  {line}", file=out)
        if self.skipped:
            print("Skipped — no native Claude Code surface (SPEC §4 item 5):", file=out)
            for line in self.skipped:
                print(f"  {line}", file=out)
        if self.unenforced:
            print("NOT ENFORCED (SPEC §4.1 — read this part):", file=out)
            for line in self.unenforced:
                print(f"  !! {line}", file=out)
        if self.notes:
            print("Notes:", file=out)
            for line in self.notes:
                print(f"  {line}", file=out)


# --------------------------------------------------------------------------
# CLAUDE.md rendering
# --------------------------------------------------------------------------


def applicable_instructions(effective: dict) -> list[dict]:
    """Instruction blocks that apply to this harness (SPEC §3.6): those with
    no `harnesses` filter, or a filter naming claude-code."""
    out = []
    for entry in effective.get("instructions", []) or []:
        if not isinstance(entry, dict):
            continue
        harnesses = entry.get("harnesses")
        if harnesses is None or HARNESS_NAME in harnesses:
            out.append(entry)
    return out


def describe_limit(entry: Any) -> str:
    """One budget limit as prose: amount, unit, window, scope."""
    if not isinstance(entry, dict):
        return repr(entry)
    scope = entry.get("scope")
    scope_txt = "aggregate over all spend" if scope == "*" else f"scope `{scope}`"
    return f"{entry.get('amount')} {entry.get('unit')} per {entry.get('window')}, {scope_txt}"


def describe_selector(when: Any) -> str:
    """When an environment applies, as one phrase for the budget override
    lines.

    Explicit activation is named on *every* line, not only for `when`-less
    environments: `--environment NAME` bypasses `when` entirely (SPEC §3.2),
    so a selector that does not hold is not evidence the override is
    inapplicable, and a session that activated the environment by name would
    otherwise read the base cap as the one in force.

    A selector the resolver does not know renders as never matching, not as
    a usable predicate. The resolver fails such an environment closed
    (SPEC §2.1, `ch.KNOWN_SELECTORS`), so prose that reads like an ordinary
    condition would be the one place in the pipeline treating it as live.

    Predicates are joined with "and", never a bare comma: every predicate in
    a `when` block must hold (SPEC §3.2, `ch.evaluate_when`), and a comma
    list reads as alternatives. Explicit activation is the one genuine
    alternative, so it is the outer "or".
    """
    if not isinstance(when, dict) or not when:
        return "applies only when explicitly activated by name"
    phrases = []
    unsupported = []
    for key, val in when.items():
        if key == "path":
            phrases.append(f"under `{val}`")
        elif key == "hostname":
            phrases.append(f"on host `{val}`")
        elif key == "git_org":
            phrases.append(f"in git org `{val}`")
        elif key == "env":
            phrases.append(f"when `{val}` is in the process environment")
        elif key in ch.KNOWN_SELECTORS:
            # Known to the resolver, no bespoke phrasing here yet.
            phrases.append(f"when `{key}` matches `{val}`")
        else:
            unsupported.append(key)
    if unsupported:
        names = ", ".join(f"`{k}`" for k in unsupported)
        verb = "is a selector" if len(unsupported) == 1 else "are selectors"
        return (
            f"never matches automatically ({names} {verb} this adapter does "
            "not support, and an unknown selector fails closed, SPEC §2.1); "
            "applies only when explicitly activated by name"
        )
    conjoined = " and ".join(phrases)
    return f"{conjoined}; or when explicitly activated by name"


def budget_section(raw: dict) -> str | None:
    """The budget prose for the CLAUDE.md region: the declared policy,
    stated as a standing directive to the reading session in its role as
    launcher of other metered workloads (task 0001, RFC 0003 C2).

    Built from the RAW manifest, not the resolved config: a global render
    must be byte-identical regardless of the context it runs in (README,
    "Environments and a global render"), so the base budget and every
    *declared* [[environment]] override are read pre-resolution and
    environment matching never changes what this section says.

    That context-independence is why each override line is merged against
    the base alone rather than accumulated: the section states the declared
    policy and the composition rule, and the reading session — which is the
    only party that knows which environments actually apply — composes them.
    """
    budget = raw.get("budget")
    if not isinstance(budget, dict):
        return None
    on_exceed = budget.get("on_exceed")
    lines = [
        "# Budget (declared policy)\n",
        "The profile declares spend limits"
        + (f' with `on_exceed = "{on_exceed}"`' if on_exceed else "")
        + ":\n",
    ]
    for entry in budget.get("limits", []) or []:
        lines.append(f"- {describe_limit(entry)}")

    overrides = []
    for env in raw.get("environment", []) or []:
        if not isinstance(env, dict) or not isinstance(env.get("budget"), dict):
            continue
        # Each line states what this environment DECLARES, field by field —
        # not its budget merged onto the base, and not a running total.
        # Merging onto the base would erase the difference between a field
        # this environment inherits and one it explicitly resets to the base
        # value: after an earlier environment raises the limit, `on_exceed`
        # alone and `on_exceed` + base limits compose to different caps
        # (SPEC §2.1) but merge to identical text. Provenance per field is
        # what makes the header's composition rule performable by a reader.
        declared = env["budget"]
        stated = []
        if "limits" in declared:
            stated.append(
                "sets limits to "
                + "; ".join(describe_limit(e) for e in declared.get("limits") or [])
            )
        if "on_exceed" in declared:
            stated.append(f'sets `on_exceed = "{declared["on_exceed"]}"`')
        if not stated:
            continue
        if len(stated) == 1:
            stated.append(
                "leaves the other field as the base or an earlier environment "
                "left it"
            )
        overrides.append(
            f"- environment `{env.get('name')}` — "
            f"{describe_selector(env.get('when'))}: {'; '.join(stated)}"
        )
    if overrides:
        lines.append(
            "\nDeclared environment overrides. Each line states only the fields\n"
            "that environment actually declares — what it does not name, it\n"
            "leaves alone. Where more than one applies at once they compose in\n"
            "the declaration order below, later winning over earlier (SPEC\n"
            "§2.1), so the values in force are the last declared value of each\n"
            "field among those that apply — not necessarily any single line as\n"
            "written:\n"
        )
        lines.extend(overrides)

    lines.append(
        "\nWhen composing an invocation of any tool or harness that accepts a\n"
        "spend cap (for example `emcee --budget`), work out which of the above\n"
        "apply here, compose them in the order given, and pass the resulting\n"
        "amount. If the flag is left off, that tool's own default silently\n"
        "wins over this declared policy.\n"
    )
    lines.append(
        "This is declared policy, not runtime enforcement: nothing in this\n"
        "harness halts a model call at a spend threshold."
    )
    return "\n".join(lines) + "\n"


def gates_section(effective: dict, profile_dir: Path) -> str | None:
    """The gates prose for the CLAUDE.md region: each declared gate that
    carries a `run` script, stated as a standing directive to the reading
    session in its role as the thing that drives the workflow — it opens
    PRs, launches harnesses that open PRs, and prepares merges (task 0002).

    Built from the RESOLVED config, unlike budget_section: gates have no
    per-environment override idiom to render declaratively (an environment
    replaces the whole array, SPEC §2.1), so the effective list is the
    truthful one — and report_unrenderable flags the render as
    context-dependent if an environment actually contributed to it.

    A gate without `run` renders nothing: there is nothing actionable to
    state, and it stays in the render report as unsatisfied.

    Each gate's directive is conditioned on its `compose` mode — see
    COMPOSE_DIRECTIVE. The adapter cannot detect whether a project has a
    gate of its own (SPEC §2.2 leaves detection harness-specific and out of
    scope for v0.3), so the prose states the condition and leaves the
    reading session to evaluate it.
    """
    gates = [
        g for g in effective.get("gates", []) or []
        if isinstance(g, dict) and g.get("run")
    ]
    if not gates:
        return None
    lines = [
        "# Gates (declared policy)\n",
        "The profile declares standing gates on the resident's own work. Before",
        "performing a gate's `on` action — or setting in motion work that ends",
        "in it, such as opening a PR or launching a harness that opens PRs —",
        "apply the gate as its `compose` mode below directs, and surface what it",
        "finds. When launching a tool that accepts a post-PR or review hook, pass",
        "the script there rather than running it by hand afterwards.\n",
    ]
    for gate in gates:
        # `run` is profile-relative in the manifest (SPEC §3.7); the reader
        # of ~/.claude/CLAUDE.md needs a path they can actually execute.
        script = profile_dir / gate["run"]
        desc = gate.get("description")
        # SPEC §2.2 makes `layer` the default for additive sections.
        compose = gate.get("compose", "layer")
        template = COMPOSE_DIRECTIVE.get(compose, COMPOSE_UNKNOWN)
        directive = template.format(
            script=script, on=gate.get("on"), compose=compose
        )
        lines.append(
            f"- `{gate.get('id')}` — on `{gate.get('on')}`"
            + (f": {desc}." if desc else ".")
            + f"\n  {directive}"
        )
    lines.append(
        "\nThis is declared policy, not runtime enforcement: no hook in this\n"
        "harness fires a gate automatically."
    )
    return "\n".join(lines) + "\n"


def plugins_section(
    effective: dict, plugin_records: dict[str, dict] | None
) -> str | None:
    """The plugins prose for the CLAUDE.md region: the plugins this render
    actually delivered, plus a standing launcher directive (SPEC §3.11). A
    harness-level install never reaches an SDK-driven session — the SDK
    loads plugins only through an explicit per-invocation option — so the
    session reading this, in its role as launcher of such tools, is the
    one place the declaration can take effect there.

    Built from the render's own records, never from the declarations: a
    declaration that was skipped (authority withheld, no packaging) or
    failed has no checkout worth directing a launcher at, and prose
    claiming otherwise would point sessions at paths that do not exist."""
    records = plugin_records or {}
    if not records and not applicable_plugins(effective):
        return None
    lines = ["# Plugins (declared policy)\n"]
    if records:
        lines.append(
            "The profile declares harness plugins, installed from a pinned\n"
            "checkout in the plugin store:\n"
        )
        for pid, rec in sorted(records.items()):
            lines.append(f"- `{pid}` — pinned checkout: `{rec['checkout']}`")
        lines.append(
            "\nThis harness loads them through its own plugin config, but an\n"
            "SDK-driven session does not: the Agent SDK loads plugins only\n"
            "through an explicit per-invocation option. When launching a tool\n"
            "that dispatches SDK sessions and accepts a plugin path (for\n"
            "example an emcee `--plugin` flag or roster key, once present),\n"
            "pass each checkout path above. If the option is left off, those\n"
            "sessions run without the plugins this profile declares."
        )
    not_delivered = [p["id"] for p in applicable_plugins(effective) if p["id"] not in records]
    if not_delivered:
        names = ", ".join(f"`{n}`" for n in sorted(not_delivered))
        lines.append(
            f"\nDeclared but not installed by the last render: {names} — see\n"
            "that render's report for why. Do not direct launchers at\n"
            "checkouts this section does not list."
        )
    return "\n".join(lines) + "\n"


def render_region(
    effective: dict,
    raw: dict,
    profile_dir: Path,
    report: Report,
    plugin_records: dict[str, dict] | None = None,
) -> str:
    """The text between the markers: concatenated instructions, the
    reporting half of any `reported` authority classes, the declared
    budget as launcher-directive prose, `run`-carrying gates as standing
    prose, then declared plugins with their own launcher directive."""
    parts: list[str] = []
    resident = effective.get("resident", {})
    name = resident.get("name") if isinstance(resident, dict) else None
    who = f" of {name}" if name else ""
    parts.append(
        f"# Chevaline profile{who}\n\n"
        f"Rendered from the Chevaline profile at `{profile_dir}`. To change\n"
        "anything below, edit the profile and re-render — not this file.\n"
    )

    blocks = applicable_instructions(effective)
    for entry in blocks:
        path = profile_dir / entry["path"]
        parts.append(path.read_text().strip() + "\n")
    skipped = len(effective.get("instructions", []) or []) - len(blocks)
    if skipped:
        report.notes.append(
            f"instructions: {skipped} block(s) filtered out by a `harnesses` key "
            f"not naming {HARNESS_NAME}"
        )

    # The reporting dimension of `reported` authority classes (see the
    # mapping comment above): permission renders into settings.json, but
    # "and tell me" only has a prose channel.
    auth = effective.get("authority", {})
    actions = auth.get("actions", {}) if isinstance(auth, dict) else {}
    reported_classes = sorted(k for k, v in actions.items() if v == "reported")
    if reported_classes:
        lines = [
            "# Standing authority expectations\n",
            "These action classes are granted without asking, but each use must",
            "be reported in your response (authority level `reported`):\n",
        ]
        for cls in reported_classes:
            gloss = ACTION_GLOSS.get(cls, cls)
            lines.append(f"- `{cls}` — {gloss}: do it, then say you did.")
        parts.append("\n".join(lines) + "\n")

    section = budget_section(raw)
    if section is not None:
        parts.append(section)

    section = gates_section(effective, profile_dir)
    if section is not None:
        parts.append(section)

    section = plugins_section(effective, plugin_records)
    if section is not None:
        parts.append(section)

    return "\n".join(parts)


def splice_claude_md(existing: str | None, region: str) -> str:
    """Replace the marker-delimited region, or append one. Never touches
    text outside the markers (SPEC §4 item 3)."""
    block = f"{BEGIN_MARKER}\n\n{region}\n{END_MARKER}\n"
    if existing is None or existing.strip() == "":
        return block
    begin = existing.find(BEGIN_MARKER)
    end = existing.find(END_MARKER)
    if begin == -1 and end == -1:
        sep = "" if existing.endswith("\n\n") else "\n" if existing.endswith("\n") else "\n\n"
        return existing + sep + block
    if begin == -1 or end == -1 or end < begin:
        raise SystemExit(
            "ERROR: ~/.claude/CLAUDE.md contains a damaged chevaline marker pair "
            "(one marker missing, or end before begin). Refusing to guess at the "
            "owned region — fix the markers by hand and re-render."
        )
    return existing[:begin] + block.rstrip("\n") + existing[end + len(END_MARKER):]


# --------------------------------------------------------------------------
# settings.json rendering (sidecar-owned, SPEC §4 item 3)
# --------------------------------------------------------------------------


def desired_settings(effective: dict, report: Report) -> tuple[dict[str, list[str]], dict[str, Any]]:
    """Returns (list_entries, scalars) this render wants in settings.json.

    list_entries maps a dotted path (e.g. "permissions.allow") to entries to
    ensure present; scalars maps a dotted path (e.g. "model") to a value.
    """
    allow: list[str] = []
    ask: list[str] = []

    auth = effective.get("authority", {})
    actions = auth.get("actions", {}) if isinstance(auth, dict) else {}
    for cls, level in actions.items():
        rules = ACTION_RULES.get(cls)
        if rules is None:
            report.skipped.append(
                f"authority.actions.{cls} — no permission-rule mapping for this "
                "class (custom or unmapped); not rendered"
            )
            continue
        if level in ("silent", "reported"):
            allow.extend(rules)
        elif level == "approval":
            ask.extend(rules)
    if actions:
        report.notes.append(
            "authority: Bash permission rules match by command prefix — an "
            "advisory mapping, not a security boundary, and the rule table is "
            "best-effort, not exhaustive"
        )
    if isinstance(auth, dict) and "default" in auth:
        report.skipped.append(
            f"authority.default = {auth['default']!r} — Claude Code has no "
            "default-level knob with these semantics; its own prompting stands "
            "in (stricter, which §3.9's restrict composition permits)"
        )

    list_entries: dict[str, list[str]] = {}
    if allow:
        list_entries["permissions.allow"] = allow
    if ask:
        list_entries["permissions.ask"] = ask

    scalars: dict[str, Any] = {}
    models = effective.get("models", {})
    if isinstance(models, dict):
        tiers = {k: v for k, v in models.items() if k != "compose"}
        if MODEL_TIER_FOR_SETTINGS in tiers:
            scalars["model"] = tiers[MODEL_TIER_FOR_SETTINGS]
        for tier in sorted(set(tiers) - {MODEL_TIER_FOR_SETTINGS}):
            report.skipped.append(
                f"models.{tier} = {tiers[tier]!r} — settings.json carries a single "
                f"`model`, bound to the {MODEL_TIER_FOR_SETTINGS!r} tier; this tier "
                "has no global surface (per-subagent pinning is the closest fit)"
            )
    return list_entries, scalars


def get_path(obj: dict, dotted: str) -> Any:
    cur: Any = obj
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def set_path(obj: dict, dotted: str, value: Any) -> None:
    parts = dotted.split(".")
    cur = obj
    for part in parts[:-1]:
        if not isinstance(cur.get(part), dict):
            cur[part] = {}
        cur = cur[part]
    cur[parts[-1]] = value


def delete_path_if_empty(obj: dict, dotted: str) -> None:
    """Removes an empty list/dict left behind at `dotted`, then any parent
    dicts that became empty, so a full un-render leaves no husks."""
    parts = dotted.split(".")
    for depth in range(len(parts), 0, -1):
        parent = obj
        for part in parts[: depth - 1]:
            if not isinstance(parent, dict) or part not in parent:
                return
            parent = parent[part]
        key = parts[depth - 1]
        if isinstance(parent, dict) and key in parent and parent[key] in ([], {}):
            del parent[key]


def apply_settings(
    settings: dict,
    sidecar: dict,
    list_entries: dict[str, list[str]],
    scalars: dict[str, Any],
    report: Report,
    plugin_records: dict[str, dict] | None = None,
) -> tuple[dict, dict]:
    """Pure function from (current settings, current sidecar, desires) to
    (new settings, new sidecar). Ownership rules in the module docstring."""
    settings = copy.deepcopy(settings)
    owned = sidecar.get("owned", {})
    old_list_owned: dict[str, list[str]] = owned.get("listEntries", {})
    old_scalar_owned: list[str] = owned.get("scalars", [])

    new_list_owned: dict[str, list[str]] = {}
    new_scalar_owned: list[str] = []

    # Lists: strip everything we previously owned, then add what the profile
    # wants now, owning only entries we actually add (an entry the resident
    # already has by hand stays theirs, and we never remove it later).
    for path in sorted(set(old_list_owned) | set(list_entries)):
        current = get_path(settings, path)
        current_list = list(current) if isinstance(current, list) else []
        previously_ours = old_list_owned.get(path, [])
        kept = [e for e in current_list if e not in previously_ours]
        added = []
        for entry in list_entries.get(path, []):
            if entry not in kept and entry not in added:
                added.append(entry)
        result = kept + added
        if result or current is not None:
            set_path(settings, path, result)
        if added:
            new_list_owned[path] = added
            report.rendered.append(f"settings.json {path}: +{len(added)} entr{'y' if len(added)==1 else 'ies'} {added}")
        removed = [e for e in previously_ours if e in current_list and e not in added]
        if removed:
            report.rendered.append(f"settings.json {path}: removed formerly-owned {removed}")
        delete_path_if_empty(settings, path)

    # Scalars: write only keys that are absent or already ours; a key the
    # resident set by hand wins, reported as a conflict.
    for path in sorted(set(old_scalar_owned) | set(scalars)):
        current = get_path(settings, path)
        ours = path in old_scalar_owned
        if path not in scalars:
            if ours and current is not None:
                # Profile no longer wants it; un-render what we owned.
                parts = path.split(".")
                parent = settings
                for part in parts[:-1]:
                    parent = parent.get(part, {})
                if isinstance(parent, dict):
                    parent.pop(parts[-1], None)
                delete_path_if_empty(settings, ".".join(parts[:-1]) or path)
                report.rendered.append(f"settings.json {path}: removed (no longer in profile)")
            continue
        desired = scalars[path]
        if current is not None and not ours:
            if current == desired:
                report.notes.append(
                    f"settings.json {path}: already {desired!r} by hand; not claiming ownership"
                )
            else:
                report.conflicts.append(
                    f"settings.json {path}: profile wants {desired!r}, but the "
                    f"resident set {current!r} by hand — hand-written config wins "
                    "(SPEC §4 item 3); remove the key and re-render to let the "
                    "profile own it"
                )
            continue
        if current != desired:
            set_path(settings, path, desired)
            report.rendered.append(f"settings.json {path} = {desired!r}")
        new_scalar_owned.append(path)

    new_sidecar = {
        "_comment": (
            "Sidecar manifest for the Chevaline claude-code adapter (SPEC §4 "
            "item 3): settings.json is JSON, which has no comments to hold "
            "ownership markers, so the keys and list entries the adapter owns "
            "are recorded here instead. Do not edit; re-rendering rewrites it."
        ),
        "owned": {
            "scalars": sorted(new_scalar_owned),
            "listEntries": {k: v for k, v in sorted(new_list_owned.items())},
        },
    }
    if plugin_records:
        new_sidecar["plugins"] = {k: v for k, v in sorted(plugin_records.items())}
    return settings, new_sidecar


# --------------------------------------------------------------------------
# Plugins (SPEC §3.11, §4.2)
#
# The claude-code surfaces used are the documented ones only: the plugin
# store checkout is registered as a local marketplace through the stable
# `claude plugin marketplace add` CLI (registration has no documented file
# surface), and enablement is the documented `enabledPlugins` settings key,
# written and owned through the same sidecar machinery as every other
# scalar. The internal `~/.claude/plugins/` state files are never touched.
#
# Materializing a checkout is an `exec.install`-class action (§4.2): at
# `approval` — including the unresolved case — nothing is fetched unless
# the resident passed --allow-install for this invocation; at `reported`
# the fetch happens and the report says so; at `silent` it just happens.
# --------------------------------------------------------------------------


def applicable_plugins(effective: dict) -> list[dict]:
    out = []
    for entry in effective.get("plugins", []) or []:
        if not isinstance(entry, dict):
            continue
        harnesses = entry.get("harnesses")
        if harnesses is None or HARNESS_NAME in harnesses:
            out.append(entry)
    return out


def install_authority(effective: dict) -> str:
    """The resolved authority level for exec.install. Unresolved — no
    action entry and no default — behaves as `approval` (SPEC §4.2)."""
    auth = effective.get("authority", {})
    if not isinstance(auth, dict):
        return "approval"
    actions = auth.get("actions", {})
    level = actions.get("exec.install") if isinstance(actions, dict) else None
    if level is None:
        level = auth.get("default")
    return level if level in ("silent", "reported", "approval") else "approval"


def run_claude_cli(cli: str, claude_dir: Path, cli_args: list[str]) -> subprocess.CompletedProcess:
    """Runs the documented `claude plugin ...` CLI against the render's
    target config dir. CLAUDE_CONFIG_DIR keeps the CLI's writes and this
    adapter's file writes pointed at the same directory."""
    env = dict(os.environ)
    env["CLAUDE_CONFIG_DIR"] = str(claude_dir)
    return subprocess.run(
        [cli, *cli_args], capture_output=True, text=True, env=env, timeout=120
    )


def render_plugins(
    effective: dict,
    args: argparse.Namespace,
    profile_dir: Path,
    claude_dir: Path,
    old_sidecar: dict,
    report: Report,
) -> tuple[dict[str, Any], dict[str, dict], list[str]]:
    """Returns (extra_scalars for settings.json, sidecar plugin records,
    errors). Runs the store materialization and marketplace registration —
    except under --dry-run, which only reports what would happen."""
    scalars: dict[str, Any] = {}
    records: dict[str, dict] = {}
    errors: list[str] = []

    declared = effective.get("plugins", []) or []
    plugins = applicable_plugins(effective)
    filtered = len(declared) - len(plugins)
    if filtered:
        report.notes.append(
            f"plugins: {filtered} entr{'y' if filtered == 1 else 'ies'} filtered out by a "
            f"`harnesses` key not naming {HARNESS_NAME}"
        )
    old_records: dict[str, dict] = (old_sidecar.get("plugins") or {})

    level = install_authority(effective)
    store = Path(args.plugin_store).expanduser() if args.plugin_store else plugstore.default_store()

    for entry in plugins:
        pid, pin = entry["id"], entry["pin"]
        compose = entry.get("compose", "layer")
        if compose != "layer":
            # Native enablement is unconditional: it cannot express "only
            # where the project has no plugin opinion" (defer) or "stop on
            # a conflict" (insist), and project-opinion detection is out of
            # scope for v0.3 (RFC 0005). Silently layering would override
            # the declared mode, so these render nothing and say so.
            report.skipped.append(
                f"plugins.{pid} (compose={compose!r}) — native plugin enablement "
                "is unconditional, and this adapter cannot detect a project's "
                "own plugin opinion (RFC 0005), so a non-layer mode cannot be "
                "honored natively; not rendered"
            )
            continue
        source = plugstore.resolve_source(entry["source"], profile_dir)
        checkout = plugstore.checkout_dir(store, pid, pin)
        materialized = checkout.exists()

        if not materialized and level == "approval" and not args.allow_install:
            report.skipped.append(
                f"plugins.{pid} — materializing {source} at {pin[:12]} is an "
                "exec.install-class action and the resolved authority is "
                "'approval' (or unresolved, which behaves the same, SPEC §4.2); "
                "re-run with --allow-install to authorize this invocation"
            )
            continue

        if not materialized and args.dry_run:
            report.notes.append(
                f"plugins.{pid}: DRY RUN — would materialize into {checkout}, "
                "register it as a local marketplace via `claude plugin "
                "marketplace add`, and enable it via the owned "
                "`enabledPlugins` settings key"
            )
            continue

        # Runs for existing checkouts too: materialize is offline and
        # idempotent there, and it is the only place the checkout's HEAD is
        # verified against the pin (SPEC §4.2) — a stale or tampered store
        # entry must not be registered just because its directory exists.
        try:
            checkout, fetched = plugstore.materialize(pid, source, pin, store)
        except plugstore.PlugstoreError as e:
            errors.append(f"plugins.{pid}: {e}")
            continue
        if fetched:
            verb = {
                "silent": "materialized",
                "reported": "materialized (exec.install is 'reported': saying so)",
                "approval": "materialized (exec.install is 'approval'; authorized by --allow-install)",
            }[level]
            report.rendered.append(f"plugins.{pid}: {verb} {source} @ {pin[:12]} → {checkout}")

        # From here the checkout exists, so the desired state is computable
        # in a dry run too — only the CLI actions stay behind the dry-run
        # guard. A dry run that dropped the desired records here would then
        # report removals a real render would never perform.
        mkt_path = checkout / ".claude-plugin" / "marketplace.json"
        if not mkt_path.is_file():
            report.skipped.append(
                f"plugins.{pid} — the checkout has no .claude-plugin/marketplace.json, "
                "so there is no claude-code packaging to register; the entry lists "
                f"{HARNESS_NAME} (or lists no harnesses), which looks like a mismatch "
                "with what the plugin repo actually ships (SPEC §4.2)"
            )
            continue
        try:
            mkt = json.loads(mkt_path.read_text())
        except (OSError, json.JSONDecodeError) as e:
            errors.append(f"plugins.{pid}: unreadable marketplace.json ({e})")
            continue
        if not isinstance(mkt, dict) or not isinstance(mkt.get("plugins", []), list):
            errors.append(
                f"plugins.{pid}: marketplace.json is valid JSON but not marketplace-"
                "shaped (object with a `plugins` array); refusing to guess"
            )
            continue
        mkt_name = mkt.get("name")
        matched = next(
            (p for p in mkt.get("plugins", []) if isinstance(p, dict) and p.get("name") == pid),
            None,
        )
        if not isinstance(mkt_name, str) or matched is None:
            report.skipped.append(
                f"plugins.{pid} — the checkout's marketplace.json does not list a "
                f"plugin named '{pid}' (marketplace {mkt_name!r}); the profile id "
                "must match the plugin's own name for the enablement key to mean "
                "anything"
            )
            continue
        # The matched entry's own source must resolve inside the pinned
        # checkout. A marketplace may point a plugin at a remote or at a
        # path outside the checkout; enabling that would execute content
        # the pin never covered — the exact thing the pin exists to prevent.
        plugin_src = matched.get("source")
        src_ok = (
            isinstance(plugin_src, str)
            and "://" not in plugin_src
            and not Path(plugin_src).is_absolute()
        )
        if src_ok:
            resolved = Path(os.path.normpath(checkout / plugin_src))
            src_ok = resolved == checkout or resolved.is_relative_to(checkout)
        if not src_ok:
            errors.append(
                f"plugins.{pid}: the marketplace entry's source {plugin_src!r} "
                "points outside the pinned checkout, so enabling it would "
                "execute content the pin never verified (SPEC §4.2); refusing"
            )
            continue
        identity = f"{pid}@{mkt_name}"
        if "." in identity:
            report.skipped.append(
                f"plugins.{pid} — identity '{identity}' contains a dot, which this "
                "adapter's dotted-path settings ownership cannot represent; not rendered"
            )
            continue

        prior = old_records.get(pid)
        up_to_date = bool(
            prior
            and prior.get("marketplace") == mkt_name
            and prior.get("pin") == pin
            and prior.get("checkout") == str(checkout)
        )
        if up_to_date:
            report.notes.append(f"plugins.{pid}: already registered at this pin; no CLI call")
        elif args.dry_run:
            report.notes.append(
                f"plugins.{pid}: DRY RUN — would register local marketplace "
                f"'{mkt_name}' → {checkout} and enable '{identity}'"
            )
        else:
            try:
                # Reaching here with a prior record means the pin or the
                # checkout location changed; either way the old registration
                # points somewhere stale and is removed before the re-add.
                if prior and prior.get("marketplace"):
                    removal = run_claude_cli(
                        args.claude_cli, claude_dir,
                        ["plugin", "marketplace", "remove", prior["marketplace"]],
                    )
                    if removal.returncode != 0:
                        report.notes.append(
                            f"plugins.{pid}: could not remove the old marketplace "
                            f"registration before re-registering ({(removal.stderr or removal.stdout).strip()}); "
                            "continuing with the add"
                        )
                added = run_claude_cli(
                    args.claude_cli, claude_dir,
                    ["plugin", "marketplace", "add", str(checkout)],
                )
            except (OSError, subprocess.SubprocessError) as e:
                errors.append(
                    f"plugins.{pid}: could not run the `{args.claude_cli}` CLI ({e}) — "
                    "marketplace registration has no documented file surface, so this "
                    "adapter cannot register the plugin without it"
                )
                continue
            output = ((added.stderr or "") + (added.stdout or "")).lower()
            if added.returncode != 0:
                # "Already exists" is only success if the existing
                # registration is the one this adapter recorded for this
                # exact checkout. A same-named marketplace the resident
                # registered by hand — or a stale one left by a failed
                # re-pin removal — must surface as a conflict, not be
                # silently adopted (and later removed) as ours.
                ours_already = (
                    "already" in output
                    and prior is not None
                    and prior.get("marketplace") == mkt_name
                    and prior.get("checkout") == str(checkout)
                )
                if not ours_already:
                    errors.append(
                        f"plugins.{pid}: `claude plugin marketplace add {checkout}` "
                        f"failed: {(added.stderr or added.stdout).strip()}"
                        + (
                            " — a marketplace with this name already exists and is "
                            "not one this adapter registered for this checkout; "
                            "resolve the collision by hand (/plugin) and re-render"
                            if "already" in output
                            else ""
                        )
                    )
                    continue
            report.rendered.append(
                f"plugins.{pid}: registered local marketplace '{mkt_name}' → {checkout}"
            )

        scalars[f"enabledPlugins.{identity}"] = True
        records[pid] = {
            "identity": identity,
            "marketplace": mkt_name,
            "checkout": str(checkout),
            "pin": pin,
            "source": source,
        }

    # Plugins the profile no longer declares (or no longer aims at this
    # harness): their enabledPlugins scalar un-renders through the ordinary
    # scalar-ownership path; the marketplace registration is removed here.
    live_marketplaces = {r["marketplace"] for r in records.values()}
    for pid, rec in sorted(old_records.items()):
        if pid in records:
            continue
        if args.dry_run:
            report.notes.append(f"plugins.{pid}: DRY RUN — would remove (no longer in profile)")
            records[pid] = rec  # keep the record; nothing was actually removed
            continue
        mkt_name = rec.get("marketplace")
        if mkt_name and mkt_name not in live_marketplaces:
            try:
                removal = run_claude_cli(
                    args.claude_cli, claude_dir,
                    ["plugin", "marketplace", "remove", mkt_name],
                )
                if removal.returncode != 0:
                    report.notes.append(
                        f"plugins.{pid}: `claude plugin marketplace remove {mkt_name}` "
                        f"failed ({(removal.stderr or removal.stdout).strip()}); remove it "
                        "by hand with /plugin"
                    )
            except (OSError, subprocess.SubprocessError) as e:
                report.notes.append(
                    f"plugins.{pid}: could not run the CLI to remove marketplace "
                    f"'{mkt_name}' ({e}); remove it by hand with /plugin"
                )
        report.rendered.append(f"plugins.{pid}: removed (no longer in profile)")

    return scalars, records, errors


# --------------------------------------------------------------------------
# Sections with no enforcing surface (reported, per SPEC §4 item 5 / §4.1)
# --------------------------------------------------------------------------


def report_unrenderable(effective: dict, explain: dict, report: Report) -> None:
    budget = effective.get("budget")
    if isinstance(budget, dict):
        limits = budget.get("limits", [])
        described = ", ".join(
            f"{e.get('scope')}/{e.get('window')}: {e.get('amount')} {e.get('unit')}"
            for e in limits
            if isinstance(e, dict)
        )
        report.unenforced.append(
            f"budget ({described}; on_exceed={budget.get('on_exceed')!r}) — stated "
            "as standing prose in the CLAUDE.md region (declared policy plus a "
            "launcher directive), but still NOT runtime-enforced on this harness: "
            "no Claude Code setting stops a model call at a spend threshold "
            "(SPEC §4.1: a non-enforcing adapter must say so). A PreToolUse hook "
            "reading provider usage is the intended future mechanism."
        )

    for gate in effective.get("gates", []) or []:
        if not isinstance(gate, dict):
            continue
        report.skipped.append(
            f"gates.{gate.get('id')} (on={gate.get('on')!r}, "
            f"compose={gate.get('compose', 'layer')!r}) — stated as standing "
            "prose in the CLAUDE.md region (the declaration plus a directive, "
            "conditioned on the compose mode, for its script and the gate's "
            "`on` action), but still not "
            "natively enforced on this harness: Claude Code has no "
            f"user-level hook surface that fires on {gate.get('on')}, so the "
            "session reading the prose, not the harness, carries the gate"
            if gate.get("run")
            else f"gates.{gate.get('id')} — no `run` and no native surface; unsatisfied"
        )

    sessions = effective.get("sessions")
    if isinstance(sessions, dict) and "isolation" in sessions:
        compose = sessions.get("compose", "defer")
        report.skipped.append(
            f"sessions.isolation = {sessions['isolation']!r} (compose={compose!r}) — "
            "no user-level Claude Code setting selects an isolation convention, "
            "and project-opinion detection is out of scope for v0.3 (RFC 0005), "
            "so a defer cannot be evaluated; not rendered"
        )

    for ext in effective.get("extensions", []) or []:
        if isinstance(ext, dict):
            report.skipped.append(
                f"extensions.{ext.get('id')} — v0.3 defines identification only, "
                "no invocation protocol (SPEC §3.10, under review in RFC 0007); "
                "not rendered"
            )

    # Environments that contributed to a *rendered* surface deserve a loud
    # note: this render is global, but path/git_org selectors vary per
    # project, so the resident should know context leaked into ~/.claude.
    # `budget` renders into CLAUDE.md too but is deliberately absent here:
    # its section is built from the raw manifest (see budget_section), so
    # environment matching cannot leak into it. `gates` IS here: its
    # section renders from the resolved config (see gates_section), so an
    # environment that replaces the gates array leaks into global prose.
    rendered_prefixes = ("instructions", "authority", "models", "resident", "gates")
    contaminated = {
        env for path, env in explain.get("sources", {}).items()
        if path.startswith(rendered_prefixes)
    }
    if contaminated:
        report.notes.append(
            "CONTEXT-DEPENDENT RENDER: environment(s) "
            f"{sorted(contaminated)} overrode values that render into global "
            "config. This render is only correct for the context it was run "
            "in — re-render from a neutral directory if that was not intended."
        )


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def cmd_render(args: argparse.Namespace) -> int:
    profile_dir = Path(args.profile_dir).resolve()
    claude_dir = Path(args.claude_dir).expanduser()
    ctx = ch.build_context(args.cwd, args.hostname, args.git_org)
    explicit = set(args.environment) if args.environment else None

    effective, errors, warnings, explain = ch.resolve_profile(profile_dir, ctx, explicit)
    for w in warnings:
        ch.print_warning(w, file=sys.stderr)
    if errors or effective is None or explain is None:
        for e in errors:
            print(f"ERROR: {e}", file=sys.stderr)
        print("Profile invalid or unresolvable; nothing rendered (SPEC §4 item 1).", file=sys.stderr)
        return 1

    harnesses = effective.get("harnesses", {})
    prefer = harnesses.get("prefer") if isinstance(harnesses, dict) else None
    if isinstance(prefer, list) and prefer and HARNESS_NAME not in prefer:
        print(
            f"harnesses.prefer = {prefer!r} does not include {HARNESS_NAME!r}; "
            "declining to render (README: [harnesses] decides whether this "
            "adapter runs at all).",
            file=sys.stderr,
        )
        return 1

    report = Report()
    report.environments = explain["environments"]

    # settings.json + sidecar are read (and settings parsed) BEFORE the
    # plugins phase: a malformed settings.json must abort the render before
    # any store fetch or marketplace CLI call mutates native state, and the
    # sidecar's records are what plugin idempotence and un-render consult.
    settings_path = claude_dir / "settings.json"
    sidecar_path = claude_dir / SIDECAR_NAME
    try:
        settings = json.loads(settings_path.read_text()) if settings_path.is_file() else {}
    except json.JSONDecodeError as e:
        print(f"ERROR: {settings_path} is not valid JSON ({e}); refusing to touch it.", file=sys.stderr)
        return 1
    sidecar = json.loads(sidecar_path.read_text()) if sidecar_path.is_file() else {}

    plugin_scalars, plugin_records, plugin_errors = render_plugins(
        effective, args, profile_dir, claude_dir, sidecar, report
    )

    # CLAUDE.md, after the plugins phase so the region's plugins section
    # states only what this render actually delivered. The budget section
    # renders from the raw manifest — resolve_profile strips
    # [[environment]] out of `effective`, and the declared overrides must
    # appear regardless of what matched here.
    raw, _ = ch.load_manifest(profile_dir)
    region = render_region(
        effective, raw or {}, profile_dir, report, plugin_records=plugin_records
    )
    md_path = claude_dir / "CLAUDE.md"
    existing_md = md_path.read_text() if md_path.is_file() else None
    new_md = splice_claude_md(existing_md, region)
    if new_md != (existing_md or ""):
        report.rendered.append(
            f"{md_path} — chevaline region "
            f"({'created file' if existing_md is None else 'updated in place'}, "
            f"{len(region)} chars)"
        )
    else:
        report.notes.append(f"{md_path}: already up to date")

    list_entries, scalars = desired_settings(effective, report)
    scalars.update(plugin_scalars)
    new_settings, new_sidecar = apply_settings(
        settings, sidecar, list_entries, scalars, report, plugin_records
    )

    report_unrenderable(effective, explain, report)
    for e in plugin_errors:
        report.unenforced.append(f"PLUGIN ERROR: {e}")

    if args.dry_run:
        report.notes.append("DRY RUN: nothing was written.")
        report.print()
        return 1 if plugin_errors else 0

    claude_dir.mkdir(parents=True, exist_ok=True)
    if new_md != (existing_md or ""):
        md_path.write_text(new_md)
    if new_settings != settings or new_sidecar != sidecar or not sidecar_path.is_file():
        settings_path.write_text(json.dumps(new_settings, indent=2) + "\n")
        sidecar_path.write_text(json.dumps(new_sidecar, indent=2) + "\n")
    report.print()
    return 1 if plugin_errors else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="adapter.py", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("render", help="Render a profile into Claude Code user config")
    p.add_argument("profile_dir", help="Path to the Chevaline profile directory")
    p.add_argument("--claude-dir", default="~/.claude", help="Claude Code config dir (default ~/.claude)")
    p.add_argument("--dry-run", action="store_true", help="Report without writing")
    p.add_argument(
        "--allow-install",
        action="store_true",
        help=(
            "Authorize exec.install-class plugin materialization for this "
            "invocation (SPEC §4.2) — required when the profile's resolved "
            "authority for exec.install is 'approval' or unresolved"
        ),
    )
    p.add_argument(
        "--plugin-store",
        default=None,
        help="Override the plugin store directory (default: $XDG_DATA_HOME/chevaline/plugins)",
    )
    p.add_argument(
        "--claude-cli",
        default="claude",
        help="The claude CLI to use for plugin marketplace registration (default: claude)",
    )
    p.add_argument("--cwd", default=None, help="Context cwd for `path` selectors")
    p.add_argument("--hostname", default=None, help="Context hostname for `hostname` selectors")
    p.add_argument("--git-org", dest="git_org", default=None, help="Context git org for `git_org` selectors")
    p.add_argument("--environment", action="append", default=None, metavar="NAME",
                   help="Explicitly activate an environment by name (SPEC §3.2)")
    p.set_defaults(func=cmd_render)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
