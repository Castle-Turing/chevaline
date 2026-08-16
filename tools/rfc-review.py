#!/usr/bin/env python3
"""rfc-review.py — turn a Chevaline RFC into a self-contained review packet
ready to paste to a model reviewer.

    python3 rfc-review.py <rfc>
        [--questions 1,3]
        [--split N]
        [--with-comments]
        [--out DIR]

`<rfc>` is either a bare number ("3" / "0003", resolved by globbing
`docs/rfcs/NNNN-*.md`) or a path to an RFC file.

Standard library only. Requires Python 3.11+.

Why a generator at all, rather than "paste the file": docs/rfcs/README.md
sets rules for how model review has to be framed to be worth anything —
state what was asked, do not let prior comments anchor the next reviewer,
do not oversell the proposal, distribute questions rather than pooling them.
Those rules are easy to state and easy to forget under a paste. This tool
applies them mechanically every time. Where docs/rfcs/README.md and
0000-template.md left a formatting choice open, the judgment call taken is
noted in a comment near the relevant code.
"""

from __future__ import annotations

import argparse
import datetime
import re
import sys
from dataclasses import dataclass
from pathlib import Path


# --------------------------------------------------------------------------
# Errors
# --------------------------------------------------------------------------


class RfcError(Exception):
    """Any user-facing failure: bad RFC reference, unparsable file, bad args."""


# --------------------------------------------------------------------------
# Parsing an RFC file into its structural pieces
# --------------------------------------------------------------------------

# "# RFC 0003 — Title" — accept an em dash or a plain hyphen, since nothing
# enforces which one a given editor produced.
TITLE_RE = re.compile(r"^#\s*RFC\s+(\d+)\s*[—-]\s*(.+?)\s*$", re.MULTILINE)

# Top-level "## Heading" lines. RFCs are not limited to the template's
# section set (0003 has "Found in practice", 0008 has "Note: this RFC
# probably wants splitting"), so sections are discovered generically rather
# than matched against a fixed list.
SECTION_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)

# A numbered reviewer-question item: "N. text..." where "text" continues
# on to following lines until the next "N. " line or the end of the
# section. Observed in 0003/0007/0008: items are contiguous, with no blank
# line separating one from the next.
QUESTION_ITEM_RE = re.compile(r"^(\d+)\.\s+(.*(?:\n(?!\d+\.\s).*)*)", re.MULTILINE)

REVIEWER_QUESTIONS_HEADING = "Reviewer questions"
COMMENTS_HEADING = "Comments"


@dataclass
class Rfc:
    number: str  # as printed in the title, e.g. "0003"
    title: str
    preamble: str  # everything before the first "## " heading
    sections: list[tuple[str, str]]  # (heading text, full section incl. "## " line)
    path: Path


def parse_rfc(text: str, path: Path) -> Rfc:
    title_match = TITLE_RE.search(text)
    if not title_match:
        raise RfcError(
            f"{path}: could not find a '# RFC NNNN — Title' heading — "
            "is this an RFC file?"
        )
    number, title = title_match.group(1), title_match.group(2)

    heading_matches = list(SECTION_RE.finditer(text))
    preamble = text[: heading_matches[0].start()] if heading_matches else text

    sections: list[tuple[str, str]] = []
    for i, m in enumerate(heading_matches):
        start = m.start()
        end = heading_matches[i + 1].start() if i + 1 < len(heading_matches) else len(text)
        sections.append((m.group(1).strip(), text[start:end]))

    return Rfc(number=number, title=title, preamble=preamble, sections=sections, path=path)


def find_section(rfc: Rfc, heading: str) -> str | None:
    for h, body in rfc.sections:
        if h == heading:
            return body
    return None


def parse_questions(section_text: str) -> list[tuple[int, str]]:
    """Returns [(original_number, question_text), ...] in RFC order."""
    _, _, body = section_text.partition("\n")  # drop the "## Reviewer questions" line
    items = []
    for m in QUESTION_ITEM_RE.finditer(body):
        items.append((int(m.group(1)), m.group(2).rstrip()))
    return items


def next_comment_number(rfc: Rfc) -> int:
    """Best-effort next comment number, read from the RFC's own (real)
    Comments section — used only to seed a plausible placeholder in the
    response template. Not part of any spec requirement; a nicety so the
    template doesn't always suggest "C1" on an RFC that already has C1-C3.
    """
    comments = find_section(rfc, COMMENTS_HEADING)
    if not comments:
        return 1
    nums = [int(n) for n in re.findall(r"^###\s*C(\d+)\b", comments, re.MULTILINE)]
    return max(nums) + 1 if nums else 1


# --------------------------------------------------------------------------
# Resolving the <rfc> argument
# --------------------------------------------------------------------------


