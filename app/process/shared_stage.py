"""Pure derivation of the order shown at the two **shared** process stages (N49-10).

The painting plan is scheduled per line (``queue_position`` is unique only within a
``production_type``), which is correct for the two parallel painting resources (one manual station, one
automatic booth). But two stages are physically **shared**:

- ``SURFACE_PREPARATION`` — ONE prep station feeds BOTH booths, so its order is a single interleaved
  sequence across both lines, NOT two independent per-line ranks.
- ``PACKING`` — ONE packing drain; order follows physical readiness + the packing-slot model, with no
  manual position numbering.

Rendering the raw per-line ``queue_position`` as a global rank at these stages made two physically
different orders (one MANUAL, one AUTOMATIC) both show "Poz. 1" / "Poz. 2" — an ambiguous duplicate, and
an interleave decided by insertion order rather than factory priority. This module derives the real
shared-stage order so the read model can own it and the frontend can render a line label + a meaningful
sequence instead of a colliding position number.

It is deliberately DB-free (mirrors ``app/manager/scheduler.py`` / ``capacity.py``): it takes plain value
objects and returns an ordering, so the derivation is fully unit-testable.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from app.process.enums import ProductionType


@dataclass(frozen=True)
class PrepCandidate:
    """An order waiting at surface preparation (un-prepped), projected for the buffer interleave.

    ``plan_rank`` is the order's rank within its own line's painting plan (its ``queue_position``, with
    ``None`` sorting last) — the *within-line* order in which that booth will consume parts.
    ``pieces`` is the operational piece count it will add to its line's prepared-but-not-yet-painted
    buffer once prepped (buffer is measured in **pieces** — owner assumption, revisit).
    """

    work_order_id: int
    production_type: ProductionType
    plan_rank: tuple[bool, int]
    pieces: int


def _line_sort_key(candidate: PrepCandidate) -> tuple:
    # Deterministic within-line order: by the painting-plan rank, then id as a stable final tie-break.
    return (candidate.plan_rank, candidate.work_order_id)


def derive_surface_preparation_order(
    candidates: Sequence[PrepCandidate],
    initial_buffer_pieces: dict[ProductionType, int],
) -> list[int]:
    """Return the interleaved surface-prep order of work-order ids across both lines.

    Rule (owner-confirmed 2026-06-23): prep next for the line with the **smaller** prepared-but-not-yet-
    painted buffer (the line closest to starving its booth); ties go to **automatic** (the primary,
    higher-throughput resource). Within a line the candidate is the next un-prepped order in that line's
    painting plan. After a line's order is chosen it is treated as entering that line's buffer (its pieces
    are added), so the next decision re-balances live.
    """
    per_line: dict[ProductionType, list[PrepCandidate]] = {}
    for candidate in candidates:
        per_line.setdefault(candidate.production_type, []).append(candidate)
    for orders in per_line.values():
        orders.sort(key=_line_sort_key)

    # Index of the next un-prepped candidate per line, and the running buffer (seeded with the orders
    # already prepped but not yet painted).
    next_index: dict[ProductionType, int] = {line: 0 for line in per_line}
    buffer: dict[ProductionType, int] = {
        line: int(initial_buffer_pieces.get(line, 0)) for line in per_line
    }

    ordered_ids: list[int] = []
    while True:
        ready_lines = [line for line, idx in next_index.items() if idx < len(per_line[line])]
        if not ready_lines:
            break
        # Smaller buffer first; tie -> automatic (False sorts before True so automatic wins).
        chosen_line = min(
            ready_lines,
            key=lambda line: (buffer[line], line is not ProductionType.AUTOMATIC),
        )
        candidate = per_line[chosen_line][next_index[chosen_line]]
        ordered_ids.append(candidate.work_order_id)
        next_index[chosen_line] += 1
        buffer[chosen_line] += candidate.pieces

    return ordered_ids
