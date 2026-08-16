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
spec = "0.3"

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
spec = "0.3"

[models]
cheap = "base-cheap"
standard = "base-standard"
deep = "base-deep"

[budget]
limits = [ { scope = "*", window = "day", amount = 10, unit = "USD" } ]

[[environment]]
name = "work"
when.hostname = "work-machine"

  [environment.models]
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
spec = "0.3"

[budget]
limits = [ { scope = "*", window = "day", amount = 10, unit = "USD" } ]

[[instructions]]
path = "a.md"

[[environment]]
name = "work"
when.hostname = "work-machine"

  [[environment.instructions]]
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


class TestEnvironmentArrayDeclarationOrder(unittest.TestCase):
    """SPEC §2.1: environments merge onto the base in *declaration order* —
    a later matching environment wins over an earlier one — and this is now
    guaranteed by TOML array order rather than incidental dict-insertion
    order. Names are chosen to sort in the opposite order from declaration,
    so a test that accidentally relied on name/alphabetical order instead of
    real array order would fail.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        write(
            self.dir / "chevaline.toml",
            """
spec = "0.3"

[budget]
limits = [ { scope = "*", window = "day", amount = 10, unit = "USD" } ]

[[environment]]
name = "zzz-first-declared"
when.hostname = "shared-machine"

  [environment.models]
  cheap = "from-zzz"

[[environment]]
name = "aaa-second-declared"
when.hostname = "shared-machine"

  [environment.models]
  cheap = "from-aaa"
""",
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_later_declared_environment_wins(self):
        ctx = make_ctx(hostname="shared-machine")
        effective, errors, warnings, explain = ch.resolve_profile(self.dir, ctx)
        self.assertEqual(errors, [])
        # Both environments match; the second one *declared* must win, even
        # though its name sorts alphabetically before the first.
        self.assertEqual(effective["models"]["cheap"], "from-aaa")
        matched = [e["name"] for e in explain["environments"] if e["matched"]]
        self.assertEqual(matched, ["zzz-first-declared", "aaa-second-declared"])
        self.assertEqual(explain["sources"]["models.cheap"], "aaa-second-declared")


class TestDuplicateEnvironmentName(unittest.TestCase):
    def test_duplicate_names_rejected(self):
        tmp = tempfile.TemporaryDirectory()
        try:
            d = Path(tmp.name)
            write(
                d / "chevaline.toml",
                """
spec = "0.3"

[budget]
limits = [ { scope = "*", window = "day", amount = 10, unit = "USD" } ]

[[environment]]
name = "work"
when.hostname = "a"

[[environment]]
name = "work"
when.hostname = "b"
""",
            )
            errors, warnings, raw = ch.validate_profile(d)
            self.assertTrue(
                any("duplicate environment name" in e for e in errors),
                msg=f"got: {errors}",
            )
        finally:
            tmp.cleanup()


class TestMissingEnvironmentName(unittest.TestCase):
    def test_missing_name_rejected(self):
        tmp = tempfile.TemporaryDirectory()
        try:
            d = Path(tmp.name)
            write(
                d / "chevaline.toml",
                """
spec = "0.3"

[budget]
limits = [ { scope = "*", window = "day", amount = 10, unit = "USD" } ]

[[environment]]
when.hostname = "a"
""",
            )
            errors, warnings, raw = ch.validate_profile(d)
            self.assertTrue(
                any("missing required field 'name'" in e for e in errors),
                msg=f"got: {errors}",
            )
        finally:
            tmp.cleanup()


class TestMissingAggregateLimit(unittest.TestCase):
    def test_environment_override_without_aggregate_is_error(self):
        tmp = tempfile.TemporaryDirectory()
        try:
            d = Path(tmp.name)
            write(
                d / "chevaline.toml",
                """
spec = "0.3"

[budget]
limits = [ { scope = "*", window = "day", amount = 10, unit = "USD" } ]

[[environment]]
name = "work"
when.hostname = "work-machine"

  [environment.budget]
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
spec = "0.3"

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
            write(d / "chevaline.toml", 'spec = "0.3"\n')
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
spec = "0.3"

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


class TestUnknownSelectorKnownSpec(unittest.TestCase):
    """spec = "0.3" is a version this tool fully implements, so an unknown
    selector cannot be a forward-compat case (SPEC §2.1) — it's a
    validation error.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        write(
            self.dir / "chevaline.toml",
            """
