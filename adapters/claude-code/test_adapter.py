"""Tests for adapters/claude-code/adapter.py. Stdlib unittest only.

Fixtures are written to temp dirs at test time; nothing is added to the repo
and nothing touches a real ~/.claude. Plugin tests build a real local git
repository as the plugin source and substitute a recording stub for the
`claude` CLI, so no network and no real Claude Code installation is needed.
"""

from __future__ import annotations

import io
import json
import stat
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import adapter  # noqa: E402


PROFILE_TOML = """
spec = "0.3"

[resident]
name = "Test Resident"

[harnesses]
prefer = ["claude-code", "codex"]

[models]
cheap = "cheap-model"
standard = "standard-model"
deep = "deep-model"

[budget]
on_exceed = "halt"
limits = [
  { scope = "*", window = "session", amount = 10, unit = "USD" },
]

[[instructions]]
path = "instructions/a.md"

[[instructions]]
path = "instructions/b.md"
harnesses = ["codex"]

[[gates]]
id = "second-opinion"
on = "merge"
description = "test gate"
compose = "layer"

[[gates]]
id = "cross-vendor-review"
on = "merge"
description = "review the branch with a different vendor's model"
compose = "layer"
run = "scripts/review.py"

[sessions]
isolation = "worktree"
compose = "defer"

[authority]
default = "reported"

[authority.actions]
"fs.write" = "silent"
"vcs.commit" = "reported"
"vcs.push" = "approval"

[[environment]]
name = "emcee"
when = { path = "/emceeland*" }

[environment.budget]
on_exceed = "halt"
limits = [
  { scope = "*", window = "session", amount = 25, unit = "USD" },
]
"""

# The base [budget] block verbatim, for tests that remove it wholesale.
BUDGET_BLOCK = """[budget]
on_exceed = "halt"
limits = [
  { scope = "*", window = "session", amount = 10, unit = "USD" },
]
"""

# The run-carrying gate verbatim, for tests that remove it wholesale.
RUN_GATE_BLOCK = """[[gates]]
id = "cross-vendor-review"
on = "merge"
description = "review the branch with a different vendor's model"
compose = "layer"
run = "scripts/review.py"

"""


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


class AdapterCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.profile = root / "profile"
        self.claude = root / "claude"
        write(self.profile / "chevaline.toml", PROFILE_TOML)
        write(self.profile / "instructions/a.md", "# Instruction A\n\nBody A.\n")
        write(self.profile / "instructions/b.md", "# Instruction B (codex only)\n")
        write(self.profile / "scripts/review.py", "# stand-in gate script\n")

    def tearDown(self):
        self.tmp.cleanup()

    def render(self, *extra: str, cwd: str = "/nowhere") -> tuple[int, str]:
        argv = [
            "render",
            str(self.profile),
            "--claude-dir",
            str(self.claude),
            "--cwd",
            cwd,
            "--hostname",
            "testhost",
            "--git-org",
            "none",
            *extra,
        ]
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = adapter.main(argv)
        return rc, buf.getvalue()

    def settings(self) -> dict:
        return json.loads((self.claude / "settings.json").read_text())

    def sidecar(self) -> dict:
        return json.loads((self.claude / adapter.SIDECAR_NAME).read_text())


