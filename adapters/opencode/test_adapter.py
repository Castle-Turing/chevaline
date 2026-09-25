"""Tests for adapters/opencode/adapter.py. Stdlib unittest only.

Fixtures are written to temp dirs at test time; nothing is added to the
repo and nothing touches a real ~/.config/opencode. Plugin tests build a
real local git repository carrying OpenCode packaging, so materialization
is exercised end to end with no network access.
"""

from __future__ import annotations

import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import adapter  # noqa: E402


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


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


PROFILE_TEMPLATE = """
spec = "0.3"

[harnesses]
prefer = ["claude-code", "opencode"]

[budget]
on_exceed = "halt"
limits = [ {{ scope = "*", window = "session", amount = 1, unit = "USD" }} ]

[authority]
default = "reported"

[authority.actions]
"exec.install" = "{install_level}"

[[instructions]]
path = "instructions/a.md"

[[instructions]]
path = "instructions/claude-only.md"
harnesses = ["claude-code"]

{plugins}
"""


class OpencodeCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.profile = root / "profile"
        self.opencode = root / "opencode"
        self.store = root / "store"
        write(self.profile / "instructions/a.md", "# Instruction A\n\nBody A.\n")
        write(self.profile / "instructions/claude-only.md", "# Claude only\n")

        self.plugin_repo = root / "pony-src"
        self.plugin_repo.mkdir(parents=True)
        write(self.plugin_repo / ".opencode" / "plugins" / "pony.mjs", "// entry\n")
        write(self.plugin_repo / "AGENTS.md", "# rules\n")
        _git("init", "--quiet", cwd=self.plugin_repo)
        _git("add", "-A", cwd=self.plugin_repo)
        _git("commit", "--quiet", "-m", "initial", cwd=self.plugin_repo)
        self.pin = _git("rev-parse", "HEAD", cwd=self.plugin_repo)

    def tearDown(self):
        self.tmp.cleanup()

    def write_profile(self, install_level: str = "silent", plugins: str | None = None):
        if plugins is None:
            plugins = (
                "[[plugins]]\n"
                'id = "pony"\n'
                f'source = "{self.plugin_repo}"\n'
                f'pin = "{self.pin}"\n'
            )
        write(
            self.profile / "chevaline.toml",
            PROFILE_TEMPLATE.format(install_level=install_level, plugins=plugins),
        )

    def render(self, *extra: str) -> tuple[int, str]:
        argv = [
            "render",
            str(self.profile),
            "--opencode-dir", str(self.opencode),
            "--plugin-store", str(self.store),
            "--cwd", "/nowhere",
            "--hostname", "testhost",
            "--git-org", "none",
            *extra,
        ]
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = adapter.main(argv)
        return rc, buf.getvalue()

    def config(self) -> dict:
        return json.loads((self.opencode / "opencode.json").read_text())


class TestInstructions(OpencodeCase):
    def test_renders_marker_region_with_harness_filter(self):
        self.write_profile()
        rc, _ = self.render()
        self.assertEqual(rc, 0)
        md = (self.opencode / "AGENTS.md").read_text()
        self.assertIn(adapter.BEGIN_MARKER, md)
        self.assertIn("Instruction A", md)
        self.assertNotIn("Claude only", md)

    def test_text_outside_markers_survives(self):
        self.write_profile()
        write(self.opencode / "AGENTS.md", "# Mine\n\nhands off\n")
        rc, _ = self.render()
        self.assertEqual(rc, 0)
        md = (self.opencode / "AGENTS.md").read_text()
        self.assertIn("hands off", md)
        self.assertIn("Instruction A", md)