def resolve_rfc_path(arg: str, repo_root: Path) -> Path:
    if re.fullmatch(r"\d+", arg):
        padded = f"{int(arg):04d}"
        rfcs_dir = repo_root / "docs" / "rfcs"
        matches = sorted(rfcs_dir.glob(f"{padded}-*.md"))
        if not matches:
            raise RfcError(
                f"no RFC found matching number {arg!r} "
                f"(looked for {rfcs_dir}/{padded}-*.md)"
            )
        if len(matches) > 1:
            names = ", ".join(str(m) for m in matches)
            raise RfcError(f"ambiguous RFC number {arg!r}: multiple files match: {names}")
        return matches[0]

    path = Path(arg)
    if not path.is_file():
        raise RfcError(f"RFC file not found: {arg}")
    return path


# --------------------------------------------------------------------------
# Selecting and distributing questions
# --------------------------------------------------------------------------


def select_questions(
    all_questions: list[tuple[int, str]], wanted: set[int] | None
) -> list[tuple[int, str]]:
    if wanted is None:
        return list(all_questions)
    available = {n for n, _ in all_questions}
    missing = wanted - available
    if missing:
        raise RfcError(
            f"--questions asked for {sorted(missing)}, but this RFC's "
            f"'## Reviewer questions' section only has {sorted(available)}"
        )
    # JUDGMENT CALL: preserve the RFC's own question order rather than the
    # order the caller listed them in --questions. The RFC's order already
    # encodes an intentional sequence (kill question first, and so on);
    # --questions is a filter, not a re-sequencing tool.
    return [q for q in all_questions if q[0] in wanted]


def round_robin_split(
    questions: list[tuple[int, str]], n: int
) -> list[list[tuple[int, str]]]:
    buckets: list[list[tuple[int, str]]] = [[] for _ in range(n)]
    for i, q in enumerate(questions):
        buckets[i % n].append(q)
    return buckets


# --------------------------------------------------------------------------
# Rendering the packet
# --------------------------------------------------------------------------

FRAMING = """\
## Framing

What follows is a draft proposal to an open, unfinished standard. It has
not been accepted. It has not been implemented. Nobody involved in writing
it has settled whether it is right.

Your job is to find what is wrong with it. Disagreement, hesitation, and
outright rejection are the useful outputs of this review — agreement is
not the goal and is not itself evidence the proposal is sound. If, having
read it, your view is that this proposal should be abandoned rather than
revised, say so plainly. That is a legitimate and welcome conclusion, not
a failure to engage constructively.
"""

VERIFICATION = """\
## Verification

For each factual claim you rely on in your answer, state whether you
checked it against a source or are answering from memory, and name the
sources you checked. "I do not know" and "I could not verify this" are
acceptable and useful answers — do not guess in order to sound
authoritative.
"""


def context_line(rfc: Rfc, with_comments: bool, bucket_len: int, total: int) -> str:
    if with_comments:
        line = (
            f"You are seeing RFC {rfc.number} only, including its existing "
            "review comments. You are not seeing SPEC.md, the other RFCs, "
            "or the repository."
        )
    else:
        line = (
            f"You are seeing RFC {rfc.number} only. You are not seeing "
            "SPEC.md, the other RFCs, the repository, or this RFC's "
            "existing review comments — comments are withheld by default "
            "so your reading is not anchored to what earlier reviewers "
            "said."
        )
    if bucket_len < total:
        line += (
            f" You are being asked {bucket_len} of this RFC's {total} "
            "reviewer questions; other reviewers are being asked the "
            "rest, so that different questions get different eyes rather "
            "than the same four questions being asked five times."
        )
    return line


def render_body(rfc: Rfc, with_comments: bool) -> str:
    # JUDGMENT CALL: the task spec says only "the ## Comments section
    # stripped unless --with-comments" for item 3 (the body), and
    # separately says item 4 carries "the assigned questions only". Taken
    # literally, item 3 would still include the RFC's full, unfiltered
    # "## Reviewer questions" section, which would show every reviewer
    # every question regardless of --questions/--split — defeating the
    # purpose of restricting exposure (the same herding/anchoring concern
    # that justifies stripping Comments). So the body strips
    # "## Reviewer questions" unconditionally too; item 4 is the only place
    # questions are shown, and only the assigned ones.
    excluded = {REVIEWER_QUESTIONS_HEADING}
    if not with_comments:
        excluded.add(COMMENTS_HEADING)
    parts = [rfc.preamble]
    for heading, body in rfc.sections:
        if heading in excluded:
            continue
        parts.append(body)
    return "".join(parts).rstrip("\n") + "\n"


def render_questions(bucket: list[tuple[int, str]], rfc: Rfc) -> str:
    lines = ["## Questions for you", ""]
    for presented, (original, text) in enumerate(bucket, start=1):
        lines.append(f"{presented}. *(RFC {rfc.number}'s original question {original})*")
        # Keep the question's own text (including its bold label, e.g.
        # "**Kill question.**") verbatim, indented to read as part of the
        # same list item.
        # `text`'s continuation lines already carry the source RFC's own
        # 3-space list-continuation indent (captured verbatim); strip it
        # before re-indenting under our own numbering, or it doubles up.
        for line in text.split("\n"):
            stripped = line[3:] if line.startswith("   ") else line
            lines.append(f"   {stripped}" if stripped else "")
    return "\n".join(lines) + "\n"