class TestFirstRender(AdapterCase):
    def test_renders_instructions_region_with_markers(self):
        rc, _ = self.render()
        self.assertEqual(rc, 0)
        md = (self.claude / "CLAUDE.md").read_text()
        self.assertIn(adapter.BEGIN_MARKER, md)
        self.assertIn(adapter.END_MARKER, md)
        self.assertIn("Instruction A", md)
        # Filtered out by harnesses = ["codex"] (SPEC §3.6).
        self.assertNotIn("Instruction B", md)

    def test_reported_authority_becomes_prose_and_allow(self):
        rc, out = self.render()
        self.assertEqual(rc, 0)
        md = (self.claude / "CLAUDE.md").read_text()
        self.assertIn("vcs.commit", md)  # the "tell me" half, as prose
        s = self.settings()
        self.assertIn("Bash(git commit:*)", s["permissions"]["allow"])
        self.assertIn("Edit", s["permissions"]["allow"])  # silent → allow
        self.assertIn("Bash(git push:*)", s["permissions"]["ask"])  # approval → ask

    def test_model_scalar_written_and_owned(self):
        self.render()
        self.assertEqual(self.settings()["model"], "standard-model")
        self.assertIn("model", self.sidecar()["owned"]["scalars"])

    def test_budget_reported_unenforced(self):
        rc, out = self.render()
        self.assertIn("NOT ENFORCED", out)
        self.assertIn("budget", out)
        # Task 0001 rewording: the report acknowledges the prose surface and
        # still refuses to claim runtime enforcement.
        self.assertIn("stated as standing prose in the CLAUDE.md region", out)
        self.assertIn("still NOT runtime-enforced", out)

    def test_gate_and_sessions_reported_skipped(self):
        _, out = self.render()
        self.assertIn("gates.second-opinion", out)
        self.assertIn("sessions.isolation", out)


class TestBudgetProse(AdapterCase):
    """Task 0001: [budget] renders into the CLAUDE.md region as declared
    policy plus a launcher directive, context-independently."""

    def test_budget_section_rendered_with_directive_and_override(self):
        rc, _ = self.render()
        self.assertEqual(rc, 0)
        md = (self.claude / "CLAUDE.md").read_text()
        self.assertIn("# Budget (declared policy)", md)
        self.assertIn('`on_exceed = "halt"`', md)
        self.assertIn("10 USD per session, aggregate over all spend", md)
        # The launcher directive: pass the cap along, or the launched tool's
        # own default silently wins.
        self.assertIn("emcee --budget", md)
        self.assertIn("silently\nwins over this declared policy", md)
        # The declared environment override, with its selector, rendered
        # even though this render's cwd does not match it.
        self.assertIn("environment `emcee` — under `/emceeland*`", md)
        self.assertIn("25 USD per session, aggregate over all spend", md)
        # Honesty: declared policy, not runtime enforcement.
        self.assertIn("not runtime enforcement", md)

    def test_render_is_identical_whatever_cwd(self):
        rc1, _ = self.render()
        self.assertEqual(rc1, 0)
        md1 = (self.claude / "CLAUDE.md").read_text()
        s1 = (self.claude / "settings.json").read_text()
        # Re-render from a cwd where the emcee environment matches; the
        # environment really matches (asserted via the report), but the
        # rendered files must not change.
        rc2, out2 = self.render(cwd="/emceeland/project")
        self.assertEqual(rc2, 0)
        self.assertIn("emcee: MATCHED", out2)
        self.assertEqual(md1, (self.claude / "CLAUDE.md").read_text())
        self.assertEqual(s1, (self.claude / "settings.json").read_text())

    def test_removing_budget_unrenders_exactly_that_section(self):
        # End-to-end, a budget-less profile is invalid (SPEC §3.5 requires
        # an aggregate limit), so the un-render invariant is exercised at
        # the render_region level: same profile, with and without [budget].
        self.render()
        md_with = (self.claude / "CLAUDE.md").read_text()
        raw, errors = adapter.ch.load_manifest(self.profile)
        self.assertFalse(errors)
        section = adapter.budget_section(raw)
        self.assertIn(section, md_with)

        ctx = adapter.ch.build_context("/nowhere", "testhost", "none")
        effective, errors, _, _ = adapter.ch.resolve_profile(self.profile, ctx)
        self.assertFalse(errors)
        effective.pop("budget")
        raw.pop("budget")
        region = adapter.render_region(effective, raw, self.profile, adapter.plugstore.default_store(), adapter.Report())
        md_without = adapter.splice_claude_md(md_with, region)
        # Exactly the budget section is gone; every other byte survives.
        self.assertEqual(md_without, md_with.replace("\n" + section, "", 1))
        self.assertNotIn("# Budget", md_without)
        self.assertIn("Instruction A", md_without)
        self.assertIn("Standing authority expectations", md_without)

    def test_override_lines_state_the_declaration_order_rule(self):
        # The header must not claim a single matching environment's limits
        # are the ones in force: environments compose in declaration order
        # (SPEC §2.1), so several can apply at once and the last declared
        # value of each field wins.
        rc, _ = self.render()
        self.assertEqual(rc, 0)
        md = (self.claude / "CLAUDE.md").read_text()
        self.assertIn("compose in\nthe declaration order below", md)
        self.assertIn("later winning over earlier", md)
        self.assertNotIn("in force instead of the base limits", md)

    def test_budgetless_profile_is_refused_not_rerendered(self):
        # The CLI-level counterpart: removing [budget] wholesale makes the
        # profile invalid, and the adapter refuses rather than re-rendering,
        # so the previous render (budget section included) stays intact.
        self.render()
        md_before = (self.claude / "CLAUDE.md").read_text()
        toml = PROFILE_TOML.replace(BUDGET_BLOCK, "")
        self.assertNotIn("[budget]\n", toml)
        write(self.profile / "chevaline.toml", toml)
        rc, _ = self.render()
        self.assertEqual(rc, 1)
        self.assertEqual(md_before, (self.claude / "CLAUDE.md").read_text())


