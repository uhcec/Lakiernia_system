"""Pure unit tests for the shared-stage surface-prep interleave derivation (N49-10)."""

from app.process.enums import ProductionType
from app.process.shared_stage import PrepCandidate, derive_surface_preparation_order


def _candidate(work_order_id: int, line: ProductionType, rank: int, pieces: int = 10) -> PrepCandidate:
    return PrepCandidate(
        work_order_id=work_order_id,
        production_type=line,
        plan_rank=(False, rank),
        pieces=pieces,
    )


def test_empty_yields_empty() -> None:
    assert derive_surface_preparation_order([], {}) == []


def test_within_line_order_follows_plan_rank() -> None:
    candidates = [
        _candidate(2, ProductionType.AUTOMATIC, rank=2),
        _candidate(1, ProductionType.AUTOMATIC, rank=1),
    ]
    # Single line: prep follows its own painting-plan order regardless of input order.
    assert derive_surface_preparation_order(candidates, {}) == [1, 2]


def test_smaller_buffer_line_is_fed_first() -> None:
    # Automatic already has a big prepared-but-not-yet-painted buffer; manual is starving, so manual
    # gets prepped first even though both have a candidate ready.
    candidates = [
        _candidate(10, ProductionType.AUTOMATIC, rank=1, pieces=5),
        _candidate(20, ProductionType.MANUAL, rank=1, pieces=5),
    ]
    order = derive_surface_preparation_order(
        candidates,
        {ProductionType.AUTOMATIC: 100, ProductionType.MANUAL: 0},
    )
    assert order[0] == 20  # the starving (manual) line first


def test_tie_goes_to_automatic() -> None:
    # Equal buffers and equal piece sizes -> the head goes to automatic (primary resource).
    candidates = [
        _candidate(20, ProductionType.MANUAL, rank=1, pieces=10),
        _candidate(10, ProductionType.AUTOMATIC, rank=1, pieces=10),
    ]
    order = derive_surface_preparation_order(candidates, {})
    assert order[0] == 10  # automatic wins the tie


def test_interleave_rebalances_as_pieces_enter_buffer() -> None:
    # Both lines start empty with equal-size orders. First pick is automatic (tie). That adds its pieces
    # to automatic's buffer, so the next pick swings to manual, then back, producing an alternation.
    candidates = [
        _candidate(1, ProductionType.AUTOMATIC, rank=1, pieces=10),
        _candidate(2, ProductionType.AUTOMATIC, rank=2, pieces=10),
        _candidate(3, ProductionType.MANUAL, rank=1, pieces=10),
        _candidate(4, ProductionType.MANUAL, rank=2, pieces=10),
    ]
    order = derive_surface_preparation_order(candidates, {})
    assert order == [1, 3, 2, 4]


def test_uneven_pieces_keep_the_lighter_line_filling() -> None:
    # Automatic orders are tiny; manual is huge. After one big manual order, automatic keeps getting
    # fed until its running buffer catches up.
    candidates = [
        _candidate(1, ProductionType.MANUAL, rank=1, pieces=100),
        _candidate(2, ProductionType.AUTOMATIC, rank=1, pieces=10),
        _candidate(3, ProductionType.AUTOMATIC, rank=2, pieces=10),
        _candidate(4, ProductionType.AUTOMATIC, rank=3, pieces=10),
    ]
    order = derive_surface_preparation_order(candidates, {})
    # Tie at start -> automatic head; manual (100) then dwarfs the tiny automatic buffer, so the
    # remaining automatic orders run before the next manual would (no more manual here).
    assert order[0] == 2
    assert set(order) == {1, 2, 3, 4}
    # Automatic orders stay in their plan order.
    assert [o for o in order if o in (2, 3, 4)] == [2, 3, 4]
