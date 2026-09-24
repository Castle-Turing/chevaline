"""Tests for tools/plugstore.py. Stdlib unittest only.

Fixture plugin repos are real local git repositories built in temp dirs, so
materialization is exercised end to end with no network access.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import plugstore  # noqa: E402


def git(*args: str, cwd: Path) -> str:
    result = subprocess.run(
        ["git", "-c", "user.email=t@example.invalid", "-c", "user.name=t", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise AssertionError(f"git {args} failed: {result.stderr}")
    return result.stdout.strip()


def make_plugin_repo(root: Path) -> tuple[Path, str]:
    repo = root / "plugin-src"
    repo.mkdir()
    git("init", "--quiet", cwd=repo)
    (repo / "AGENTS.md").write_text("# rules\n")
    git("add", "-A", cwd=repo)
    git("commit", "--quiet", "-m", "initial", cwd=repo)
    sha = git("rev-parse", "HEAD", cwd=repo)
    return repo, sha


class PlugstoreCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.repo, self.sha = make_plugin_repo(self.root)
        self.store = self.root / "store"

    def tearDown(self):
        self.tmp.cleanup()


class TestMaterialize(PlugstoreCase):
    def test_first_materialization_fetches_and_verifies(self):
        dest, fetched = plugstore.materialize("p", str(self.repo), self.sha, self.store)
        self.assertTrue(fetched)
        self.assertEqual(dest, self.store / "p" / self.sha)
        self.assertTrue((dest / "AGENTS.md").is_file())

    def test_second_materialization_is_idempotent_and_offline(self):
        plugstore.materialize("p", str(self.repo), self.sha, self.store)
        # A second call must not need the source at all.
        dest, fetched = plugstore.materialize(
            "p", str(self.root / "does-not-exist"), self.sha, self.store
        )
        self.assertFalse(fetched)
        self.assertEqual(dest, self.store / "p" / self.sha)

    def test_unknown_pin_fails_and_leaves_no_husk(self):
        bogus = "0" * 40
        with self.assertRaises(plugstore.PlugstoreError):
            plugstore.materialize("p", str(self.repo), bogus, self.store)
        self.assertFalse((self.store / "p" / bogus).exists())

    def test_git_launch_failure_is_a_plugstore_error(self):
        import subprocess as sp

        real_run = sp.run

        def broken_run(argv, **kwargs):
            if argv and argv[0] == "git" and "clone" in argv:
                raise OSError("git not found")
            return real_run(argv, **kwargs)

        sp.run = broken_run
        try:
            with self.assertRaises(plugstore.PlugstoreError):
                plugstore.materialize("p", str(self.repo), self.sha, self.store)
        finally:
            sp.run = real_run

    def test_escaping_plugin_id_is_refused(self):
        with self.assertRaises(plugstore.PlugstoreError):
            plugstore.materialize("../evil", str(self.repo), self.sha, self.store)

    def test_resolve_source_is_profile_relative(self):
        profile = self.root / "profile"
        self.assertEqual(
            plugstore.resolve_source("plugins/local", profile),
            str(profile / "plugins/local"),
        )
        self.assertEqual(plugstore.resolve_source("/abs/path", profile), "/abs/path")
        self.assertEqual(
            plugstore.resolve_source("https://example.invalid/r", profile),
            "https://example.invalid/r",
        )
        self.assertEqual(
            plugstore.resolve_source("git@example.invalid:o/r.git", profile),
            "git@example.invalid:o/r.git",
        )

    def test_tampered_store_entry_is_refused(self):
        dest, _ = plugstore.materialize("p", str(self.repo), self.sha, self.store)
        (dest / "extra.txt").write_text("tamper\n")
        git("add", "-A", cwd=dest)
        git("commit", "--quiet", "-m", "tamper", cwd=dest)
        with self.assertRaises(plugstore.PlugstoreError):
            plugstore.materialize("p", str(self.repo), self.sha, self.store)


if __name__ == "__main__":
    unittest.main()