class TestBudgetOverrideLabels(unittest.TestCase):
    """PR #2 review: what an override line claims about when it applies.
    budget_section is called directly — these cases turn on the raw
    manifest's shape, not on anything the resolver does with it."""

    BASE = {"on_exceed": "halt", "limits": [
        {"scope": "*", "window": "session", "amount": 10, "unit": "USD"},
    ]}

    def section(self, *envs: dict) -> str:
        return adapter.budget_section({"budget": self.BASE, "environment": list(envs)})

    def env(self, name: str, when: dict | None, amount: int = 25, **extra) -> dict:
        e = {"name": name, "budget": {"limits": [
            {"scope": "*", "window": "session", "amount": amount, "unit": "USD"},
        ], **extra}}
        if when is not None:
            e["when"] = when
        return e

    def test_explicit_activation_is_named_even_with_a_selector(self):
        # --environment bypasses `when` entirely (SPEC §3.2), so a line that
        # names only the selector understates when the override applies.
        section = self.section(self.env("work", {"git_org": "Castle-Turing"}))
        self.assertIn("in git org `Castle-Turing`; or when explicitly activated by name", section)

    def test_multiple_predicates_are_conjoined_not_listed_as_alternatives(self):
        # Every predicate in a `when` block must hold (SPEC §3.2), so a comma
        # list would invite a session to apply the override on one match.
        section = self.section(self.env("prod", {"path": "/work/**", "hostname": "prod"}))
        self.assertIn("under `/work/**` and on host `prod`; or when explicitly", section)

    def test_whenless_environment_says_activation_only(self):
        section = self.section(self.env("manual", None))
        self.assertIn("applies only when explicitly activated by name", section)

    def test_unknown_selector_renders_as_never_matching(self):
        # The resolver fails an unknown selector closed (SPEC §2.1); the
        # prose must not read like a condition that could hold.
        section = self.section(self.env("future", {"region": "eu-west"}))
        self.assertIn("never matches automatically", section)
        self.assertIn("`region` is a selector this adapter does not support", section)
        self.assertIn("fails closed", section)
        self.assertNotIn("when `region` matches `eu-west`", section)

    def test_environment_matching_the_base_still_renders(self):
        # Nil against the base alone, but load-bearing under composition: it
        # resets a preceding environment's override back to the base.
        raised = self.env("raise", {"path": "/a*"}, amount=25)
        reset = self.env("reset", {"path": "/a/b*"}, amount=10)
        section = self.section(raised, reset)
        self.assertIn("environment `reset`", section)
        self.assertLess(section.index("environment `raise`"), section.index("environment `reset`"))

    def test_a_line_states_only_the_fields_that_environment_declares(self):
        # `later` declares on_exceed alone, so it must not appear to carry a
        # limit — neither the base's (merging) nor an earlier one's
        # (accumulating). Whatever it does not name, it leaves alone.
        section = self.section(
            self.env("earlier", {"path": "/a*"}, amount=25),
            {"name": "later", "when": {"path": "/b*"}, "budget": {"on_exceed": "warn"}},
        )
        later_line = [l for l in section.splitlines() if "`later`" in l][0]
        self.assertIn('sets `on_exceed = "warn"`', later_line)
        self.assertIn("leaves the other field", later_line)
        self.assertNotIn("USD", later_line)

    def test_an_inherited_field_reads_differently_from_an_explicit_reset(self):
        # After an earlier environment raises the limit, on_exceed alone
        # composes to 25/warn while on_exceed plus the base limits composes
        # to 10/warn (SPEC §2.1). Rendering both as the base merge made them
        # identical text, so the reader could not perform the composition the
        # header asks for.
        inherits = self.section(
            self.env("earlier", {"path": "/a*"}, amount=25),
            {"name": "later", "when": {"path": "/b*"}, "budget": {"on_exceed": "warn"}},
        )
        resets = self.section(
            self.env("earlier", {"path": "/a*"}, amount=25),
            self.env("later", {"path": "/b*"}, amount=10, on_exceed="warn"),
        )
        self.assertNotEqual(
            [l for l in inherits.splitlines() if "`later`" in l][0],
            [l for l in resets.splitlines() if "`later`" in l][0],
        )
        self.assertIn("sets limits to 10 USD per session", resets)


