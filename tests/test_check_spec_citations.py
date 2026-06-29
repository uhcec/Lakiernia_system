"""Unit tests for the anti-drift citation guard (``scripts/check_spec_citations.py``).

Pins the two guard levels: existence/range (legacy) and the anchored content check (the upgrade),
plus backward-compatibility for un-anchored citations.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_MODULE_PATH = Path(__file__).resolve().parent.parent / "scripts" / "check_spec_citations.py"
_spec = importlib.util.spec_from_file_location("check_spec_citations", _MODULE_PATH)
assert _spec and _spec.loader
checker = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(checker)


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A fake repo root so ``check_doc`` resolves cited paths under ``tmp_path``."""
    monkeypatch.setattr(checker, "REPO_ROOT", tmp_path)
    return tmp_path


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _target(repo: Path) -> None:
    # A small target file: assign_plan spans lines 1-3, a constant on line 5.
    _write(
        repo / "app/mod.py",
        "def assign_plan(self):\n    return self._plan()  # the plan\n\n\nTHRESHOLD = 100.0\n",
    )


def test_unanchored_citation_passes_when_in_range(repo: Path) -> None:
    _target(repo)
    doc = _write(repo / "docs/SPEC.md", "- behaviour `app/mod.py:2`")
    assert checker.check_doc(doc) == []


def test_missing_file_is_flagged(repo: Path) -> None:
    doc = _write(repo / "docs/SPEC.md", "- behaviour `app/gone.py:5`")
    problems = checker.check_doc(doc)
    assert problems and "does not exist" in problems[0]


def test_out_of_range_line_is_flagged(repo: Path) -> None:
    _target(repo)  # 5 lines
    doc = _write(repo / "docs/SPEC.md", "- behaviour `app/mod.py:99`")
    problems = checker.check_doc(doc)
    assert problems and "has 5 lines" in problems[0]


def test_matching_anchor_passes(repo: Path) -> None:
    _target(repo)
    doc = _write(repo / "docs/SPEC.md", "- plan assign `app/mod.py:1-3@def assign_plan`")
    assert checker.check_doc(doc) == []


def test_anchor_on_constant_passes(repo: Path) -> None:
    _target(repo)
    doc = _write(repo / "docs/SPEC.md", "- threshold `app/mod.py:5@THRESHOLD`")
    assert checker.check_doc(doc) == []


def test_mismatched_anchor_is_flagged(repo: Path) -> None:
    # The anchor token is no longer on the cited lines → content drift.
    _target(repo)
    doc = _write(repo / "docs/SPEC.md", "- plan assign `app/mod.py:5@def assign_plan`")
    problems = checker.check_doc(doc)
    assert len(problems) == 1
    assert "anchored on" in problems[0]
    assert "def assign_plan" in problems[0]
    # The message shows what the cited line actually reads, to aid re-pointing.
    assert "THRESHOLD" in problems[0]


def test_anchor_out_of_range_reports_range_not_anchor(repo: Path) -> None:
    # Range failure takes precedence over the (un-checkable) anchor.
    _target(repo)
    doc = _write(repo / "docs/SPEC.md", "- x `app/mod.py:50@whatever`")
    problems = checker.check_doc(doc)
    assert problems and "has 5 lines" in problems[0]
