#!/usr/bin/env python3
"""Anti-drift guard: every `file:line` citation in docs/ must still resolve.

The spec method (CLAUDE.md) grounds each documented behaviour in a `file:line`
citation. When code moves, those citations rot — and a rotten citation is the
first visible sign that SPEC/DECISIONS have drifted from the code.

This guard catches the two mechanical failures:
  * the cited file no longer exists, or
  * the cited line (or the end of a `start-end` range) is past the file's end.

It deliberately does NOT check that the cited lines still say the right thing —
that needs a human. It only flags citations that can no longer point anywhere,
i.e. the cheapest, surest drift signal. Run over the living specs on every
commit (not just changed docs), because a citation usually dies from a *code*
edit, not a doc edit.

Scope: only the **living** specs (SPEC.md + its Polish mirror), which describe
what the code does *today*, so every citation there must resolve. The ledgers
(CHANGES.md / ZMIANY.md) and the decision log (DECISIONS.md) are deliberately
EXCLUDED: their "Now:" / implementation citations are point-in-time snapshots of
code that a shipped change has since deleted — they are *meant* to rot, and
flagging them would be a false alarm.

Exit code 0 = all citations resolve; 1 = at least one dead citation (printed).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = REPO_ROOT / "docs"

# Only the living specs are guarded — see the module docstring for why the
# ledgers and the decision log are excluded.
LIVING_SPECS = ("SPEC.md", "SPECYFIKACJA.md")

# Code-file extensions a citation may target. `.py` is all that exists today;
# the rest are here so frontend citations (added when the frontend is reviewed)
# are covered without a code change.
CODE_EXTENSIONS = ("py", "ts", "tsx", "js", "jsx", "mjs", "sql")

# Matches an inline-code citation like `app/process/service.py:2237-2240`
# or `app/work_orders/models.py:52`. Group 1 = path, 2 = start, 3 = end (opt).
_EXT_ALT = "|".join(CODE_EXTENSIONS)
CITATION_RE = re.compile(
    r"`(?P<path>[A-Za-z0-9_./-]+\.(?:" + _EXT_ALT + r")):"
    r"(?P<start>\d+)(?:-(?P<end>\d+))?`"
)


def file_line_count(path: Path) -> int:
    # Count lines tolerant of the final newline; encoding errors shouldn't crash
    # the guard, so read as bytes and split.
    data = path.read_bytes()
    if not data:
        return 0
    return data.count(b"\n") + (0 if data.endswith(b"\n") else 1)


def check_doc(doc: Path) -> list[str]:
    """Return human-readable problems for one doc file (empty list = clean)."""
    problems: list[str] = []
    for lineno, text in enumerate(doc.read_text(encoding="utf-8").splitlines(), 1):
        for m in CITATION_RE.finditer(text):
            cited = m.group("path")
            start = int(m.group("start"))
            end = int(m.group("end")) if m.group("end") else start
            where = f"{doc.relative_to(REPO_ROOT).as_posix()}:{lineno}"
            target = REPO_ROOT / cited
            if not target.is_file():
                problems.append(f"{where}: cited file does not exist -> `{cited}`")
                continue
            n = file_line_count(target)
            hi = max(start, end)
            if hi > n:
                problems.append(
                    f"{where}: `{cited}` cites line {hi} but the file has {n} lines"
                )
    return problems


def main() -> int:
    all_problems: list[str] = []
    for name in LIVING_SPECS:
        doc = DOCS_DIR / name
        if not doc.is_file():
            continue
        all_problems.extend(check_doc(doc))
    if all_problems:
        print("Dead `file:line` citation(s) — docs have drifted from the code:\n")
        for p in all_problems:
            print(f"  {p}")
        print(
            "\nFix the citation (re-point it at the moved code) or update the doc. "
            "See CLAUDE.md: SPEC is updated in the same change as the code."
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