class TestGatesProse(AdapterCase):
    """Task 0002: a `run`-carrying gate renders into the CLAUDE.md region
    as standing prose — declaration plus directive — while a run-less gate
    keeps its report-only treatment."""

    def test_run_gate_rendered_with_resolved_path_and_directive(self):
        rc, _ = self.render()
        self.assertEqual(rc, 0)
        md = (self.claude / "CLAUDE.md").read_text()
        self.assertIn("# Gates (declared policy)", md)
        self.assertIn("`cross-vendor-review` — on `merge`", md)
        self.assertIn("review the branch with a different vendor's model", md)
        # The `run` path is resolved against the profile root: the reader
        # gets a path they can execute, not a manifest-relative fragment.
        self.assertIn(f"`{self.profile / 'scripts/review.py'}`", md)
        # The standing directive covers work that *ends* in the on-event,
        # and prefers a launched tool's own hook surface.
        self.assertIn("or setting in motion work that ends", md)
        self.assertIn("post-PR or review hook", md)
        # Honesty: declared policy, not runtime enforcement.
        self.assertIn("no hook in this\nharness fires a gate automatically", md)

    def test_runless_gate_renders_nothing_and_stays_unsatisfied(self):
        _, out = self.render()
        md = (self.claude / "CLAUDE.md").read_text()
        self.assertNotIn("second-opinion", md)
        self.assertIn("gates.second-opinion — no `run` and no native surface; unsatisfied", out)

    def test_rerender_of_unchanged_profile_is_byte_identical(self):
        self.render()
        md1 = (self.claude / "CLAUDE.md").read_text()
        rc, _ = self.render()
        self.assertEqual(rc, 0)
        self.assertEqual(md1, (self.claude / "CLAUDE.md").read_text())

    def test_removing_run_gate_unrenders_exactly_that_section(self):
        self.render()
        md_with = (self.claude / "CLAUDE.md").read_text()
        ctx = adapter.ch.build_context("/nowhere", "testhost", "none")
        effective, errors, _, _ = adapter.ch.resolve_profile(self.profile, ctx)
        self.assertFalse(errors)
        section = adapter.gates_section(effective, self.profile)
        self.assertIn(section, md_with)

        toml = PROFILE_TOML.replace(RUN_GATE_BLOCK, "")
        self.assertNotIn("cross-vendor-review", toml)
        write(self.profile / "chevaline.toml", toml)
        rc, _ = self.render()
        self.assertEqual(rc, 0)
        md_without = (self.claude / "CLAUDE.md").read_text()
        # Exactly the gates section is gone; every other byte survives.
        self.assertEqual(md_without, md_with.replace("\n" + section, "", 1))
        self.assertNotIn("# Gates", md_without)
        self.assertIn("Instruction A", md_without)
        self.assertIn("# Budget (declared policy)", md_without)

    def test_run_gate_still_reported_skipped_reworded(self):
        _, out = self.render()
        # Task 0002 rewording: the report acknowledges the prose surface
        # and still refuses to claim native enforcement.
        self.assertIn("gates.cross-vendor-review", out)
        # Phrases unique to the gates line — the budget NOT ENFORCED line
        # shares its "standing prose" opener, so asserting on that alone
        # would not prove the gates rewording is present.
        self.assertIn(
            "a directive, conditioned on the compose mode, for its script "
            "and the gate's `on` action",
            out,
        )
        self.assertIn("still not natively enforced on this harness", out)
        self.assertIn("the session reading the prose, not the harness, carries the gate", out)


