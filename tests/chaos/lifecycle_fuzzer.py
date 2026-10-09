"""Lifecycle fuzzer (CHANGES #14 follow-up; independent review 2026-07-11 §2 recommendation).

The citation-guarded spec proves individual rules exist; nothing proves behaviours COMPOSE — the
undercount chain (#12) and the DONE-restart hole (#14) were both composites of individually
owner-confirmed rules. This fuzzer drives random *legal* action sequences through the real HTTP
API and asserts the global invariants after EVERY step, so a composite that corrupts state fails
loudly with the seed + step that produced it.

Deterministic: seeded ``random.Random``, no wall-clock dependence — a failure reproduces exactly.

The walker is state-aware (it reads the order's detail and picks a plausible next action) so runs
actually reach completions — including intake undercounts (counted < ordered), correction rounds
(RAL replan-in-place and DECORAL children), Decoral merges, and administrative resets. A slice of
deliberately *hostile* pokes (restarting DONE stages, replanning, random queue moves) exercises
the guards; a controlled rejection (409/422) is a legal outcome, a raw 500 or a broken invariant
is not.
"""

from __future__ import annotations

import random

from tests.chaos.harness import ChaosEnvironment, LoggedApiClient
from tests.chaos.invariants import assert_global_invariants


def _build_create_payload(rng: random.Random, index: int) -> dict:
    coating_type = rng.choice(["RAL", "RAL", "RAL", "DECORAL"])
    return {
        "title": f"Fuzz {index}",
        "coating_type": coating_type,
        "total_quantity": rng.randint(1, 8),
        "customer_name": "FUZZ",
        "ral_code": rng.choice(["RAL 7016", "RAL 9010", "RAL 3020"]),
        "paint_code": "P-FUZZ",
        "paint_producer": "AkzoNobel",
        "received_date": "2026-07-01",
        "planned_pickup_date": "2026-07-20",
        "total_area_m2": float(rng.randint(5, 40)),
        "profiles_to_count": True,
        "accessories_to_count": True,
        "is_incomplete_on_arrival": rng.random() < 0.1,
    }


