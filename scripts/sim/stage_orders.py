"""Mechanically advance work orders through the process pipeline to POPULATE downstream stations.

The black-box personas explore freely, so a single pass barely moves an order one stage — which leaves
the downstream station panels (hanging, production, packing) empty and untestable. This is the
controller's mechanical job: drive a few orders forward via the real API (as the correct station user
each step) so each persona lands on a page that actually has work. It makes NO UX decisions; it just
positions the factory state. Run in-process (calls sim_client.call) so Git-Bash path mangling and JWT
plumbing are sidestepped.

Usage (SIM_BASE_URL must point at the sim backend):
    python scripts/sim/stage_orders.py 0003:HANGING 0001:PRODUCTION 0002:PACKING

Each "ORDER:STAGE" lands that order so its CURRENT stage is STAGE (i.e. it finishes every stage BEFORE
STAGE and sits, not-yet-started, in STAGE's queue). Prints the resulting status per order. Tolerant of
steps already done. Stages: SURFACE_PREPARATION < HANGING < PRODUCTION < PACKING.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # scripts/ for sim_client
import sim_client  # noqa: E402

# Linear automatic-line path and the station user authorised to act at each stage.
PIPELINE = ["SURFACE_PREPARATION", "HANGING", "PRODUCTION", "PACKING"]
STAGE_LOGIN = {
    "SURFACE_PREPARATION": "przygotowanie",
    "HANGING": "zawieszanie",
    "PRODUCTION": "produkcja-automat",
    "PACKING": "pakowanie",
}


def _order_index() -> dict[str, dict]:
    status, data = sim_client.call("admin", "GET", "/work-orders")
    rows = data.get("items") if isinstance(data, dict) else data
    return {r["order_number"]: r for r in rows} if isinstance(rows, list) else {}


def _status_of(order_id: int) -> str | None:
    status, order = sim_client.call("admin", "GET", f"/work-orders/{order_id}")
    if isinstance(order, dict):
        ps = order.get("process_status")
        return ps.get("value") if isinstance(ps, dict) else ps
    return None


def _finish_stage(order_id: int, stage: str, counted: int | None) -> tuple[bool, str]:
    """start (tolerant) then finish one stage as the authorised station user."""
    login = STAGE_LOGIN[stage]
    body = {"counted_quantity": counted} if counted is not None else None
    sim_client.call(login, "POST", f"/process/work-orders/{order_id}/stages/{stage}/start", body)
    status, resp = sim_client.call(login, "POST", f"/process/work-orders/{order_id}/stages/{stage}/finish", body)
    if 200 <= status < 300:
        return True, "ok"
    detail = resp.get("detail") if isinstance(resp, dict) else resp
    return False, f"HTTP {status}: {detail}"


def advance(order_number: str, target_stage: str, index: dict[str, dict]) -> str:
    row = index.get(order_number)
    if not row:
        return f"{order_number} -> NOT FOUND"
    order_id = row["id"]
    total = row.get("total_quantity")
    if target_stage not in PIPELINE:
        return f"{order_number} -> unknown stage {target_stage}"
    # Finish every stage strictly before the target so the order comes to rest in the target's queue.
    for stage in PIPELINE[: PIPELINE.index(target_stage)]:
        ok, msg = _finish_stage(order_id, stage, total)
        if not ok:
            return f"{order_number} (id {order_id}) blocked finishing {stage}: {msg} | now={_status_of(order_id)}"
    return f"{order_number} (id {order_id}) -> {_status_of(order_id)}"


def main(argv: list[str]) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    if not argv:
        print("usage: stage_orders.py ORDER:STAGE [ORDER:STAGE ...]")
        return 2
    index = _order_index()
    for spec in argv:
        order_number, _, stage = spec.partition(":")
        print(advance(order_number, stage, index))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