def render_response_template(rfc: Rfc, how_it_saw: str) -> str:
    date = datetime.date.today().isoformat()
    comment_num = next_comment_number(rfc)
    return (
        "## Your response\n\n"
        "Use exactly this format (from docs/rfcs/0000-template.md):\n\n"
        "```markdown\n"
        f"### C{comment_num} — {date} · <state your model name and "
        f"version here, or `unattributed` if you do not know it> · "
        f"{how_it_saw}\n\n"
        "- **Asked for:** \n"
        "- **Position:** \n"
        "- **Verified:** \n"
        "- **Disposition:** pending\n"
        "```\n"
    )


def build_packet(
    rfc: Rfc,
    bucket: list[tuple[int, str]],
    total_questions: int,
    with_comments: bool,
    packet_i: int | None,
    packet_n: int | None,
) -> str:
    title_line = f"# Review packet — RFC {rfc.number}: {rfc.title}"
    parts = [title_line]
    if packet_n is not None:
        parts.append(f"*Packet {packet_i} of {packet_n}.*")
    parts.append("")
    parts.append(FRAMING)

    ctx = context_line(rfc, with_comments, len(bucket), total_questions)
    parts.append("## Context\n\n" + ctx + "\n")

    parts.append("## RFC text\n")
    parts.append(render_body(rfc, with_comments))

    parts.append(render_questions(bucket, rfc))

    parts.append(VERIFICATION)

    how_it_saw = ctx if packet_n is None else (
        f"RFC {rfc.number} only" + (", with comments" if with_comments else "")
        + f", packet {packet_i} of {packet_n} ({len(bucket)}/{total_questions} questions)"
    )
    parts.append(render_response_template(rfc, how_it_saw))

    return "\n".join(parts).rstrip("\n") + "\n"


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def parse_questions_arg(raw: str) -> set[int]:
    try:
        return {int(x.strip()) for x in raw.split(",") if x.strip()}
    except ValueError:
        raise RfcError(f"--questions must be a comma-separated list of integers, got {raw!r}")


def run(args: argparse.Namespace) -> int:
    repo_root = Path(__file__).resolve().parent.parent
    try:
        rfc_path = resolve_rfc_path(args.rfc, repo_root)
        text = rfc_path.read_text()
        rfc = parse_rfc(text, rfc_path)

        rq_section = find_section(rfc, REVIEWER_QUESTIONS_HEADING)
        if rq_section is None:
            raise RfcError(
                f"RFC {rfc.number} ({rfc_path}) has no '## Reviewer questions' "
                "section — nothing to build a packet from"
            )
        all_questions = parse_questions(rq_section)
        if not all_questions:
            raise RfcError(
                f"RFC {rfc.number} ({rfc_path}) has a '## Reviewer questions' "
                "section but no numbered questions could be parsed from it"
            )

        wanted = parse_questions_arg(args.questions) if args.questions else None
        selected = select_questions(all_questions, wanted)

        if args.split is not None:
            if args.split < 1:
                raise RfcError("--split must be a positive integer")
            buckets = round_robin_split(selected, args.split)
            packets = [
                (i + 1, args.split, bucket)
                for i, bucket in enumerate(buckets)
                if bucket  # a packet with no questions is not emitted
            ]
        else:
            packets = [(1, None, selected)]

        if not packets:
            raise RfcError("no questions selected — nothing to build a packet from")

    except RfcError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    total = len(all_questions)
    rendered = [
        (i, n, build_packet(rfc, bucket, total, args.with_comments, i, n))
        for i, n, bucket in packets
    ]

    if args.out:
        out_dir = Path(args.out)
        out_dir.mkdir(parents=True, exist_ok=True)
        for i, n, packet_text in rendered:
            if n is None:
                fname = f"rfc-{rfc.number}-review-packet.md"
            else:
                fname = f"rfc-{rfc.number}-packet-{i}-of-{n}.md"
            out_path = out_dir / fname
            out_path.write_text(packet_text)
            print(f"wrote {out_path}")
    else:
        divider = "\n" + ("=" * 78) + "\n\n"
        sys.stdout.write(divider.join(p for _, _, p in rendered))

    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="rfc-review.py",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "rfc", help='RFC number ("3" / "0003", resolved by glob) or a path to an RFC file'
    )
    parser.add_argument(
        "--questions",
        default=None,
        metavar="N,N,...",
        help="only include these original question numbers (default: all)",
    )
    parser.add_argument(
        "--split",
        type=int,
        default=None,
        metavar="N",
        help="emit N packets, distributing questions round-robin",
    )
    parser.add_argument(
        "--with-comments",
        action="store_true",
        help="include the RFC's existing '## Comments' section (default: excluded)",
    )
    parser.add_argument(
        "--out",
        default=None,
        metavar="DIR",
        help="write packet file(s) to DIR instead of stdout",
    )
    args = parser.parse_args(argv)
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
