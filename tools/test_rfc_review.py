"""Tests for tools/rfc-review.py. Stdlib unittest only.

Fixtures are written to temp dirs at test time; nothing is added to the repo.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import importlib.util

_spec = importlib.util.spec_from_file_location(
    "rfc_review", Path(__file__).resolve().parent / "rfc-review.py"
)
rr = importlib.util.module_from_spec(_spec)
sys.modules["rfc_review"] = rr  # dataclass() needs the module registered
_spec.loader.exec_module(rr)  # noqa: E402


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


FULL_RFC = """# RFC 0042 — Example proposal for testing

- **Status:** Draft
- **Raised:** 2026-08-16, a test fixture
- **Affects:** nothing real

## Summary

A one-paragraph summary of the fictional change.

## Problem

Some problem statement that spans
a couple of lines.

## Proposal

The illustrative proposal text.

## Consequences

Some consequences.

## Open questions

- An open question.

## How this gets decided

The evidence that would settle it.

## Reviewer questions

1. **Kill question.** What answer here would mean this proposal should be
   abandoned rather than revised?
2. A question about the thing the author is least sure of.
3. A factual claim in this RFC, named, with a request to check it against
   a source rather than from memory.
4. A question about whether this is the right problem to solve.

## Comments

*Append-only.*

### C1 — 2026-08-01 · gpt-test · read the whole repo

- **Asked for:** an assessment
- **Position:** looks fine
- **Verified:** nothing
- **Disposition:** pending

### C2 — 2026-08-02 · claude-test · pasted the file

- **Asked for:** a second opinion
- **Position:** disagree with C1
- **Verified:** nothing
- **Disposition:** pending
"""


NO_QUESTIONS_RFC = """# RFC 0099 — No reviewer questions here

- **Status:** Draft
- **Raised:** 2026-08-16, a test fixture
- **Affects:** nothing real

## Summary

No reviewer questions section at all.

## Problem

