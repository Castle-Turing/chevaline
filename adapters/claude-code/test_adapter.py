"""Tests for adapters/claude-code/adapter.py. Stdlib unittest only.

Fixtures are written to temp dirs at test time; nothing is added to the repo
and nothing touches a real ~/.claude.
"""

from __future__ import annotations

import io
import json
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
        self.assertIn("silently wins", md)
        # The declared environment override, with its selector, rendered
        # even though this render's cwd does not match it.
        self.assertIn("under `/emceeland*` (environment `emcee`)", md)
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
        region = adapter.render_region(effective, raw, self.profile, adapter.Report())
        md_without = adapter.splice_claude_md(md_with, region)
        # Exactly the budget section is gone; every other byte survives.
        self.assertEqual(md_without, md_with.replace("\n" + section, "", 1))
        self.assertNotIn("# Budget", md_without)
        self.assertIn("Instruction A", md_without)
        self.assertIn("Standing authority expectations", md_without)

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


if __name__ == "__main__":
    unittest.main()