class TestGateComposeModes(AdapterCase):
    """PR #3 review, P1: the rendered directive is conditioned on the gate's
    `compose` mode. Only `layer` means run it unconditionally — an
    unconditional line would send a session to run a `defer` gate the
    project's own convention should have displaced, and to run an `insist`
    gate straight through the conflict it exists to stop at (SPEC §2.2)."""

    def render_with_compose(self, mode: str) -> str:
        block = RUN_GATE_BLOCK.replace('compose = "layer"', f'compose = "{mode}"')
        write(self.profile / "chevaline.toml", PROFILE_TOML.replace(RUN_GATE_BLOCK, block))
        rc, _ = self.render()
        self.assertEqual(rc, 0)
        return (self.claude / "CLAUDE.md").read_text()

    def test_layer_directs_an_unconditional_run(self):
        md = self.render_with_compose("layer")
        self.assertIn(f"Run `{self.profile / 'scripts/review.py'}`. Compose `layer`:", md)
        self.assertIn("a project gate on `merge` does not excuse skipping this one", md)

    def test_defer_runs_only_where_the_project_has_no_gate(self):
        md = self.render_with_compose("defer")
        self.assertIn("Compose `defer`: run", md)
        self.assertIn("only where the project has no gate of its own on `merge`", md)
        self.assertIn("this one is not run", md)
        # The unconditional form must be gone, not merely accompanied.
        self.assertNotIn(f"Run `{self.profile / 'scripts/review.py'}`. Compose", md)

    def test_insist_stops_on_a_conflict_rather_than_yielding_or_overriding(self):
        md = self.render_with_compose("insist")
        self.assertIn("Compose `insist`: run", md)
        self.assertIn("do not quietly yield to the project and do not run over it", md)
        self.assertIn("stop, surface the conflict, and wait", md)

    def test_unknown_mode_renders_as_unevaluable_and_withholds_the_run(self):
        # The validator rejects a mode outside layer/defer/insist for a gate,
        # so this state means the profile outran the adapter — a mode from a
        # newer spec version. gates_section is called directly because the
        # resolver would refuse the profile before rendering.
        effective = {
            "gates": [
                {
                    "id": "future-gate",
                    "on": "merge",
                    "compose": "quorum",
                    "run": "scripts/review.py",
                }
            ]
        }
        section = adapter.gates_section(effective, self.profile)
        self.assertIn("Compose `quorum` is not a mode this adapter can evaluate", section)
        self.assertIn("Do not run", section)
        self.assertNotIn(f"Run `{self.profile / 'scripts/review.py'}`. Compose", section)


class TestIdempotence(AdapterCase):
    def test_second_render_changes_nothing(self):
        self.render()
        md1 = (self.claude / "CLAUDE.md").read_text()
        s1 = (self.claude / "settings.json").read_text()
        side1 = (self.claude / adapter.SIDECAR_NAME).read_text()
        rc, _ = self.render()
        self.assertEqual(rc, 0)
        self.assertEqual(md1, (self.claude / "CLAUDE.md").read_text())
        self.assertEqual(s1, (self.claude / "settings.json").read_text())
        self.assertEqual(side1, (self.claude / adapter.SIDECAR_NAME).read_text())


