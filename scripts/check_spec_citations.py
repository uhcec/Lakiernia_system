#!/usr/bin/env python3
"""Anti-drift guard: every `file:line` citation in docs/ must still resolve — and,
when anchored, still point at the code it claims to.

The spec method (CLAUDE.md) grounds each documented behaviour in a `file:line`
citation. When code moves, those citations rot — and a rotten citation is the
first visible sign that SPEC/DECISIONS have drifted from the code.

Two failure modes, two levels of guard:

  1. **Existence / range** (always checked): the cited file is gone, or the cited
     line (or the end of a `start-end` range) is past the file's end. The cheapest,
     surest drift signal.

  2. **Content** (checked when the citation carries an `@anchor`): the cited lines
     no longer contain the anchored token. A bare `path:line` only proves the line
     *exists*, so when code is inserted/deleted above it the citation silently slides
     onto unrelated code while still "resolving". The anchor closes that hole — see
     below.

## Anchored citations

Grammar:  `` `<path>:<start>[-<end>][@<anchor>]` ``

`<anchor>` is a short **literal substring** (a symbol name like `assign_plan`, or any
distinctive code fragment) that MUST appear somewhere within the cited line range.
Examples:

    `app/manager/service.py:1409-1412@def assign_plan`
    `app/manager/capacity.py:48@CHANGEOVER_ODZYSK_THRESHOLD_M2`

Because the anchor pins both *where* (the line range) and *what* (the token on those
lines), it fails loudly the moment the code moves: the line range no longer holds the
token, so a human must re-point the citation and re-confirm it still describes current
behaviour. That re-confirmation is exactly the drift check a bare line number cannot do.

Anchors are **optional and backward-compatible**: an un-anchored `path:line` is still
checked for existence/range (the legacy behaviour), so this can be rolled out file by
file. High-churn files (e.g. the large service modules) are the ones worth anchoring.

This guard is deliberately mechanical: it does NOT judge whether the prose is *correct*,
only whether the citation still lands on the claimed token. Run over the living specs on
every commit (not just changed docs), because a citation usually dies from a *code* edit,
not a doc edit.

Scope: the **living** docs — SPEC.md + its Polish mirror (what the code does *today*) and
REVIEW_LEDGER.md (open decision outcomes, citing the *current* control/badge a decision
shipped) — so every citation there must resolve. The change-ledgers (CHANGES.md /
ZMIANY.md) and the decision log (DECISIONS.md) are deliberately EXCLUDED: their "Now:" /
implementation citations are point-in-time snapshots of code that a shipped change has
since deleted — they are *meant* to rot, and flagging them would be a false alarm.

Exit code 0 = all citations resolve; 1 = at least one dead/misanchored citation (printed).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = REPO_ROOT / "docs"

# Only the living docs are guarded — see the module docstring for why the
# change-ledgers and the decision log are excluded. REVIEW_LEDGER.md is included:
# its citations point at *current* code (the control/badge a decision shipped), not
# point-in-time snapshots, so they must keep resolving like a spec line.
LIVING_SPECS = ("SPEC.md", "SPECYFIKACJA.md", "REVIEW_LEDGER.md")

# Code-file extensions a citation may target. `.py` is all that exists today;
# the rest are here so frontend citations (added when the frontend is reviewed)
# are covered without a code change.
CODE_EXTENSIONS = ("py", "ts", "tsx", "js", "jsx", "mjs", "sql")

# Matches an inline-code citation like `app/process/service.py:2237-2240`,
# `app/work_orders/models.py:52`, or the anchored form
# `app/manager/service.py:1409-1412@def assign_plan`.
# Group: path, start, end (opt), anchor (opt — any text up to the closing backtick).
_EXT_ALT = "|".join(CODE_EXTENSIONS)
CITATION_RE = re.compile(
    r"`(?P<path>[A-Za-z0-9_./-]+\.(?:" + _EXT_ALT + r")):"
    r"(?P<start>\d+)(?:-(?P<end>\d+))?"
    r"(?:@(?P<anchor>[^`]+))?`"
)


def file_lines(path: Path) -> list[str]:
    """The target file's lines (encoding-tolerant; errors shouldn't crash the guard)."""
    return path.read_text(encoding="utf-8", errors="replace").splitlines()


def check_doc(doc: Path) -> list[str]:
    """Return human-readable problems for one doc file (empty list = clean)."""
    problems: list[str] = []
    for lineno, text in enumerate(doc.read_text(encoding="utf-8").splitlines(), 1):
        for m in CITATION_RE.finditer(text):
            cited = m.group("path")
            start = int(m.group("start"))
            end = int(m.group("end")) if m.group("end") else start
            anchor = m.group("anchor")
            where = f"{doc.relative_to(REPO_ROOT).as_posix()}:{lineno}"
            target = REPO_ROOT / cited

            if not target.is_file():
                problems.append(f"{where}: cited file does not exist -> `{cited}`")
                continue

            lines = file_lines(target)
            n = len(lines)
            hi = max(start, end)
            if hi > n:
                problems.append(
                    f"{where}: `{cited}` cites line {hi} but the file has {n} lines"
                )
                continue

            if anchor is not None:
                # Lines are 1-based in citations; slice the inclusive [start, end] range.
                cited_text = "\n".join(lines[start - 1 : end])
                if anchor not in cited_text:
                    shown = cited_text.strip().replace("\n", " / ")
                    if len(shown) > 120:
                        shown = shown[:117] + "..."
                    problems.append(
                        f"{where}: `{cited}:{start}"
                        + (f"-{end}" if end != start else "")
                        + f"` anchored on \"{anchor}\" but those lines now read: \"{shown}\""
                        + " — re-point the citation and confirm it still describes current behaviour."
                    )
    return problems


def main() -> int:
    # The guard's own output must never crash on a non-UTF-8 console (Windows cp1252),
    # or a real drift failure turns into an unrelated UnicodeEncodeError. Force UTF-8.
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")

    all_problems: list[str] = []
    for name in LIVING_SPECS:
        doc = DOCS_DIR / name
        if not doc.is_file():
            continue
        all_problems.extend(check_doc(doc))
    if all_problems:
        print("Dead/misanchored `file:line` citation(s) — docs have drifted from the code:\n")
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