class LifecycleFuzzer:
    def __init__(self, env: ChaosEnvironment, seed: int, steps: int) -> None:
        self.env = env
        self.rng = random.Random(seed)
        self.seed = seed
        self.steps = steps
        self.client: LoggedApiClient = env.create_actor_client(f"LifecycleFuzzer-{seed}")
        self.order_ids: list[int] = []
        self.created_count = 0

    # --- helpers ------------------------------------------------------------------------------

    def _detail(self, order_id: int) -> dict | None:
        response = self.client.get(f"/work-orders/{order_id}")
        if response.status_code != 200:
            return None
        return response.json()

    def _stage_status(self, detail: dict, stage: str) -> str | None:
        for stage_state in detail["stage_states"]:
            if stage_state["stage"]["value"] == stage:
                return stage_state["status"]["value"]
        return None

    def _prep_counted(self, detail: dict) -> int | None:
        for stage_state in detail["stage_states"]:
            if stage_state["stage"]["value"] == "SURFACE_PREPARATION":
                return stage_state.get("counted_quantity")
        return None

    def _discover_unplanned(self) -> None:
        """Correction children are born unplanned and invisible to the office list — adopt them."""
        response = self.client.get("/manager/work-orders/unplanned")
        if response.status_code != 200:
            return
        for item in response.json():
            if item["id"] not in self.order_ids:
                self.order_ids.append(item["id"])

    # --- the walk -----------------------------------------------------------------------------

    def _create_order(self) -> None:
        self.created_count += 1
        response = self.client.post("/work-orders", json=_build_create_payload(self.rng, self.created_count))
        if response.status_code == 201:
            self.order_ids.append(response.json()["id"])

    def _hostile_poke(self, detail: dict) -> None:
        """Deliberately off-script actions — the guards must answer 409, never corrupt state."""
        order_id = detail["id"]
        poke = self.rng.choice(["restart_done", "reopen", "replan", "queue_move", "line_switch", "admin_reset"])
        if poke == "restart_done":
            done_stages = [s["stage"]["value"] for s in detail["stage_states"] if s["status"]["value"] == "DONE"]
            if done_stages:
                stage = self.rng.choice(done_stages)
                body = {"counted_quantity": self.rng.randint(1, 5)} if stage == "SURFACE_PREPARATION" else None
                self.client.post(f"/process/work-orders/{order_id}/stages/{stage}/start", json=body)
        elif poke == "reopen":
            stage = self.rng.choice([s["stage"]["value"] for s in detail["stage_states"]] or ["PACKING"])
            self.client.post(f"/process/work-orders/{order_id}/stages/{stage}/reopen")
        elif poke == "replan":
            self.client.post(
                f"/manager/work-orders/{order_id}/plan",
                json={"production_type": self.rng.choice(["MANUAL", "AUTOMATIC"]), "queue_position": self.rng.randint(1, 10)},
            )
        elif poke == "queue_move":
            self.client.patch(
                f"/manager/work-orders/{order_id}/queue-position",
                json={"queue_position": self.rng.randint(1, 10)},
            )
        elif poke == "line_switch":
            self.client.patch(
                f"/manager/work-orders/{order_id}/production-type",
                json={"production_type": self.rng.choice(["MANUAL", "AUTOMATIC"])},
            )
        elif poke == "admin_reset":
            self.client.post(f"/work-orders/{order_id}/administrative-reset")

    def _record_some_paint_run(self) -> None:
        """Enter consumption for a random open paint run (CHANGES #22) — sometimes while one of its
        orders is still hanging, which the guard must refuse."""
        runs = self.client.get("/process/paint-runs/open").json()["runs"]
        if not runs:
            return
        run = self.rng.choice(runs)
        self.client.post(
            f"/process/paint-runs/{run['id']}/consumption",
            json={"consumed_kg": round(self.rng.uniform(0.5, 8.0), 1)},
        )

    def _complete_packing(self, detail: dict) -> None:
        order_id = detail["id"]
        counted = self._prep_counted(detail)
        if counted is None:
            # Correction rounds / prep-skipping orders pack their active batch size.
            counted = detail["current_active_quantity"]
        if counted <= 0:
            return
        ok_quantity = self.rng.randint(0, counted)
        correction_quantity = counted - ok_quantity
        payload: dict = {
            "counted_quantity": counted,
            "ok_quantity": ok_quantity,
            "correction_quantity": correction_quantity,
        }
        if correction_quantity > 0:
            payload["correction_profiles_quantity"] = correction_quantity
            payload["correction_accessories_quantity"] = 0
            payload["correction_reason_category"] = "niedomalowanie"
        self.client.post(f"/process/work-orders/{order_id}/packing/complete", json=payload)

    def _advance_decoral(self, order_id: int) -> None:
        """Work a random not-DONE Decoral batch from the station board."""
        board = self.client.get("/process/stages/DECORAL_PRODUCTION/work-orders")
        if board.status_code != 200:
            return
        rows = [
            row
            for row in board.json()
            if row["id"] == order_id and row["stage_status"]["status"]["value"] != "DONE" and row.get("batch_id")
        ]
        if not rows:
            return
        row = self.rng.choice(rows)
        batch_id = row["batch_id"]
        if row["stage_status"]["status"]["value"] == "NOT_STARTED":
            self.client.post(f"/process/work-orders/{order_id}/batches/{batch_id}/stages/DECORAL_PRODUCTION/start")
        else:
            active = row.get("batch_quantity") or 1
            ok_quantity = self.rng.randint(0, active)
            correction_quantity = active - ok_quantity
            payload = {"ok_quantity": ok_quantity, "correction_quantity": correction_quantity}
            self.client.post(
                f"/process/work-orders/{order_id}/batches/{batch_id}/decoral-production/complete",
                json=payload,
            )

    def _advance(self, detail: dict) -> None:
        """Pick a plausible forward action for the order's current state."""
        order_id = detail["id"]
        status = detail["process_status"]["value"]

        if status == "INCOMPLETE":
            self.client.post(f"/work-orders/{order_id}/mark-complete-arrival")
            return
        if status == "TO_BE_PLANNED":
            payload: dict = {"production_type": self.rng.choice(["MANUAL", "MANUAL", "AUTOMATIC"])}
            if self.rng.random() < 0.4:
                payload["queue_position"] = self.rng.randint(1, 6)
            self.client.post(f"/manager/work-orders/{order_id}/plan", json=payload)
            return

        prep = self._stage_status(detail, "SURFACE_PREPARATION")
        if prep == "NOT_STARTED":
            # Random count up to the active quantity — intake undercounts arise naturally here.
            active = max(1, detail["current_active_quantity"])
            self.client.post(
                f"/process/work-orders/{order_id}/stages/SURFACE_PREPARATION/start",
                json={"counted_quantity": self.rng.randint(1, active)},
            )
            return
        if prep == "IN_PROGRESS":
            self.client.post(f"/process/work-orders/{order_id}/stages/SURFACE_PREPARATION/finish")
            return

        production_type = (detail.get("production_type") or {}).get("value")
        if production_type == "AUTOMATIC":
            hanging = self._stage_status(detail, "HANGING")
            if hanging == "NOT_STARTED":
                self.client.post(f"/process/work-orders/{order_id}/stages/HANGING/start")
                return
            if hanging == "IN_PROGRESS":
                if self.rng.random() < 0.5:
                    self._record_some_paint_run()
                else:
                    self.client.post(f"/process/work-orders/{order_id}/stages/HANGING/finish")
                return
            packing = self._stage_status(detail, "PACKING")
            if packing in {"NOT_STARTED", "IN_PROGRESS"}:
                if self.rng.random() < 0.3:
                    self._record_some_paint_run()
                else:
                    self._complete_packing(detail)
                return
        else:
            production = self._stage_status(detail, "PRODUCTION")
            if production == "NOT_STARTED":
                self.client.post(f"/process/work-orders/{order_id}/stages/PRODUCTION/start")
                return
            if production == "IN_PROGRESS":
                self.client.post(f"/process/work-orders/{order_id}/stages/PRODUCTION/finish")
                return
            packing = self._stage_status(detail, "PACKING")
            if packing == "NOT_STARTED":
                self.client.post(f"/process/work-orders/{order_id}/stages/PACKING/start")
                return
            if packing == "IN_PROGRESS":
                self._complete_packing(detail)
                return

        if status in {"DECORAL_PRODUCTION", "WAITING_FOR_CORRECTIONS"} or self._stage_status(detail, "DECORAL_PRODUCTION") is not None:
            self._advance_decoral(order_id)

    def step(self) -> None:
        if not self.order_ids or self.rng.random() < 0.12:
            self._create_order()
            return
        if self.rng.random() < 0.25:
            self._discover_unplanned()

        order_id = self.rng.choice(self.order_ids)
        detail = self._detail(order_id)
        if detail is None:
            return
        if detail["process_status"]["value"] == "READY":
            # Completed orders are mostly left alone; occasionally poke them (guards must hold).
            if self.rng.random() < 0.3:
                self._hostile_poke(detail)
            return
        if self.rng.random() < 0.15:
            self._hostile_poke(detail)
        else:
            self._advance(detail)

    def run(self) -> None:
        for step_index in range(self.steps):
            self.step()
            with self.env.create_session() as session:
                try:
                    assert_global_invariants(session, self.env.event_log)
                except AssertionError as exc:  # pragma: no cover - failure path
                    last = self.env.event_log[-1] if self.env.event_log else None
                    last_text = f"{last.method} {last.path} -> {last.status_code}" if last else "<no events>"
                    raise AssertionError(
                        f"Lifecycle fuzz seed={self.seed} broke an invariant at step {step_index + 1} "
                        f"(last action: {last_text}): {exc}"
                    ) from exc


def run_lifecycle_fuzz(env: ChaosEnvironment, *, seed: int, steps: int = 120) -> None:
    LifecycleFuzzer(env, seed, steps).run()