class TestNonClobbering(AdapterCase):
    def test_hand_written_model_wins_and_is_reported(self):
        write(self.claude / "settings.json", json.dumps({"model": "hand-picked"}))
        rc, out = self.render()
        self.assertEqual(rc, 0)
        self.assertEqual(self.settings()["model"], "hand-picked")
        self.assertNotIn("model", self.sidecar()["owned"]["scalars"])
        self.assertIn("hand-picked", out)  # conflict is loud, not silent

    def test_hand_written_prose_outside_markers_survives(self):
        write(self.claude / "CLAUDE.md", "My own notes.\n")
        self.render()
        md = (self.claude / "CLAUDE.md").read_text()
        self.assertTrue(md.startswith("My own notes."))
        self.assertIn(adapter.BEGIN_MARKER, md)
        # Re-render still preserves it.
        self.render()
        self.assertTrue((self.claude / "CLAUDE.md").read_text().startswith("My own notes."))

    def test_hand_added_permission_entry_survives_rerender(self):
        self.render()
        s = self.settings()
        s["permissions"]["allow"].append("Bash(make:*)")
        (self.claude / "settings.json").write_text(json.dumps(s))
        self.render()
        self.assertIn("Bash(make:*)", self.settings()["permissions"]["allow"])

    def test_unrelated_settings_keys_untouched(self):
        write(
            self.claude / "settings.json",
            json.dumps({"theme": "dark", "custom": {"a": 1}}),
        )
        self.render()
        s = self.settings()
        self.assertEqual(s["theme"], "dark")
        self.assertEqual(s["custom"], {"a": 1})

    def test_damaged_marker_pair_refuses(self):
        write(self.claude / "CLAUDE.md", f"notes\n{adapter.BEGIN_MARKER}\nno end marker\n")
        with self.assertRaises(SystemExit):
            self.render()


class TestProfileChangeReRender(AdapterCase):
    def test_removed_authority_class_unrenders_its_entries(self):
        self.render()
        self.assertIn("Bash(git push:*)", self.settings()["permissions"]["ask"])
        toml = PROFILE_TOML.replace('"vcs.push" = "approval"\n', "")
        write(self.profile / "chevaline.toml", toml)
        self.render()
        s = self.settings()
        self.assertNotIn("Bash(git push:*)", s.get("permissions", {}).get("ask", []))

    def test_removed_model_tier_unrenders_owned_scalar(self):
        self.render()
        self.assertEqual(self.settings()["model"], "standard-model")
        toml = PROFILE_TOML.replace('standard = "standard-model"\n', "")
        write(self.profile / "chevaline.toml", toml)
        self.render()
        self.assertNotIn("model", self.settings())


class TestHarnessGating(AdapterCase):
    def test_declines_when_not_preferred(self):
        toml = PROFILE_TOML.replace(
            'prefer = ["claude-code", "codex"]', 'prefer = ["codex"]'
        )
        write(self.profile / "chevaline.toml", toml)
        rc, _ = self.render()
        self.assertEqual(rc, 1)
        self.assertFalse((self.claude / "CLAUDE.md").exists())


class TestDryRun(AdapterCase):
    def test_dry_run_writes_nothing(self):
        rc, out = self.render("--dry-run")
        self.assertEqual(rc, 0)
        self.assertIn("DRY RUN", out)
        self.assertFalse((self.claude / "CLAUDE.md").exists())
        self.assertFalse((self.claude / "settings.json").exists())


class TestInvalidProfileRefused(AdapterCase):
    def test_invalid_profile_renders_nothing(self):
        # Strip the aggregate limit → invalid per SPEC §3.5.
        toml = PROFILE_TOML.replace('{ scope = "*", window = "session", amount = 10, unit = "USD" },', "")
        write(self.profile / "chevaline.toml", toml)
        rc, _ = self.render()
        self.assertEqual(rc, 1)
        self.assertFalse((self.claude / "CLAUDE.md").exists())


