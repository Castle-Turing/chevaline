"""Tests for tools/chevaline.py. Stdlib unittest only.

Fixtures are written to temp dirs at test time; nothing is added to the repo.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import chevaline as ch  # noqa: E402


REPO_ROOT = Path(__file__).resolve().parent.parent
ADA_DIR = REPO_ROOT / "examples" / "ada"


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def make_ctx(cwd="/nowhere", hostname="testhost", git_org=None):
    return ch.Context(cwd=cwd, hostname=hostname, git_org=git_org)


class TestValidSimpleProfile(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        write(
            self.dir / "chevaline.toml",
            """
spec = "0.2"

[resident]
name = "Test Resident"

[models]
cheap = "cheap-model"
standard = "standard-model"
deep = "deep-model"

[budget]
on_exceed = "halt"
limits = [
  { scope = "*", window = "day", amount = 10, unit = "USD" },
]

[sessions]
isolation = "worktree"
compose = "defer"
""",
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_validates_cleanly(self):
        errors, warnings, raw = ch.validate_profile(self.dir)
        self.assertEqual(errors, [])
        self.assertIsNotNone(raw)

    def test_resolves_to_base_when_no_environments(self):
        ctx = make_ctx()
        effective, errors, warnings, explain = ch.resolve_profile(self.dir, ctx)
        self.assertEqual(errors, [])
        self.assertEqual(effective["models"]["cheap"], "cheap-model")
        self.assertEqual(effective["budget"]["limits"][0]["unit"], "USD")
        self.assertNotIn("environment", effective)
        self.assertEqual(explain["environments"], [])
        self.assertEqual(explain["sources"], {})


class TestAdaExample(unittest.TestCase):
    def test_ada_validates_cleanly(self):
        errors, warnings, raw = ch.validate_profile(ADA_DIR)
        self.assertEqual(errors, [], msg=f"unexpected errors: {errors}")
        self.assertIsNotNone(raw)

    def test_ada_resolves_under_matching_work_context(self):
        ctx = make_ctx(cwd="/Users/ada/work/somerepo", git_org="acme")
        # `path` selector uses "~/work/**" — expand ~ to match against HOME.
        import os

        home = os.path.expanduser("~")
        ctx = make_ctx(cwd=f"{home}/work/somerepo", git_org="acme")
        effective, errors, warnings, explain = ch.resolve_profile(ADA_DIR, ctx)
        self.assertEqual(errors, [])
        # Work environment should have applied: token budget, work models.
        self.assertEqual(effective["models"]["cheap"], "qwen2.5-coder")
        self.assertEqual(effective["models"]["deep"], "llama-3.3-405b")
        self.assertEqual(effective["budget"]["limits"][0]["unit"], "tokens")
        self.assertEqual(effective["budget"]["limits"][0]["amount"], 5_000_000)
        matched = [e for e in explain["environments"] if e["matched"]]
        self.assertEqual([m["name"] for m in matched], ["work"])
        self.assertEqual(explain["sources"]["models.cheap"], "work")

    def test_ada_resolves_under_nonmatching_context(self):
        ctx = make_ctx(cwd="/somewhere/else", hostname="personal-laptop", git_org=None)
        effective, errors, warnings, explain = ch.resolve_profile(ADA_DIR, ctx)
        self.assertEqual(errors, [])
        # Base (personal) config should be in effect.
        self.assertEqual(effective["models"]["cheap"], "claude-haiku-4-5")
        self.assertEqual(effective["budget"]["limits"][0]["unit"], "USD")
        matched = [e for e in explain["environments"] if e["matched"]]
        self.assertEqual(matched, [])
        self.assertEqual(explain["sources"], {})


class TestRecursiveTableMerge(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        write(
            self.dir / "chevaline.toml",
            """
spec = "0.2"

[models]
cheap = "base-cheap"
standard = "base-standard"
deep = "base-deep"

[budget]
limits = [ { scope = "*", window = "day", amount = 10, unit = "USD" } ]

[environment.work]
when.hostname = "work-machine"

[environment.work.models]
cheap = "work-cheap"
""",
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_only_cheap_overridden_rest_inherited(self):
        ctx = make_ctx(hostname="work-machine")
        effective, errors, warnings, explain = ch.resolve_profile(self.dir, ctx)
        self.assertEqual(errors, [])
        self.assertEqual(effective["models"]["cheap"], "work-cheap")
        self.assertEqual(effective["models"]["standard"], "base-standard")
        self.assertEqual(effective["models"]["deep"], "base-deep")
        self.assertEqual(explain["sources"]["models.cheap"], "work")
        self.assertNotIn("models.standard", explain["sources"])
        self.assertNotIn("models.deep", explain["sources"])


class TestArrayWholesaleReplacement(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        write(self.dir / "a.md", "a")
        write(self.dir / "b.md", "b")
        write(
            self.dir / "chevaline.toml",
            """
spec = "0.2"

[budget]
limits = [ { scope = "*", window = "day", amount = 10, unit = "USD" } ]

[[instructions]]
path = "a.md"

[environment.work]
when.hostname = "work-machine"