class TestPlugins(OpencodeCase):
    def test_adds_absolute_mjs_entry_and_owns_it(self):
        self.write_profile()
        rc, out = self.render()
        self.assertEqual(rc, 0, out)
        entry = str(self.store / "pony" / self.pin / ".opencode" / "plugins" / "pony.mjs")
        self.assertEqual(self.config()["plugin"], [entry])
        sidecar = json.loads((self.opencode / adapter.SIDECAR_NAME).read_text())
        self.assertEqual(sidecar["owned"]["plugin"], [entry])

    def test_approval_without_flag_fetches_nothing(self):
        self.write_profile(install_level="approval")
        rc, out = self.render()
        self.assertEqual(rc, 0)
        self.assertIn("--allow-install", out)
        self.assertFalse(self.store.exists())
        self.assertNotIn("plugin", self.config())

    def test_hand_written_entries_survive(self):
        self.write_profile()
        write(self.opencode / "opencode.json", json.dumps({"plugin": ["@vendor/theirs"]}))
        rc, _ = self.render()
        self.assertEqual(rc, 0)
        plugin = self.config()["plugin"]
        self.assertIn("@vendor/theirs", plugin)
        self.assertEqual(len(plugin), 2)

    def test_second_render_is_byte_identical(self):
        self.write_profile()
        self.render()
        first = (self.opencode / "opencode.json").read_bytes()
        rc, _ = self.render()
        self.assertEqual(rc, 0)
        self.assertEqual((self.opencode / "opencode.json").read_bytes(), first)

    def test_dropping_the_plugin_unrenders_only_ours(self):
        self.write_profile()
        write(self.opencode / "opencode.json", json.dumps({"plugin": ["@vendor/theirs"]}))
        self.render()
        self.write_profile(plugins="")
        rc, _ = self.render()
        self.assertEqual(rc, 0)
        self.assertEqual(self.config()["plugin"], ["@vendor/theirs"])

    def test_corrupted_sidecar_target_cannot_redirect_writes(self):
        outside = Path(self.tmp.name) / "outside.json"
        outside.write_text("{}")
        write(
            self.opencode / adapter.SIDECAR_NAME,
            json.dumps({"owned": {"plugin": []}, "target": "../outside.json"}),
        )
        self.write_profile()
        rc, out = self.render()
        self.assertEqual(rc, 0, out)
        self.assertEqual(outside.read_text(), "{}")
        self.assertIn("plugin", self.config())  # wrote opencode.json instead

    def test_config_target_stays_put_when_jsonc_appears_later(self):
        self.write_profile()
        self.render()  # writes opencode.json and records it as the target
        write(self.opencode / "opencode.jsonc", "{}")
        self.write_profile(plugins="")
        rc, out = self.render()
        self.assertEqual(rc, 0, out)
        self.assertIn("config target stays opencode.json", out)
        # The owned entry was removed from the file it was written to.
        self.assertNotIn("plugin", self.config())
        self.assertEqual(
            json.loads((self.opencode / "opencode.jsonc").read_text()), {}
        )

    def test_non_object_config_is_declined_loudly(self):
        self.write_profile()
        write(self.opencode / "opencode.json", "[]")
        rc, _ = self.render()
        self.assertEqual(rc, 1)
        self.assertFalse(self.store.exists())
        self.assertEqual((self.opencode / "opencode.json").read_text(), "[]")

    def test_jsonc_with_comments_is_declined_loudly(self):
        self.write_profile()
        write(
            self.opencode / "opencode.jsonc",
            '// my comments are load-bearing\n{"plugin": []}\n',
        )
        rc, _ = self.render()
        self.assertEqual(rc, 1)

    def test_js_and_ts_entry_points_are_recognized(self):
        (self.plugin_repo / ".opencode" / "plugins" / "pony.mjs").unlink()
        write(self.plugin_repo / ".opencode" / "plugins" / "pony.js", "// entry\n")
        write(self.plugin_repo / ".opencode" / "plugins" / "extra.ts", "// entry\n")
        write(self.plugin_repo / ".opencode" / "plugins" / "helper.cjs", "// helper\n")
        _git("add", "-A", cwd=self.plugin_repo)
        _git("commit", "--quiet", "-m", "js entry", cwd=self.plugin_repo)
        self.pin = _git("rev-parse", "HEAD", cwd=self.plugin_repo)
        self.write_profile()
        rc, out = self.render()
        self.assertEqual(rc, 0, out)
        base = self.store / "pony" / self.pin / ".opencode" / "plugins"
        self.assertEqual(
            self.config()["plugin"],
            [str(base / "extra.ts"), str(base / "pony.js")],
        )

    def test_relative_store_override_still_writes_absolute_entries(self):
        import os

        self.write_profile()
        before = os.getcwd()
        os.chdir(self.tmp.name)
        try:
            rc, out = self.render("--plugin-store", "rel-store")
        finally:
            os.chdir(before)
        self.assertEqual(rc, 0, out)
        entry = self.config()["plugin"][0]
        self.assertTrue(Path(entry).is_absolute(), entry)
        self.assertTrue(entry.startswith(self.tmp.name), entry)

    def test_singular_plugin_directory_is_recognized(self):
        (self.plugin_repo / ".opencode" / "plugins" / "pony.mjs").unlink()
        write(self.plugin_repo / ".opencode" / "plugin" / "pony.mjs", "// entry\n")
        _git("add", "-A", cwd=self.plugin_repo)
        _git("commit", "--quiet", "-m", "singular dir", cwd=self.plugin_repo)
        self.pin = _git("rev-parse", "HEAD", cwd=self.plugin_repo)
        self.write_profile()
        rc, out = self.render()
        self.assertEqual(rc, 0, out)
        entry = str(self.store / "pony" / self.pin / ".opencode" / "plugin" / "pony.mjs")
        self.assertEqual(self.config()["plugin"], [entry])

    def test_non_layer_compose_is_reported_not_layered(self):
        self.write_profile(
            plugins=(
                "[[plugins]]\n"
                'id = "pony"\n'
                f'source = "{self.plugin_repo}"\n'
                f'pin = "{self.pin}"\n'
                'compose = "insist"\n'
            ),
        )
        rc, out = self.render()
        self.assertEqual(rc, 0, out)
        self.assertIn("non-layer mode cannot be honored natively", out)
        self.assertFalse(self.store.exists())
        self.assertNotIn("plugin", self.config())

    def test_symlinked_entry_point_escaping_checkout_is_refused(self):
        outside = self.plugin_repo.parent / "outside.mjs"
        outside.write_text("// mutable\n")
        (self.plugin_repo / ".opencode" / "plugins" / "evil.mjs").symlink_to(
            "../../../outside.mjs"
        )
        _git("add", "-A", cwd=self.plugin_repo)
        _git("commit", "--quiet", "-m", "symlink entry", cwd=self.plugin_repo)
        self.pin = _git("rev-parse", "HEAD", cwd=self.plugin_repo)
        self.write_profile()
        rc, out = self.render()
        self.assertEqual(rc, 1)
        self.assertIn("resolve outside the pinned checkout", out)

    def test_non_list_plugin_value_is_a_conflict_not_raw_material(self):
        write(self.opencode / "opencode.json", json.dumps({"plugin": "not-a-list"}))
        self.write_profile()
        rc, out = self.render()
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.config()["plugin"], "not-a-list")
        self.assertIn("-shaped, not", out)

    def test_dry_run_on_a_new_pin_does_not_project_removal(self):
        self.write_profile()
        self.render()
        write(self.plugin_repo / "CHANGED.md", "new content\n")
        _git("add", "-A", cwd=self.plugin_repo)
        _git("commit", "--quiet", "-m", "new pin", cwd=self.plugin_repo)
        self.pin = _git("rev-parse", "HEAD", cwd=self.plugin_repo)
        old_entry = self.config()["plugin"][0]
        self.write_profile()
        rc, out = self.render("--dry-run")
        self.assertEqual(rc, 0, out)
        self.assertNotIn("removed formerly-owned", out)
        self.assertIn("post-fetch state unknown", out)
        self.assertEqual(self.config()["plugin"], [old_entry])

    def test_no_opencode_packaging_is_reported(self):
        (self.plugin_repo / ".opencode" / "plugins" / "pony.mjs").unlink()
        _git("add", "-A", cwd=self.plugin_repo)
        _git("commit", "--quiet", "-m", "strip packaging", cwd=self.plugin_repo)
        self.pin = _git("rev-parse", "HEAD", cwd=self.plugin_repo)
        self.write_profile()
        rc, out = self.render()
        self.assertEqual(rc, 0, out)
        self.assertIn("no OpenCode packaging", out)
        self.assertNotIn("plugin", self.config())


class TestHarnessGating(OpencodeCase):
    def test_declines_when_prefer_excludes_opencode(self):
        self.write_profile()
        toml = (self.profile / "chevaline.toml").read_text()
        toml = toml.replace('prefer = ["claude-code", "opencode"]', 'prefer = ["claude-code"]')
        write(self.profile / "chevaline.toml", toml)
        rc, _ = self.render()
        self.assertEqual(rc, 1)


if __name__ == "__main__":
    unittest.main()