def _git(*args: str, cwd: Path) -> str:
    result = subprocess.run(
        ["git", "-c", "user.email=t@example.invalid", "-c", "user.name=t", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise AssertionError(f"git {args} failed: {result.stderr}")
    return result.stdout.strip()


PLUGIN_PROFILE_TEMPLATE = """
spec = "0.3"

[harnesses]
prefer = ["claude-code"]

[budget]
on_exceed = "halt"
limits = [ {{ scope = "*", window = "session", amount = 1, unit = "USD" }} ]

[authority]
default = "reported"

[authority.actions]
"exec.install" = "{install_level}"

{plugins}
"""


class PluginCase(unittest.TestCase):
    """Shared fixture: a plugin source repo carrying claude-code packaging,
    a plugin store, and a recording stub standing in for the claude CLI."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.profile = root / "profile"
        self.claude = root / "claude"
        self.store = root / "store"

        self.plugin_repo = root / "pony-src"
        self.plugin_repo.mkdir(parents=True)
        write(
            self.plugin_repo / ".claude-plugin" / "marketplace.json",
            json.dumps(
                {"name": "pony", "plugins": [{"name": "pony", "source": "./"}]}
            ),
        )
        write(self.plugin_repo / "AGENTS.md", "# rules\n")
        _git("init", "--quiet", cwd=self.plugin_repo)
        _git("add", "-A", cwd=self.plugin_repo)
        _git("commit", "--quiet", "-m", "initial", cwd=self.plugin_repo)
        self.pin = _git("rev-parse", "HEAD", cwd=self.plugin_repo)

        self.cli_log = root / "cli.log"
        self.cli = root / "fake-claude"
        self.cli.write_text(
            "#!/bin/sh\n"
            f'echo "$@" >> "{self.cli_log}"\n'
            "exit 0\n"
        )
        self.cli.chmod(self.cli.stat().st_mode | stat.S_IXUSR)

    def tearDown(self):
        self.tmp.cleanup()

    def write_profile(self, install_level: str = "approval", plugins: str | None = None):
        if plugins is None:
            plugins = (
                "[[plugins]]\n"
                'id = "pony"\n'
                f'source = "{self.plugin_repo}"\n'
                f'pin = "{self.pin}"\n'
            )
        write(
            self.profile / "chevaline.toml",
            PLUGIN_PROFILE_TEMPLATE.format(install_level=install_level, plugins=plugins),
        )

    def render(self, *extra: str) -> tuple[int, str]:
        argv = [
            "render",
            str(self.profile),
            "--claude-dir", str(self.claude),
            "--plugin-store", str(self.store),
            "--claude-cli", str(self.cli),
            "--cwd", "/nowhere",
            "--hostname", "testhost",
            "--git-org", "none",
            *extra,
        ]
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = adapter.main(argv)
        return rc, buf.getvalue()

    def cli_calls(self) -> list[str]:
        if not self.cli_log.is_file():
            return []
        return self.cli_log.read_text().strip().splitlines()

    def settings(self) -> dict:
        return json.loads((self.claude / "settings.json").read_text())

    def sidecar(self) -> dict:
        return json.loads((self.claude / adapter.SIDECAR_NAME).read_text())


class TestPluginAuthorityGating(PluginCase):
    def test_approval_without_flag_skips_and_fetches_nothing(self):
        self.write_profile(install_level="approval")
        rc, out = self.render()
        self.assertEqual(rc, 0)
        self.assertIn("--allow-install", out)
        self.assertFalse(self.store.exists())
        self.assertEqual(self.cli_calls(), [])

    def test_approval_with_flag_installs(self):
        self.write_profile(install_level="approval")
        rc, out = self.render("--allow-install")
        self.assertEqual(rc, 0, out)
        self.assertTrue((self.store / "pony" / self.pin / "AGENTS.md").is_file())
        self.assertIn("authorized by --allow-install", out)

    def test_reported_level_installs_and_says_so(self):
        self.write_profile(install_level="reported")
        rc, out = self.render()
        self.assertEqual(rc, 0, out)
        self.assertIn("'reported': saying so", out)


class TestPluginRender(PluginCase):
    def test_registers_marketplace_and_owns_enablement(self):
        self.write_profile(install_level="silent")
        rc, out = self.render()
        self.assertEqual(rc, 0, out)
        checkout = self.store / "pony" / self.pin
        calls = self.cli_calls()
        self.assertEqual(calls, [f"plugin marketplace add {checkout}"])
        self.assertIs(self.settings()["enabledPlugins"]["pony@pony"], True)
        side = self.sidecar()
        self.assertIn("enabledPlugins.pony@pony", side["owned"]["scalars"])
        self.assertEqual(side["plugins"]["pony"]["identity"], "pony@pony")
        self.assertEqual(side["plugins"]["pony"]["pin"], self.pin)

    def test_launcher_directive_prose_renders(self):
        self.write_profile(install_level="silent")
        rc, _ = self.render()
        self.assertEqual(rc, 0)
        md = (self.claude / "CLAUDE.md").read_text()
        self.assertIn("# Plugins (declared policy)", md)
        self.assertIn(str(self.store / "pony" / self.pin), md)
        self.assertIn("SDK sessions", md)

    def test_second_render_is_idempotent_and_calls_no_cli(self):
        self.write_profile(install_level="silent")
        self.render()
        first_settings = (self.claude / "settings.json").read_bytes()
        calls_before = self.cli_calls()
        rc, out = self.render()
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.cli_calls(), calls_before)
        self.assertEqual((self.claude / "settings.json").read_bytes(), first_settings)
        self.assertIn("already registered at this pin", out)

    def test_dropping_the_plugin_unrenders_and_removes_marketplace(self):
        self.write_profile(install_level="silent")
        self.render()
        self.write_profile(install_level="silent", plugins="")
        rc, out = self.render()
        self.assertEqual(rc, 0, out)
        self.assertNotIn("enabledPlugins", self.settings())
        self.assertNotIn("plugins", self.sidecar())
        self.assertIn("plugin marketplace remove pony", self.cli_calls())

    def test_missing_claude_packaging_is_reported_not_guessed(self):
        # A source with no .claude-plugin/marketplace.json: nothing to register.
        for path in [".claude-plugin/marketplace.json"]:
            (self.plugin_repo / path).unlink()
        _git("add", "-A", cwd=self.plugin_repo)
        _git("commit", "--quiet", "-m", "strip packaging", cwd=self.plugin_repo)
        self.pin = _git("rev-parse", "HEAD", cwd=self.plugin_repo)
        self.write_profile(install_level="silent")
        rc, out = self.render()
        self.assertEqual(rc, 0, out)
        self.assertIn("no claude-code packaging", out)
        self.assertEqual(self.cli_calls(), [])
        self.assertNotIn("enabledPlugins", self.settings())

    def test_dry_run_touches_nothing(self):
        self.write_profile(install_level="silent")
        rc, out = self.render("--dry-run")
        self.assertEqual(rc, 0, out)
        self.assertIn("DRY RUN", out)
        self.assertFalse(self.store.exists())
        self.assertEqual(self.cli_calls(), [])
        self.assertFalse((self.claude / "settings.json").exists())

    def test_harness_filter_excludes_this_adapter(self):
        self.write_profile(
            install_level="silent",
            plugins=(
                "[[plugins]]\n"
                'id = "pony"\n'
                f'source = "{self.plugin_repo}"\n'
                f'pin = "{self.pin}"\n'
                'harnesses = ["opencode"]\n'
            ),
        )
        rc, out = self.render()
        self.assertEqual(rc, 0, out)
        self.assertFalse(self.store.exists())
        self.assertNotIn("enabledPlugins", self.settings())
        self.assertIn("filtered out", out)


if __name__ == "__main__":
    unittest.main()