[[environment.work.instructions]]
path = "b.md"
""",
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_environment_instructions_replace_not_append(self):
        ctx = make_ctx(hostname="work-machine")
        effective, errors, warnings, explain = ch.resolve_profile(self.dir, ctx)
        self.assertEqual(errors, [])
        paths = [i["path"] for i in effective["instructions"]]
        self.assertEqual(paths, ["b.md"])  # wholesale replace, not append

    def test_nonmatching_keeps_base_array(self):
        ctx = make_ctx(hostname="other-machine")
        effective, errors, warnings, explain = ch.resolve_profile(self.dir, ctx)
        self.assertEqual(errors, [])
        paths = [i["path"] for i in effective["instructions"]]
        self.assertEqual(paths, ["a.md"])


class TestMissingAggregateLimit(unittest.TestCase):
    def test_environment_override_without_aggregate_is_error(self):
        tmp = tempfile.TemporaryDirectory()
        try:
            d = Path(tmp.name)
            write(
                d / "chevaline.toml",
                """
spec = "0.2"

[budget]
limits = [ { scope = "*", window = "day", amount = 10, unit = "USD" } ]

[environment.work]
when.hostname = "work-machine"

[environment.work.budget]
limits = [ { scope = "deep", window = "day", amount = 500000, unit = "tokens" } ]
""",
            )
            errors, warnings, raw = ch.validate_profile(d)
            self.assertTrue(
                any("BUDGET AGGREGATE MISSING" in e for e in errors),
                msg=f"expected aggregate error, got: {errors}",
            )
        finally:
            tmp.cleanup()

    def test_base_without_aggregate_is_error(self):
        tmp = tempfile.TemporaryDirectory()
        try:
            d = Path(tmp.name)
            write(
                d / "chevaline.toml",
                """
spec = "0.2"

[budget]
limits = [ { scope = "deep", window = "day", amount = 500000, unit = "tokens" } ]
""",
            )
            errors, warnings, raw = ch.validate_profile(d)
            self.assertTrue(any("BUDGET AGGREGATE MISSING" in e for e in errors))
        finally:
            tmp.cleanup()

    def test_missing_budget_entirely_is_error(self):
        tmp = tempfile.TemporaryDirectory()
        try:
            d = Path(tmp.name)
            write(d / "chevaline.toml", 'spec = "0.2"\n')
            errors, warnings, raw = ch.validate_profile(d)
            self.assertTrue(any("BUDGET AGGREGATE MISSING" in e for e in errors))
        finally:
            tmp.cleanup()


class TestMissingUnit(unittest.TestCase):
    def test_missing_unit_rejected(self):
        tmp = tempfile.TemporaryDirectory()
        try:
            d = Path(tmp.name)
            write(
                d / "chevaline.toml",
                """
spec = "0.2"

[budget]
limits = [ { scope = "*", window = "day", amount = 10 } ]
""",
            )
            errors, warnings, raw = ch.validate_profile(d)
            self.assertTrue(
                any("unit" in e and "missing required field" in e for e in errors),
                msg=f"got: {errors}",
            )
        finally:
            tmp.cleanup()


class TestUnknownSelector(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        write(
            self.dir / "chevaline.toml",
            """
spec = "0.2"

[budget]
limits = [ { scope = "*", window = "day", amount = 10, unit = "USD" } ]

[environment.mystery]
when.branch = "main"

[environment.mystery.budget]
limits = [ { scope = "*", window = "day", amount = 999, unit = "USD" } ]
""",
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_validate_warns_not_errors(self):
        errors, warnings, raw = ch.validate_profile(self.dir)
        self.assertEqual(errors, [])
        self.assertTrue(any("unknown selector" in w for w in warnings))

    def test_resolve_fails_closed(self):
        ctx = make_ctx()
        effective, errors, warnings, explain = ch.resolve_profile(self.dir, ctx)
        self.assertEqual(errors, [])
        rep = explain["environments"][0]
        self.assertFalse(rep["matched"])
        self.assertIn("unknown selector", rep["reason"])
        # base budget (10 USD) should remain in effect, not the mystery override
        self.assertEqual(effective["budget"]["limits"][0]["amount"], 10)


class TestMissingReferencedPath(unittest.TestCase):
    def test_missing_instruction_path_rejected(self):
        tmp = tempfile.TemporaryDirectory()
        try:
            d = Path(tmp.name)
            write(
                d / "chevaline.toml",
                """
spec = "0.2"

[budget]
limits = [ { scope = "*", window = "day", amount = 10, unit = "USD" } ]

[[instructions]]
path = "instructions/does-not-exist.md"
""",
            )
            errors, warnings, raw = ch.validate_profile(d)
            self.assertTrue(
                any("does-not-exist.md" in e for e in errors), msg=f"got: {errors}"
            )
        finally:
            tmp.cleanup()


class TestCLI(unittest.TestCase):
    def test_validate_cli_exit_codes(self):
        import subprocess

        tool = REPO_ROOT / "tools" / "chevaline.py"
        result = subprocess.run(
            [sys.executable, str(tool), "validate", str(ADA_DIR)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        self.assertIn("valid", result.stdout)

    def test_resolve_cli_json(self):
        import subprocess
        import json

        tool = REPO_ROOT / "tools" / "chevaline.py"
        result = subprocess.run(
            [sys.executable, str(tool), "resolve", str(ADA_DIR), "--json"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertIn("config", payload)
        self.assertIn("spec", payload["config"])

    def test_resolve_cli_explain(self):
        import subprocess

        tool = REPO_ROOT / "tools" / "chevaline.py"
        result = subprocess.run(
            [sys.executable, str(tool), "resolve", str(ADA_DIR), "--explain"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        self.assertIn("Environments considered", result.stdout)


if __name__ == "__main__":
    unittest.main()
