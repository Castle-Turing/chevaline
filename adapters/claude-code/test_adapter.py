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

    def render(self, *extra: str) -> tuple[int, str]:
        argv = [
            "render",
            str(self.profile),
            "--claude-dir",
            str(self.claude),
            "--cwd",
            "/nowhere",
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

    def test_gate_and_sessions_reported_skipped(self):
        _, out = self.render()
        self.assertIn("gates.second-opinion", out)
        self.assertIn("sessions.isolation", out)


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
