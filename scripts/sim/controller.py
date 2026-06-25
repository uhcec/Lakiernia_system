"""Clock + bookkeeping for the workflow simulation (the mechanical half of the harness).

This controller owns *nothing* about what any station decides. It advances the dev virtual clock, takes
queue snapshots so the orchestrator knows which stations have work, runs the invariant auditor, and
appends to the run's timeline. The actual decisions are made by the live persona agents (one per
station), which act through ``scripts/sim_client.py``. Drive it sequentially — one backend worker (NA8).

Subcommands (all print JSON to stdout):

    init-run [--start ISO]      create runs/<ts>/, freeze the clock at the shift start, mark it LATEST
    clock get|set|advance       read / freeze / step the dev virtual clock (/dev/clock)
    snapshot                     per-stage queues + unplanned + planned: who has work this tick
    audit [--run DIR]            run invariants over every known order; append violations to invariants.md
    event --json '{...}'         append one decision to the run's timeline.jsonl (stamped with sim time)

Requires the backend running (single worker, APP_ENV=development) and the dev clock router mounted.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS_DIR = _REPO_ROOT / "scripts"
sys.path.insert(0, str(_SCRIPTS_DIR))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import sim_client  # noqa: E402  (path set up above)
import auditor  # noqa: E402

_RUNS_DIR = Path(__file__).resolve().parent / "runs"
_LATEST = _RUNS_DIR / "LATEST"

STAGES = ["SURFACE_PREPARATION", "HANGING", "PRODUCTION", "PACKING", "DECORAL_PRODUCTION"]


# --- dev virtual clock ---------------------------------------------------------------------------

def _clock_get() -> dict:
    status, data = sim_client.call("admin", "GET", "/dev/clock")
    if status != 200:
        raise SystemExit(f"GET /dev/clock failed ({status}): {data}")
    return data


def _clock_set(when: datetime) -> dict:
    status, data = sim_client.call("admin", "PUT", "/dev/clock", {"now": when.isoformat()})
    if status != 200:
        raise SystemExit(f"PUT /dev/clock failed ({status}): {data}")
    return data


def _sim_now() -> datetime:
    return datetime.fromisoformat(_clock_get()["now"])


# --- run bookkeeping -----------------------------------------------------------------------------

def _resolve_run(run: str | None) -> Path:
    if run:
        return Path(run)
    if _LATEST.exists():
        return Path(_LATEST.read_text("utf-8").strip())
    raise SystemExit("No run specified and no LATEST run found. Call init-run first.")


def _known_orders_path(run_dir: Path) -> Path:
    return run_dir / "known_orders.json"


def _load_json(path: Path, default):
    try:
        return json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        return default


def _record_known_orders(run_dir: Path, ids: set[int]) -> set[int]:
    path = _known_orders_path(run_dir)
    known = set(_load_json(path, []))
    known |= ids
    path.write_text(json.dumps(sorted(known)), "utf-8")
    return known


# --- snapshot ------------------------------------------------------------------------------------

def _slim(order: dict) -> dict:
    return {
        "id": order.get("id"),
        "order_number": order.get("order_number"),
        "customer_name": order.get("customer_name"),
        "process_status": auditor._status_value(order),
        "production_type": auditor._production_type_value(order),
        "queue_position": order.get("queue_position"),
        "total_quantity": order.get("total_quantity"),
        "completed_quantity": order.get("completed_quantity"),
    }


def _snapshot(run_dir: Path | None) -> dict:
    snap: dict = {"sim_time": _clock_get()["now"], "stages": {}, "unplanned": [], "planned": []}
    seen: set[int] = set()

    for stage in STAGES:
        status, data = sim_client.call("admin", "GET", f"/process/stages/{stage}/work-orders")
        rows = data if isinstance(data, list) else []
        snap["stages"][stage] = [
            {"id": r.get("id"), "order_number": r.get("order_number"), "customer_name": r.get("customer_name")}
            for r in rows
        ]
        seen |= {r["id"] for r in rows if r.get("id")}

    for key, path in (("unplanned", "/manager/work-orders/unplanned"), ("planned", "/manager/work-orders")):
        status, data = sim_client.call("admin", "GET", path)
        rows = data if isinstance(data, list) else []
        snap[key] = [_slim(r) for r in rows]
        seen |= {r["id"] for r in rows if r.get("id")}

    if run_dir is not None:
        _record_known_orders(run_dir, seen)
    return snap


# --- audit ---------------------------------------------------------------------------------------

def _all_order_ids(run_dir: Path) -> list[int]:
    ids: set[int] = set(_load_json(_known_orders_path(run_dir), []))
    status, data = sim_client.call("admin", "GET", "/work-orders")
    rows = data.get("items") if isinstance(data, dict) else data
    if isinstance(rows, list):
        ids |= {r["id"] for r in rows if isinstance(r, dict) and r.get("id")}
    _record_known_orders(run_dir, ids)
    return sorted(ids)


def _audit(run_dir: Path) -> dict:
    sim_time = _clock_get()["now"]
    audit_state_path = run_dir / "audit_state.json"
    prev_completed: dict[str, int] = _load_json(audit_state_path, {})

    orders: list[dict] = []
    violations: list[str] = []
    # Worklist grows as we discover correction children (P-orders) — they are NOT in the default
    # /work-orders list, so following `correction_orders` is the only way to invariant-check them.
    to_check = list(_all_order_ids(run_dir))
    seen_ids: set[int] = set()
    while to_check:
        order_id = to_check.pop(0)
        if order_id in seen_ids:
            continue
        seen_ids.add(order_id)
        status, order = sim_client.call("admin", "GET", f"/work-orders/{order_id}")
        if status != 200 or not isinstance(order, dict):
            violations.append(f"[id {order_id}] could not be read back ({status})")
            continue
        orders.append(order)
        violations += auditor.check_order(order, prev_completed.get(str(order_id)))
        if isinstance(order.get("completed_quantity"), int):
            prev_completed[str(order_id)] = order["completed_quantity"]
        for child in order.get("correction_orders", []) or []:
            child_id = child.get("id")
            if isinstance(child_id, int) and child_id not in seen_ids:
                to_check.append(child_id)
    _record_known_orders(run_dir, seen_ids)

    violations += auditor.check_queue_uniqueness(orders)

    status, packing = sim_client.call("admin", "GET", "/process/stages/PACKING/work-orders")
    if isinstance(packing, list):
        violations += auditor.check_packing_slots(packing)

    audit_state_path.write_text(json.dumps(prev_completed), "utf-8")

    if violations:
        with (run_dir / "invariants.md").open("a", encoding="utf-8") as handle:
            handle.write(f"\n## Violations at sim time {sim_time}\n\n")
            for issue in violations:
                handle.write(f"- {issue}\n")

    return {"sim_time": sim_time, "orders_checked": len(orders), "violations": violations}


# --- timeline ------------------------------------------------------------------------------------

def _event(run_dir: Path, payload: dict) -> dict:
    record = {
        "sim_time": _clock_get()["now"],
        "wall_time": datetime.now(UTC).isoformat(),
        **payload,
    }
    with (run_dir / "timeline.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


# --- CLI ----------------------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    # The API speaks Polish; force UTF-8 so JSON output never dies on a legacy cp1252 console.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init-run", help="create a run dir and freeze the clock at the shift start")
    p_init.add_argument("--start", default="2026-06-22T07:00:00Z", help="ISO shift-start instant (default Mon 07:00)")

    p_clock = sub.add_parser("clock", help="read/freeze/step the dev virtual clock")
    p_clock.add_argument("action", choices=["get", "set", "advance"])
    p_clock.add_argument("--iso", help="ISO instant for 'set'")
    p_clock.add_argument("--minutes", type=int, default=0, help="minutes to step for 'advance'")

    sub.add_parser("snapshot", help="per-stage queues + unplanned + planned").add_argument(
        "--run", default=None, help="run dir (defaults to LATEST)"
    )

    sub.add_parser("audit", help="run invariants over every known order").add_argument(
        "--run", default=None, help="run dir (defaults to LATEST)"
    )

    p_event = sub.add_parser("event", help="append one decision to the run's timeline.jsonl")
    p_event.add_argument("--run", default=None)
    p_event.add_argument("--json", required=True, help="JSON object describing the action")

    args = parser.parse_args(argv)

    if args.command == "init-run":
        _RUNS_DIR.mkdir(parents=True, exist_ok=True)
        run_dir = _RUNS_DIR / datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        run_dir.mkdir(parents=True, exist_ok=True)
        _LATEST.write_text(str(run_dir), "utf-8")
        (run_dir / "friction.md").write_text("# Friction log\n\nUX gaps the personas hit during the run.\n", "utf-8")
        (run_dir / "invariants.md").write_text("# Invariant violations\n", "utf-8")
        state = _clock_set(datetime.fromisoformat(args.start.replace("Z", "+00:00")))
        print(json.dumps({"run_dir": str(run_dir), "clock": state}, indent=2))
        return 0

    if args.command == "clock":
        if args.action == "get":
            print(json.dumps(_clock_get(), indent=2))
        elif args.action == "set":
            if not args.iso:
                raise SystemExit("clock set requires --iso")
            print(json.dumps(_clock_set(datetime.fromisoformat(args.iso.replace("Z", "+00:00"))), indent=2))
        else:  # advance
            print(json.dumps(_clock_set(_sim_now() + timedelta(minutes=args.minutes)), indent=2))
        return 0

    if args.command == "snapshot":
        run_dir = Path(_LATEST.read_text("utf-8").strip()) if (args.run is None and _LATEST.exists()) else (
            Path(args.run) if args.run else None
        )
        print(json.dumps(_snapshot(run_dir), ensure_ascii=False, indent=2))
        return 0

    if args.command == "audit":
        print(json.dumps(_audit(_resolve_run(args.run)), ensure_ascii=False, indent=2))
        return 0

    if args.command == "event":
        print(json.dumps(_event(_resolve_run(args.run), json.loads(args.json)), ensure_ascii=False, indent=2))
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