N/A.
"""


class TestRfcParsing(unittest.TestCase):
    def test_parses_title_and_number(self):
        rfc = rr.parse_rfc(FULL_RFC, Path("0042-example.md"))
        self.assertEqual(rfc.number, "0042")
        self.assertEqual(rfc.title, "Example proposal for testing")

    def test_finds_reviewer_questions_section(self):
        rfc = rr.parse_rfc(FULL_RFC, Path("0042-example.md"))
        section = rr.find_section(rfc, rr.REVIEWER_QUESTIONS_HEADING)
        self.assertIsNotNone(section)
        self.assertIn("Kill question", section)

    def test_parses_four_numbered_questions_in_order(self):
        rfc = rr.parse_rfc(FULL_RFC, Path("0042-example.md"))
        section = rr.find_section(rfc, rr.REVIEWER_QUESTIONS_HEADING)
        questions = rr.parse_questions(section)
        self.assertEqual([n for n, _ in questions], [1, 2, 3, 4])
        self.assertIn("Kill question", questions[0][1])
        self.assertIn("abandoned rather than revised", questions[0][1])

    def test_missing_reviewer_questions_section_is_none(self):
        rfc = rr.parse_rfc(NO_QUESTIONS_RFC, Path("0099-none.md"))
        self.assertIsNone(rr.find_section(rfc, rr.REVIEWER_QUESTIONS_HEADING))


class TestNumberAndPathResolution(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.rfcs_dir = self.root / "docs" / "rfcs"
        write(self.rfcs_dir / "0003-budget-thing.md", FULL_RFC)
        write(self.rfcs_dir / "0042-example.md", FULL_RFC)

    def tearDown(self):
        self.tmp.cleanup()

    def test_bare_number_resolves_by_glob(self):
        p = rr.resolve_rfc_path("42", self.root)
        self.assertEqual(p, self.rfcs_dir / "0042-example.md")

    def test_zero_padded_number_resolves(self):
        p = rr.resolve_rfc_path("0003", self.root)
        self.assertEqual(p, self.rfcs_dir / "0003-budget-thing.md")

    def test_explicit_path_is_used_directly(self):
        target = self.rfcs_dir / "0042-example.md"
        p = rr.resolve_rfc_path(str(target), self.root)
        self.assertEqual(p, target)

    def test_missing_number_raises_clear_error(self):
        with self.assertRaises(rr.RfcError) as cm:
            rr.resolve_rfc_path("9999", self.root)
        self.assertIn("9999", str(cm.exception))

    def test_missing_path_raises_clear_error(self):
        with self.assertRaises(rr.RfcError):
            rr.resolve_rfc_path(str(self.root / "nope.md"), self.root)


class TestCommentsStripping(unittest.TestCase):
    def setUp(self):
        self.rfc = rr.parse_rfc(FULL_RFC, Path("0042-example.md"))

    def test_comments_stripped_by_default(self):
        body = rr.render_body(self.rfc, with_comments=False)
        self.assertNotIn("## Comments", body)
        self.assertNotIn("C1 — 2026-08-01", body)

    def test_comments_retained_with_flag(self):
        body = rr.render_body(self.rfc, with_comments=True)
        self.assertIn("## Comments", body)
        self.assertIn("C1 — 2026-08-01", body)
        self.assertIn("C2 — 2026-08-02", body)

    def test_reviewer_questions_section_always_stripped_from_body(self):
        # The full question list is presented separately (item 4), not
        # embedded in the verbatim body, regardless of --with-comments.
        body_default = rr.render_body(self.rfc, with_comments=False)
        body_with_comments = rr.render_body(self.rfc, with_comments=True)
        self.assertNotIn("## Reviewer questions", body_default)
        self.assertNotIn("## Reviewer questions", body_with_comments)

    def test_body_retains_other_sections(self):
        body = rr.render_body(self.rfc, with_comments=False)
        for heading in ("## Summary", "## Problem", "## Proposal", "## Consequences"):
            self.assertIn(heading, body)


class TestQuestionSelection(unittest.TestCase):
    def setUp(self):
        self.rfc = rr.parse_rfc(FULL_RFC, Path("0042-example.md"))
        section = rr.find_section(self.rfc, rr.REVIEWER_QUESTIONS_HEADING)
        self.all_questions = rr.parse_questions(section)

    def test_questions_selects_subset(self):
        selected = rr.select_questions(self.all_questions, {1, 3})
        self.assertEqual([n for n, _ in selected], [1, 3])

    def test_questions_preserves_rfc_order_regardless_of_input_order(self):
        selected = rr.select_questions(self.all_questions, {3, 1})
        self.assertEqual([n for n, _ in selected], [1, 3])

    def test_unknown_question_number_raises(self):
        with self.assertRaises(rr.RfcError):
            rr.select_questions(self.all_questions, {1, 99})

    def test_no_filter_returns_all(self):
        selected = rr.select_questions(self.all_questions, None)
        self.assertEqual(selected, self.all_questions)

    def test_original_numbers_preserved_in_rendered_label(self):
        selected = rr.select_questions(self.all_questions, {3})
        rendered = rr.render_questions(selected, self.rfc)
        # Renumbered as "1." (presented order) but labelled with original "3".
        self.assertIn("1. *(RFC 0042's original question 3)*", rendered)


class TestSplit(unittest.TestCase):
    def setUp(self):
        self.rfc = rr.parse_rfc(FULL_RFC, Path("0042-example.md"))
        section = rr.find_section(self.rfc, rr.REVIEWER_QUESTIONS_HEADING)
        self.all_questions = rr.parse_questions(section)

    def test_round_robin_distributes_all_questions_without_loss_or_duplication(self):
        buckets = rr.round_robin_split(self.all_questions, 2)
        combined = sorted(n for bucket in buckets for n, _ in bucket)
        self.assertEqual(combined, [1, 2, 3, 4])

    def test_round_robin_shape(self):
        buckets = rr.round_robin_split(self.all_questions, 2)
        self.assertEqual([n for n, _ in buckets[0]], [1, 3])
        self.assertEqual([n for n, _ in buckets[1]], [2, 4])

    def test_split_more_than_questions_drops_empty_packets(self):
        buckets = rr.round_robin_split(self.all_questions, 6)
        nonempty = [b for b in buckets if b]
        self.assertEqual(len(nonempty), 4)  # 4 questions, so 4 non-empty buckets
        self.assertTrue(all(len(b) == 1 for b in nonempty))


class TestCliEndToEnd(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.rfcs_dir = self.root / "docs" / "rfcs"
        write(self.rfcs_dir / "0042-example.md", FULL_RFC)
        write(self.rfcs_dir / "0099-nq.md", NO_QUESTIONS_RFC)
        self._real_repo_root = rr.Path(__file__).resolve().parent.parent

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, argv, capsys_target="stdout"):
        import contextlib
        import io

        # Monkeypatch repo_root resolution: run() computes repo_root from
        # tools/rfc-review.py's own location, so point argv at an absolute
        # RFC path instead of exercising glob resolution here (that's
        # covered directly in TestNumberAndPathResolution).
        buf = io.StringIO()
        errbuf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(errbuf):
            rc = rr.main(argv)
        return rc, buf.getvalue(), errbuf.getvalue()

    def test_missing_rfc_path_gives_clear_error(self):
        rc, out, err = self._run([str(self.root / "does-not-exist.md")])
        self.assertEqual(rc, 1)
        self.assertIn("error:", err)

    def test_rfc_without_reviewer_questions_gives_clear_error(self):
        rc, out, err = self._run([str(self.rfcs_dir / "0099-nq.md")])
        self.assertEqual(rc, 1)
        self.assertIn("Reviewer questions", err)

    def test_full_packet_generated_to_stdout(self):
        rc, out, err = self._run([str(self.rfcs_dir / "0042-example.md")])
        self.assertEqual(rc, 0)
        self.assertIn("Review packet", out)
        self.assertIn("## Framing", out)
        self.assertIn("## Context", out)
        self.assertIn("## RFC text", out)
        self.assertIn("## Questions for you", out)
        self.assertIn("## Verification", out)
        self.assertIn("## Your response", out)
        self.assertNotIn("## Comments", out)
        # all four questions present by default
        for n in (1, 2, 3, 4):
            self.assertIn(f"original question {n}", out)

    def test_with_comments_flag_includes_comments(self):
        rc, out, err = self._run(
            [str(self.rfcs_dir / "0042-example.md"), "--with-comments"]
        )
        self.assertEqual(rc, 0)
        self.assertIn("## Comments", out)
        self.assertIn("C1 — 2026-08-01", out)

    def test_questions_flag_subsets_output(self):
        rc, out, err = self._run(
            [str(self.rfcs_dir / "0042-example.md"), "--questions", "1,3"]
        )
        self.assertEqual(rc, 0)
        self.assertIn("original question 1", out)
        self.assertIn("original question 3", out)
        self.assertNotIn("original question 2", out)
        self.assertNotIn("original question 4", out)

    def test_split_emits_multiple_labelled_packets_to_stdout(self):
        rc, out, err = self._run([str(self.rfcs_dir / "0042-example.md"), "--split", "2"])
        self.assertEqual(rc, 0)
        self.assertIn("Packet 1 of 2", out)
        self.assertIn("Packet 2 of 2", out)
        for n in (1, 2, 3, 4):
            self.assertIn(f"original question {n}", out)

    def test_split_writes_one_file_per_packet_with_out(self):
        out_dir = self.root / "packets"
        rc, out, err = self._run(
            [
                str(self.rfcs_dir / "0042-example.md"),
                "--split",
                "2",
                "--out",
                str(out_dir),
            ]
        )
        self.assertEqual(rc, 0)
        files = sorted(out_dir.glob("*.md"))
        self.assertEqual(len(files), 2)
        self.assertTrue((out_dir / "rfc-0042-packet-1-of-2.md").exists())
        self.assertTrue((out_dir / "rfc-0042-packet-2-of-2.md").exists())

    def test_split_with_fewer_questions_than_packets_drops_empty_packet(self):
        out_dir = self.root / "packets2"
        rc, out, err = self._run(
            [
                str(self.rfcs_dir / "0042-example.md"),
                "--questions",
                "1,2",
                "--split",
                "5",
                "--out",
                str(out_dir),
            ]
        )
        self.assertEqual(rc, 0)
        files = sorted(out_dir.glob("*.md"))
        # Only 2 questions selected -> at most 2 non-empty packets, even
        # though 5 were requested.
        self.assertEqual(len(files), 2)
        combined_text = "\n".join(f.read_text() for f in files)
        self.assertIn("original question 1", combined_text)
        self.assertIn("original question 2", combined_text)
        self.assertNotIn("original question 3", combined_text)


if __name__ == "__main__":
    unittest.main()