spec = "0.3"

[budget]
limits = [ { scope = "*", window = "day", amount = 10, unit = "USD" } ]

[[environment]]
name = "mystery"
when.branch = "main"

  [environment.budget]
  limits = [ { scope = "*", window = "day", amount = 999, unit = "USD" } ]
""",
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_validate_errors_not_warns(self):
        errors, warnings, raw = ch.validate_profile(self.dir)
        self.assertTrue(
            any("unknown selector" in e for e in errors), msg=f"got errors={errors}"
        )

    def test_resolve_refuses_because_validate_errors(self):
        ctx = make_ctx()
        effective, errors, warnings, explain = ch.resolve_profile(self.dir, ctx)
        self.assertIsNone(effective)
        self.assertTrue(any("unknown selector" in e for e in errors))


class TestUnknownSelectorNewerSpec(unittest.TestCase):
    """spec declares a version newer than this tool implements (0.3), so an
    unknown selector is treated as forward-compatible: a warning, and the
    environment fails closed (never matches) rather than the profile being
    rejected outright.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        write(
            self.dir / "chevaline.toml",
            """
spec = "0.99"

[budget]
limits = [ { scope = "*", window = "day", amount = 10, unit = "USD" } ]

[[environment]]
name = "mystery"
when.branch = "main"

  [environment.budget]
  limits = [ { scope = "*", window = "day", amount = 999, unit = "USD" } ]
""",
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_validate_warns_not_errors(self):
        errors, warnings, raw = ch.validate_profile(self.dir)
        self.assertEqual(errors, [], msg=f"got errors={errors}")
        self.assertTrue(any("unknown selector" in w for w in warnings))
        self.assertTrue(
            any(w.startswith(ch.FORWARD_COMPAT_MARKER) for w in warnings),
            msg=f"expected a prominently-marked forward-compat warning, got: {warnings}",
        )

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
spec = "0.3"

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


class TestComposeShapeRules(unittest.TestCase):
    def _validate(self, body: str):
        tmp = tempfile.TemporaryDirectory()
        try:
            d = Path(tmp.name)
            write(
                d / "chevaline.toml",
                'spec = "0.3"\n\n'
                '[budget]\n'
                'limits = [ { scope = "*", window = "day", amount = 10, unit = "USD" } ]\n\n'
                + body,
            )
            return ch.validate_profile(d)
        finally:
            tmp.cleanup()

    def test_layer_on_sessions_is_error(self):
        errors, warnings, raw = self._validate(
            '[sessions]\nisolation = "worktree"\ncompose = "layer"\n'
        )
        self.assertTrue(
            any("sessions" in e and "compose" in e for e in errors), msg=f"got: {errors}"
        )

    def test_defer_on_sessions_is_valid(self):
        errors, warnings, raw = self._validate(
            '[sessions]\nisolation = "worktree"\ncompose = "defer"\n'
        )
        self.assertEqual(errors, [])

    def test_insist_on_sessions_is_valid(self):
        errors, warnings, raw = self._validate(
            '[sessions]\nisolation = "worktree"\ncompose = "insist"\n'
        )
        self.assertEqual(errors, [])

    def test_restrict_on_sessions_is_error(self):
        errors, warnings, raw = self._validate(
            '[sessions]\nisolation = "worktree"\ncompose = "restrict"\n'
        )
        self.assertTrue(any("sessions" in e and "compose" in e for e in errors))

    def test_layer_on_harnesses_is_error(self):
        # SPEC §3.3: "single-valued in effect" -> only defer/insist valid.
        errors, warnings, raw = self._validate(
            '[harnesses]\nprefer = ["claude-code"]\ncompose = "layer"\n'
        )
        self.assertTrue(any("harnesses" in e and "compose" in e for e in errors))

    def test_defer_on_harnesses_is_valid(self):
        errors, warnings, raw = self._validate(
            '[harnesses]\nprefer = ["claude-code"]\ncompose = "defer"\n'
        )
        self.assertEqual(errors, [])

    def test_restrict_on_models_is_error(self):
        # SPEC §3.4 (corrected): restrict is deliberately NOT valid for
        # models — a tier-to-identifier mapping has no stated ordering.
        errors, warnings, raw = self._validate(
            '[models]\ncheap = "x"\ncompose = "restrict"\n'
        )
        self.assertTrue(any("models" in e and "compose" in e for e in errors))

    def test_defer_on_models_is_valid(self):
        errors, warnings, raw = self._validate(
            '[models]\ncheap = "x"\ncompose = "defer"\n'
        )
        self.assertEqual(errors, [])

    def test_layer_on_gates_is_valid(self):
        errors, warnings, raw = self._validate(
            '[[gates]]\nid = "g"\non = "merge"\ndescription = "d"\ncompose = "layer"\n'
        )
        self.assertEqual(errors, [])

    def test_restrict_on_gates_is_error(self):
        errors, warnings, raw = self._validate(
            '[[gates]]\nid = "g"\non = "merge"\ndescription = "d"\ncompose = "restrict"\n'
        )
        self.assertTrue(any("gates" in e and "compose" in e for e in errors))

    def test_defer_on_extensions_is_valid(self):
        errors, warnings, raw = self._validate(
            '[[extensions]]\nid = "e"\ndescription = "d"\ncompose = "defer"\n'
        )
        self.assertEqual(errors, [])

    def test_restrict_on_extensions_is_error(self):
        errors, warnings, raw = self._validate(
            '[[extensions]]\nid = "e"\ndescription = "d"\ncompose = "restrict"\n'
        )
        self.assertTrue(any("extensions" in e and "compose" in e for e in errors))

    def test_compose_on_authority_is_rejected_outright(self):
        # SPEC §3.9 (corrected): authority composes with `restrict` always
        # and the mode is not settable -- ANY explicit `compose` key here is
        # an error, regardless of its value.
        errors, warnings, raw = self._validate(
            '[authority]\ndefault = "reported"\ncompose = "restrict"\n'
        )
        self.assertTrue(
            any("authority" in e and "compose" in e for e in errors), msg=f"got: {errors}"
        )

    def test_compose_on_authority_is_rejected_even_when_value_would_otherwise_be_valid(self):
        errors, warnings, raw = self._validate(
            '[authority]\ndefault = "reported"\ncompose = "restrict"\n'
        )
        # Not merely "restrict is the wrong value" -- the key itself is invalid.
        self.assertTrue(any("not a valid field" in e or "not settable" in e for e in errors))


class TestExplicitActivation(unittest.TestCase):
    """SPEC §3.2: explicit activation selects an environment by `name`,
    bypassing `when` entirely, and is the only way a `when`-less
    environment ever applies.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        write(
            self.dir / "chevaline.toml",
            """
spec = "0.3"

[budget]
limits = [ { scope = "*", window = "day", amount = 10, unit = "USD" } ]

[[environment]]
name = "no-when-block"

  [environment.models]
  cheap = "explicit-only-model"
""",
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_when_less_environment_never_matches_without_explicit_activation(self):
        ctx = make_ctx()
        effective, errors, warnings, explain = ch.resolve_profile(self.dir, ctx)
        self.assertEqual(errors, [])
        self.assertNotIn("models", effective)
        rep = explain["environments"][0]
        self.assertFalse(rep["matched"])

    def test_explicit_activation_bypasses_when(self):
        ctx = make_ctx()
        effective, errors, warnings, explain = ch.resolve_profile(
            self.dir, ctx, explicit_names={"no-when-block"}
        )
        self.assertEqual(errors, [])
        self.assertEqual(effective["models"]["cheap"], "explicit-only-model")
        rep = explain["environments"][0]
        self.assertTrue(rep["matched"])
        self.assertIn("explicitly activated", rep["reason"])

    def test_explicit_activation_of_unknown_name_is_error(self):
        ctx = make_ctx()
        effective, errors, warnings, explain = ch.resolve_profile(
            self.dir, ctx, explicit_names={"does-not-exist"}
        )
        self.assertIsNone(effective)
        self.assertTrue(any("does-not-exist" in e for e in errors), msg=f"got: {errors}")

    def test_cli_environment_flag(self):
        import subprocess
        import json

        tool = REPO_ROOT / "tools" / "chevaline.py"
        result = subprocess.run(
            [sys.executable, str(tool), "resolve", str(self.dir), "--json", "--environment", "no-when-block"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["config"]["models"]["cheap"], "explicit-only-model")


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
