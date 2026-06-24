"""Invariant checks for the workflow simulation.

Pure functions over the backend's read models (``WorkOrderRead`` dicts and the PACKING stage read), so
they are unit-testable and the controller can run them after every action. Each check returns a list of
human-readable violation strings; an empty list means the invariant held.

These assert *durable* truths the backend promises (CLAUDE.md "Core domain model"), not workflow policy —
policy lives in ``docs/WORKFLOW.md`` and is judged by the personas, not here.
"""

from __future__ import annotations

# ProcessDisplayStatus values (app/process/enums.py). A status outside this set means the read model and
# the simulation disagree about the lifecycle vocabulary — itself a finding.
KNOWN_PROCESS_STATUSES = {
    "TO_BE_PLANNED", "INCOMPLETE", "SURFACE_PREPARATION", "HANGING", "PRODUCTION_MANUAL",
    "PRODUCTION_AUTOMATIC", "DECORAL_PRODUCTION", "PACKING", "WAITING_FOR_CORRECTIONS", "READY",
}


def _status_value(order: dict) -> str | None:
    status = order.get("process_status")
    if isinstance(status, dict):
        return status.get("value")
    return status


def _production_type_value(order: dict) -> str | None:
    production_type = order.get("production_type")
    if isinstance(production_type, dict):
        return production_type.get("value")
    return production_type


def check_order(order: dict, prev_completed: int | None) -> list[str]:
    """Per-order invariants from a full ``WorkOrderRead`` dict."""
    issues: list[str] = []
    number = order.get("order_number", order.get("id"))
    total = order.get("total_quantity")
    completed = order.get("completed_quantity")
    active = order.get("current_active_quantity")

    if isinstance(total, int) and isinstance(completed, int):
        if completed < 0 or completed > total:
            issues.append(f"[{number}] completed_quantity {completed} outside [0, {total}]")
    if prev_completed is not None and isinstance(completed, int) and completed < prev_completed:
        issues.append(f"[{number}] completed_quantity went backwards: {prev_completed} -> {completed}")
    if isinstance(active, int) and active < 0:
        issues.append(f"[{number}] current_active_quantity is negative: {active}")

    batches = order.get("batches") or []
    active_batches = [b for b in batches if b.get("is_active")]
    if len(active_batches) > 1:
        issues.append(f"[{number}] more than one active batch: {len(active_batches)} (one-active-batch invariant)")

    status = _status_value(order)
    if status is not None and status not in KNOWN_PROCESS_STATUSES:
        issues.append(f"[{number}] unknown process_status '{status}'")

    return issues


def check_queue_uniqueness(orders: list[dict]) -> list[str]:
    """``queue_position`` is unique within a production line (DB partial unique index)."""
    issues: list[str] = []
    seen: dict[tuple[str, int], object] = {}
    for order in orders:
        position = order.get("queue_position")
        line = _production_type_value(order)
        if position is None or line is None:
            continue
        key = (line, position)
        if key in seen:
            issues.append(
                f"queue_position {position} on line {line} held by both "
                f"{seen[key]} and {order.get('order_number', order.get('id'))}"
            )
        else:
            seen[key] = order.get("order_number", order.get("id"))
    return issues


def check_packing_slots(packing_reads: list[dict]) -> list[str]:
    """No more orders may physically hold the packing station than there are slots (NA22)."""
    holders = [r for r in packing_reads if r.get("holds_packing_slot")]
    if not holders:
        return []
    slots_total = max((r.get("packing_slots_total", 1) or 1) for r in holders)
    if len(holders) > slots_total:
        held = ", ".join(str(r.get("order_number", r.get("id"))) for r in holders)
        return [f"{len(holders)} orders hold a packing slot but only {slots_total} exist: {held}"]
    return []
