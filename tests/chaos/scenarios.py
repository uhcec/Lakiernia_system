from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from tests.chaos.actors import AttachmentAgent, ChaosAgent, ManagerAgent, OfficeAgent, PackingAgent, StageOperatorAgent
from tests.chaos.harness import ChaosEnvironment


def build_create_payload(title: str, *, coating_type: str = "RAL", total_quantity: int = 100) -> dict:
    return {
        "title": title,
        "coating_type": coating_type,
        "total_quantity": total_quantity,
        "customer_name": "ACME",
        "ral_code": "RAL 7016",
        "paint_producer": "AkzoNobel",
        "received_date": "2026-05-25",
        "profiles_to_count": True,
        "accessories_to_count": True,
    }


def create_work_order(client, title: str, *, coating_type: str = "RAL", total_quantity: int = 100) -> dict:
    response = client.post("/work-orders", json=build_create_payload(title, coating_type=coating_type, total_quantity=total_quantity))
    assert response.status_code == 201
    return response.json()


def synchronized_create_work_order(client, barrier: Barrier, title: str):
    barrier.wait()
    return client.post("/work-orders", json=build_create_payload(title))


def create_planned_work_order(
    client,
    title: str,
    queue_position: int,
    production_type: str = "MANUAL",
    *,
    coating_type: str = "RAL",
    total_quantity: int = 100,
) -> dict:
    created = create_work_order(client, title, coating_type=coating_type, total_quantity=total_quantity)
    response = client.post(
        f"/manager/work-orders/{created['id']}/plan",
        json={"production_type": production_type, "queue_position": queue_position},
    )
    assert response.status_code == 200
    return created


def start_surface_preparation(client, work_order_id: int, counted_quantity: int = 100):
    return client.post(
        f"/process/work-orders/{work_order_id}/stages/SURFACE_PREPARATION/start",
        json={"counted_quantity": counted_quantity},
    )


def advance_to_packing(client, work_order_id: int) -> None:
    detail = get_work_order_detail(client, work_order_id)
    if not detail["is_correction"]:
        start_surface_preparation(client, work_order_id, detail["current_active_quantity"])
        client.post(f"/process/work-orders/{work_order_id}/stages/SURFACE_PREPARATION/finish")

    detail = get_work_order_detail(client, work_order_id)
    if detail["production_type"]["value"] == "AUTOMATIC":
        client.post(f"/process/work-orders/{work_order_id}/stages/HANGING/start")
        return

    client.post(f"/process/work-orders/{work_order_id}/stages/PRODUCTION/start")
    client.post(f"/process/work-orders/{work_order_id}/stages/PRODUCTION/finish")
    client.post(f"/process/work-orders/{work_order_id}/stages/PACKING/start")


def synchronized_post(client, barrier: Barrier, path: str, **kwargs):
    barrier.wait()
    return client.post(path, **kwargs)


def get_direct_correction_children(client, parent_id: int) -> list[dict]:
    work_orders = client.get("/work-orders")
    assert work_orders.status_code == 200
    return [item for item in work_orders.json()["items"] if item["is_correction"] and item["parent_order"]["id"] == parent_id]


def get_work_order_detail(client, work_order_id: int) -> dict:
    response = client.get(f"/work-orders/{work_order_id}")
    assert response.status_code == 200
    return response.json()


def seed_three_planned_orders(env: ChaosEnvironment) -> list[dict]:
    seeder = env.create_actor_client("Seeder")
    return [
        create_planned_work_order(seeder, "Chaos Queue 1", 1),
        create_planned_work_order(seeder, "Chaos Queue 2", 2),
        create_planned_work_order(seeder, "Chaos Queue 3", 3),
    ]


def scenario_two_managers_reorder_same_queue(env: ChaosEnvironment):
    orders = seed_three_planned_orders(env)
    manager_a = ManagerAgent(env.create_actor_client("ManagerAgent-A"))
    manager_b = ManagerAgent(env.create_actor_client("ManagerAgent-B"))
    barrier = Barrier(2)

    queue_revision = manager_a.get_queue_revision()
    reorder_a = [
        {"work_order_id": orders[2]["id"], "queue_position": 1},
        {"work_order_id": orders[1]["id"], "queue_position": 2},
        {"work_order_id": orders[0]["id"], "queue_position": 3},
    ]
    reorder_b = [
        {"work_order_id": orders[1]["id"], "queue_position": 1},
        {"work_order_id": orders[0]["id"], "queue_position": 2},
        {"work_order_id": orders[2]["id"], "queue_position": 3},
    ]

    with ThreadPoolExecutor(max_workers=2) as executor:
        future_a = executor.submit(manager_a.synchronized_reorder, barrier, queue_revision=queue_revision, items=reorder_a)
        future_b = executor.submit(manager_b.synchronized_reorder, barrier, queue_revision=queue_revision, items=reorder_b)
    return [future_a.result(), future_b.result()]


def scenario_stale_queue_payload_submit(env: ChaosEnvironment):
    orders = seed_three_planned_orders(env)
    manager = ManagerAgent(env.create_actor_client("ManagerAgent"))
    chaos = ChaosAgent(env.create_actor_client("ChaosAgent"))
    barrier = Barrier(2)

    stale_revision = manager.get_queue_revision()
    fresh_items = [
        {"work_order_id": orders[1]["id"], "queue_position": 1},
        {"work_order_id": orders[2]["id"], "queue_position": 2},
        {"work_order_id": orders[0]["id"], "queue_position": 3},
    ]
    stale_items = [
        {"work_order_id": orders[2]["id"], "queue_position": 1},
        {"work_order_id": orders[0]["id"], "queue_position": 2},
        {"work_order_id": orders[1]["id"], "queue_position": 3},
    ]

    with ThreadPoolExecutor(max_workers=2) as executor:
        future_fresh = executor.submit(manager.synchronized_reorder, barrier, queue_revision=stale_revision, items=fresh_items)
        future_stale = executor.submit(
            chaos.reorder_with_stale_payload_after_barrier,
            barrier,
            queue_revision=stale_revision,
            items=stale_items,
        )
    return [future_fresh.result(), future_stale.result()]


def scenario_queue_position_patch_collides_with_bulk_reorder(env: ChaosEnvironment):
    orders = seed_three_planned_orders(env)
    manager_reorder = ManagerAgent(env.create_actor_client("ManagerAgent-Reorder"))
    manager_patch = ManagerAgent(env.create_actor_client("ManagerAgent-Patch"))
    barrier = Barrier(2)

    queue_revision = manager_reorder.get_queue_revision()
    reorder_items = [
        {"work_order_id": orders[2]["id"], "queue_position": 1},
        {"work_order_id": orders[1]["id"], "queue_position": 2},
        {"work_order_id": orders[0]["id"], "queue_position": 3},
    ]

    with ThreadPoolExecutor(max_workers=2) as executor:
        future_reorder = executor.submit(manager_reorder.synchronized_reorder, barrier, queue_revision=queue_revision, items=reorder_items)
        future_patch = executor.submit(
            manager_patch.synchronized_update_queue_position,
            barrier,
            orders[0]["id"],
            queue_position=4,
        )

    list_response, planned = manager_reorder.list_planned()
    assert list_response.status_code == 200
    planned_positions = [item["queue_position"] for item in planned]
    assert len(planned_positions) == len(set(planned_positions))

    return [future_reorder.result(), future_patch.result(), list_response]


def scenario_operator_double_finishes_same_stage(env: ChaosEnvironment):
    seeder = env.create_actor_client("Seeder")
    created = create_planned_work_order(seeder, "Double Finish", 1)

    operator_a = StageOperatorAgent(env.create_actor_client("StageOperatorAgent-A"))
    operator_b = StageOperatorAgent(env.create_actor_client("StageOperatorAgent-B"))
    start_response = operator_a.start_surface_preparation(created["id"], 100)
    assert start_response.status_code == 200

    barrier = Barrier(2)
    with ThreadPoolExecutor(max_workers=2) as executor:
        future_a = executor.submit(operator_a.synchronized_finish_surface_preparation, barrier, created["id"])
        future_b = executor.submit(operator_b.synchronized_finish_surface_preparation, barrier, created["id"])
    return [future_a.result(), future_b.result()]


def scenario_double_click_packing_complete(env: ChaosEnvironment):
    seeder = env.create_actor_client("Seeder")
    created = create_planned_work_order(seeder, "Double Packing Complete", 1)
    advance_to_packing(seeder, created["id"])

    packing_a = PackingAgent(env.create_actor_client("PackingAgent-A"))
    packing_b = PackingAgent(env.create_actor_client("PackingAgent-B"))
    barrier = Barrier(2)

    with ThreadPoolExecutor(max_workers=2) as executor:
        future_a = executor.submit(
            packing_a.synchronized_complete_packing,
            barrier,
            created["id"],
            counted_quantity=100,
            ok_quantity=100,
            correction_quantity=0,
        )
        future_b = executor.submit(
            packing_b.synchronized_complete_packing,
            barrier,
            created["id"],
            counted_quantity=100,
            ok_quantity=100,
            correction_quantity=0,
        )
    return [future_a.result(), future_b.result()]


def scenario_packing_creates_correction_while_manager_reorders(env: ChaosEnvironment):
    orders = seed_three_planned_orders(env)
    seeder = env.create_actor_client("Seeder-Packing")
    parent = create_planned_work_order(seeder, "Packing Reorder Parent", 4)
    advance_to_packing(seeder, parent["id"])

    manager = ManagerAgent(env.create_actor_client("ManagerAgent"))
    packing = PackingAgent(env.create_actor_client("PackingAgent"))
    barrier = Barrier(2)
    queue_revision = manager.get_queue_revision()
    reorder_items = [
        {"work_order_id": orders[1]["id"], "queue_position": 1},
        {"work_order_id": orders[2]["id"], "queue_position": 2},
        {"work_order_id": parent["id"], "queue_position": 3},
        {"work_order_id": orders[0]["id"], "queue_position": 4},
    ]

    with ThreadPoolExecutor(max_workers=2) as executor:
        future_reorder = executor.submit(manager.synchronized_reorder, barrier, queue_revision=queue_revision, items=reorder_items)
        future_packing = executor.submit(
            packing.synchronized_complete_packing,
            barrier,
            parent["id"],
            counted_quantity=100,
            ok_quantity=90,
            correction_quantity=10,
        )
    return [future_reorder.result(), future_packing.result()]


def scenario_repeated_correction_split_does_not_duplicate_child(env: ChaosEnvironment):
    seeder = env.create_actor_client("Seeder")
    created = create_planned_work_order(seeder, "Repeated Correction Split", 1)
    advance_to_packing(seeder, created["id"])

    packing_a = PackingAgent(env.create_actor_client("PackingAgent-A"))
    packing_b = PackingAgent(env.create_actor_client("PackingAgent-B"))
    barrier = Barrier(2)

    with ThreadPoolExecutor(max_workers=2) as executor:
        future_a = executor.submit(
            packing_a.synchronized_complete_packing,
            barrier,
            created["id"],
            counted_quantity=100,
            ok_quantity=85,
            correction_quantity=15,
        )
        future_b = executor.submit(
            packing_b.synchronized_complete_packing,
            barrier,
            created["id"],
            counted_quantity=100,
            ok_quantity=85,
            correction_quantity=15,
        )

    children = get_direct_correction_children(seeder, created["id"])
    assert len(children) <= 1
    return [future_a.result(), future_b.result()]


def scenario_parallel_normal_and_correction_creation(env: ChaosEnvironment):
    seeder = env.create_actor_client("Seeder-Mixed-Creation")
    parent = create_planned_work_order(seeder, "Mixed Creation Parent", 1)
    advance_to_packing(seeder, parent["id"])

    creators = [env.create_actor_client(f"OfficeCreator-{index}") for index in range(1, 4)]
    packing = PackingAgent(env.create_actor_client("PackingAgent-Mixed-Creation"))
    barrier = Barrier(4)

    with ThreadPoolExecutor(max_workers=4) as executor:
        create_futures = [
            executor.submit(synchronized_create_work_order, creator, barrier, f"Mixed Creation Normal {index}")
            for index, creator in enumerate(creators, start=1)
        ]
        correction_future = executor.submit(
            packing.synchronized_complete_packing,
            barrier,
            parent["id"],
            counted_quantity=100,
            ok_quantity=90,
            correction_quantity=10,
        )

    children = get_direct_correction_children(seeder, parent["id"])
    assert len(children) <= 1

    return [*(future.result() for future in create_futures), correction_future.result()]


def scenario_correction_planning_collides_with_parent_completion(env: ChaosEnvironment):
    seeder = env.create_actor_client("Seeder-Correction-Planning-Race")
    parent = create_planned_work_order(
        seeder,
        "Correction Planning Parent Completion",
        1,
        production_type="MANUAL",
        coating_type="DECORAL",
    )
    advance_to_packing(seeder, parent["id"])
    split_response = seeder.post(
        f"/process/work-orders/{parent['id']}/packing/complete",
        json={"counted_quantity": 100, "ok_quantity": 70, "correction_quantity": 30, "correction_reason_category": "niedomalowanie"},
    )
    assert split_response.status_code == 200
    batch_id = split_response.json()["batch_id"]
    correction_order = get_direct_correction_children(seeder, parent["id"])[0]
    start_parent_decoral = seeder.post(f"/process/work-orders/{parent['id']}/batches/{batch_id}/stages/DECORAL_PRODUCTION/start")
    assert start_parent_decoral.status_code == 200

    manager = ManagerAgent(env.create_actor_client("ManagerAgent-Correction-Planning"))
    parent_finisher = env.create_actor_client("DecoralFinalizer-Parent")
    barrier = Barrier(2)

    with ThreadPoolExecutor(max_workers=2) as executor:
        future_plan = executor.submit(
            manager.synchronized_plan,
            barrier,
            correction_order["id"],
            production_type="MANUAL",
            queue_position=2,
        )
        future_finish = executor.submit(
            synchronized_post,
            parent_finisher,
            barrier,
            f"/process/work-orders/{parent['id']}/batches/{batch_id}/stages/DECORAL_PRODUCTION/finish",
        )

    parent_detail = get_work_order_detail(seeder, parent["id"])
    correction_detail = get_work_order_detail(seeder, correction_order["id"])
    assert parent_detail["process_status"]["value"] == "WAITING_FOR_CORRECTIONS"
    assert parent_detail["completed_quantity"] in {0, 70}
    assert correction_detail["production_type"]["value"] == "MANUAL"
    stage_states = {stage["stage"]["value"]: stage["status"]["value"] for stage in correction_detail["stage_states"]}
    assert stage_states["SURFACE_PREPARATION"] == "DONE"
    assert stage_states["PRODUCTION"] == "NOT_STARTED"

    return [future_plan.result(), future_finish.result()]


def scenario_correction_completion_races_parent_duplicate_packing(env: ChaosEnvironment):
    seeder = env.create_actor_client("Seeder-Correction-Completion-Race")
    parent = create_planned_work_order(seeder, "Correction Completion Parent Duplicate", 1)
    advance_to_packing(seeder, parent["id"])
    split_response = seeder.post(
        f"/process/work-orders/{parent['id']}/packing/complete",
        json={"counted_quantity": 100, "ok_quantity": 90, "correction_quantity": 10, "correction_reason_category": "niedomalowanie"},
    )
    assert split_response.status_code == 200
    correction_order = get_direct_correction_children(seeder, parent["id"])[0]
    manager = ManagerAgent(env.create_actor_client("ManagerAgent-Correction-Completion"))
    plan_response = manager.plan(correction_order["id"], production_type="MANUAL", queue_position=2)
    assert plan_response.status_code == 200
    advance_to_packing(seeder, correction_order["id"])

    child_packing = PackingAgent(env.create_actor_client("PackingAgent-Correction-Child"))
    parent_duplicate = PackingAgent(env.create_actor_client("PackingAgent-Parent-Duplicate"))
    barrier = Barrier(2)

    with ThreadPoolExecutor(max_workers=2) as executor:
        future_child = executor.submit(
            child_packing.synchronized_complete_packing,
            barrier,
            correction_order["id"],
            counted_quantity=10,
            ok_quantity=10,
            correction_quantity=0,
        )
        future_parent_duplicate = executor.submit(
            parent_duplicate.synchronized_complete_packing,
            barrier,
            parent["id"],
            counted_quantity=100,
            ok_quantity=90,
            correction_quantity=10,
        )

    parent_detail = get_work_order_detail(seeder, parent["id"])
    correction_detail = get_work_order_detail(seeder, correction_order["id"])
    children = get_direct_correction_children(seeder, parent["id"])
    assert len(children) == 1
    assert parent_detail["process_status"]["value"] == "READY"
    assert parent_detail["completed_quantity"] == 100
    assert correction_detail["is_historical_correction"] is True

    return [future_child.result(), future_parent_duplicate.result()]


def scenario_office_edits_order_while_manager_plans_it(env: ChaosEnvironment):
    seeder = env.create_actor_client("Seeder")
    created = create_work_order(seeder, "Office Edit During Planning")

    manager = ManagerAgent(env.create_actor_client("ManagerAgent"))
    office = OfficeAgent(env.create_actor_client("OfficeAgent"))
    barrier = Barrier(2)

    with ThreadPoolExecutor(max_workers=2) as executor:
        future_plan = executor.submit(
            manager.synchronized_plan,
            barrier,
            created["id"],
            production_type="MANUAL",
            queue_position=1,
        )
        future_patch = executor.submit(
            office.synchronized_patch_work_order,
            barrier,
            created["id"],
            {"customer_name": "Office Updated Customer", "notes": "Office race edit"},
        )

    detail = get_work_order_detail(seeder, created["id"])
    assert detail["production_type"] is None or detail["production_type"]["value"] == "MANUAL"
    assert detail["customer_name"] in {"ACME", "Office Updated Customer"}
    assert detail["notes"] in {None, "Office race edit"}
    return [future_plan.result(), future_patch.result()]


def scenario_office_mark_complete_while_manager_plans(env: ChaosEnvironment):
    seeder = env.create_actor_client("Seeder")
    incomplete = create_work_order(seeder, "Office Complete During Planning")

    office = OfficeAgent(env.create_actor_client("OfficeAgent"))
    manager = ManagerAgent(env.create_actor_client("ManagerAgent"))
    initial_patch = office.patch_work_order(incomplete["id"], {"notes": "Awaiting intake completion"})
    assert initial_patch.status_code == 200

    detail_before = get_work_order_detail(seeder, incomplete["id"])
    assert detail_before["is_incomplete_on_arrival"] is False

    incomplete_flag_response = office.patch_work_order(incomplete["id"], {"notes": "Cannot mark incomplete via patch"})
    assert incomplete_flag_response.status_code == 200

    incomplete_seed = seeder.post(
        "/work-orders",
        json={**build_create_payload("Office Complete During Planning Incomplete"), "is_incomplete_on_arrival": True},
    )
    assert incomplete_seed.status_code == 201
    incomplete_created = incomplete_seed.json()

    barrier = Barrier(2)
    with ThreadPoolExecutor(max_workers=2) as executor:
        future_complete = executor.submit(office.synchronized_mark_complete_arrival, barrier, incomplete_created["id"])
        future_plan = executor.submit(
            manager.synchronized_plan,
            barrier,
            incomplete_created["id"],
            production_type="MANUAL",
            queue_position=1,
        )

    final_detail = get_work_order_detail(seeder, incomplete_created["id"])
    assert not (
        final_detail["is_incomplete_on_arrival"] is True
        and final_detail["production_type"] is not None
        and final_detail["queue_position"] is not None
    )
    return [future_complete.result(), future_plan.result()]


def scenario_office_patch_races_complete_arrival(env: ChaosEnvironment):
    seeder = env.create_actor_client("Seeder-Incomplete-Patch")
    created_response = seeder.post(
        "/work-orders",
        json={**build_create_payload("Office Patch Complete Arrival Race"), "is_incomplete_on_arrival": True},
    )
    assert created_response.status_code == 201
    created = created_response.json()

    patching_office = OfficeAgent(env.create_actor_client("OfficeAgent-Patch-Incomplete"))
    completing_office = OfficeAgent(env.create_actor_client("OfficeAgent-Complete-Incomplete"))
    barrier = Barrier(2)

    with ThreadPoolExecutor(max_workers=2) as executor:
        future_patch = executor.submit(
            patching_office.synchronized_patch_work_order,
            barrier,
            created["id"],
            {"customer_name": "Office Race Customer", "notes": "Race patch kept coherent"},
        )
        future_complete = executor.submit(completing_office.synchronized_mark_complete_arrival, barrier, created["id"])

    final_detail = get_work_order_detail(seeder, created["id"])
    assert final_detail["is_incomplete_on_arrival"] is False
    assert final_detail["status"]["value"] == "ENTERED"
    assert final_detail["customer_name"] in {"ACME", "Office Race Customer"}
    assert final_detail["notes"] in {None, "Race patch kept coherent"}

    return [future_patch.result(), future_complete.result()]


def scenario_invalid_patch_during_planning(env: ChaosEnvironment):
    seeder = env.create_actor_client("Seeder")
    created_response = seeder.post(
        "/work-orders",
        json={
            **build_create_payload("Invalid Patch During Planning"),
            "profiles_quantity": 5,
            "profiles_to_count": False,
        },
    )
    assert created_response.status_code == 201
    created = created_response.json()
    before_detail = get_work_order_detail(seeder, created["id"])

    office = OfficeAgent(env.create_actor_client("OfficeAgent"))
    manager = ManagerAgent(env.create_actor_client("ManagerAgent"))
    barrier = Barrier(2)

    with ThreadPoolExecutor(max_workers=2) as executor:
        future_plan = executor.submit(
            manager.synchronized_plan,
            barrier,
            created["id"],
            production_type="MANUAL",
            queue_position=1,
        )
        future_patch = executor.submit(
            office.synchronized_patch_work_order,
            barrier,
            created["id"],
            {"profiles_to_count": True, "notes": "Should not persist"},
        )

    patch_response = future_patch.result()
    after_detail = get_work_order_detail(seeder, created["id"])

    assert patch_response.status_code == 422
    assert after_detail["profiles_quantity"] == before_detail["profiles_quantity"]
    assert after_detail["profiles_to_count"] == before_detail["profiles_to_count"]
    assert after_detail["accessories_quantity"] == before_detail["accessories_quantity"]
    assert after_detail["accessories_to_count"] == before_detail["accessories_to_count"]
    assert after_detail["customer_name"] == before_detail["customer_name"]
    assert after_detail["notes"] == before_detail["notes"]

    return [future_plan.result(), patch_response]


def scenario_attachment_upload_delete_detail_reload(env: ChaosEnvironment):
    seeder = env.create_actor_client("Seeder-Attachments")
    created = create_work_order(seeder, "Attachment Race")
    initial_upload = seeder.post(
        f"/work-orders/{created['id']}/attachments",
        files={"file": ("initial.pdf", b"%PDF-1.4\n%%EOF", "application/pdf")},
    )
    assert initial_upload.status_code == 201
    initial_attachment_id = initial_upload.json()["id"]
    anchor_upload = seeder.post(
        f"/work-orders/{created['id']}/attachments",
        files={"file": ("anchor.pdf", b"%PDF-1.4\n%%EOF", "application/pdf")},
    )
    assert anchor_upload.status_code == 201

    uploader = AttachmentAgent(env.create_actor_client("AttachmentAgent-Upload"))
    deleter = AttachmentAgent(env.create_actor_client("AttachmentAgent-Delete"))
    office = OfficeAgent(env.create_actor_client("OfficeAgent-Detail"))
    barrier = Barrier(3)

    with ThreadPoolExecutor(max_workers=3) as executor:
        future_upload = executor.submit(uploader.synchronized_upload_pdf, barrier, created["id"], filename="fresh.pdf")
        future_delete = executor.submit(deleter.synchronized_delete_attachment, barrier, created["id"], initial_attachment_id)
        future_detail = executor.submit(office.synchronized_get_work_order, barrier, created["id"])

    list_response = uploader.list_attachments(created["id"])
    assert list_response.status_code == 200
    remaining_filenames = {attachment["original_filename"] for attachment in list_response.json()}
    assert "initial.pdf" not in remaining_filenames
    assert "anchor.pdf" in remaining_filenames
    assert remaining_filenames <= {"anchor.pdf", "fresh.pdf"}

    return [future_upload.result(), future_delete.result(), future_detail.result(), list_response]


def scenario_parallel_hanging_start(env: ChaosEnvironment):
    seeder = env.create_actor_client("Seeder-Hanging")
    first = create_planned_work_order(seeder, "Chaos Hanging First", 1, production_type="AUTOMATIC")
    second = create_planned_work_order(seeder, "Chaos Hanging Second", 2, production_type="AUTOMATIC")

    for work_order_id in [first["id"], second["id"]]:
        start_surface_preparation(seeder, work_order_id, 100)
        seeder.post(f"/process/work-orders/{work_order_id}/stages/SURFACE_PREPARATION/finish")

    operator_a = StageOperatorAgent(env.create_actor_client("HangingAgent-A"))
    operator_b = StageOperatorAgent(env.create_actor_client("HangingAgent-B"))
    barrier = Barrier(2)

    with ThreadPoolExecutor(max_workers=2) as executor:
        future_a = executor.submit(operator_a.synchronized_start_hanging, barrier, first["id"])
        future_b = executor.submit(operator_b.synchronized_start_hanging, barrier, second["id"])

    return [future_a.result(), future_b.result()]


def scenario_packing_actual_expected_mismatch(env: ChaosEnvironment):
    seeder = env.create_actor_client("Seeder-ActualMismatch")
    created = create_planned_work_order(seeder, "Chaos Actual Mismatch", 1)

    start_surface_preparation(seeder, created["id"], 95)
    seeder.post(f"/process/work-orders/{created['id']}/stages/SURFACE_PREPARATION/finish")
    seeder.post(f"/process/work-orders/{created['id']}/stages/PRODUCTION/start")
    seeder.post(f"/process/work-orders/{created['id']}/stages/PRODUCTION/finish")
    seeder.post(f"/process/work-orders/{created['id']}/stages/PACKING/start")

    packing = PackingAgent(env.create_actor_client("PackingAgent-Mismatch"))
    stale_response = packing.complete_packing(
        created["id"],
        counted_quantity=100,
        ok_quantity=95,
        correction_quantity=5,
    )
    valid_response = packing.complete_packing(
        created["id"],
        counted_quantity=95,
        ok_quantity=90,
        correction_quantity=5,
    )

    return [stale_response, valid_response]


def scenario_correction_uses_actual_split(env: ChaosEnvironment):
    seeder = env.create_actor_client("Seeder-CorrectionActual")
    created = create_planned_work_order(seeder, "Chaos Correction Actual", 1, production_type="MANUAL")

    start_surface_preparation(seeder, created["id"], 95)
    seeder.post(f"/process/work-orders/{created['id']}/stages/SURFACE_PREPARATION/finish")
    seeder.post(f"/process/work-orders/{created['id']}/stages/PRODUCTION/start")
    seeder.post(f"/process/work-orders/{created['id']}/stages/PRODUCTION/finish")
    seeder.post(f"/process/work-orders/{created['id']}/stages/PACKING/start")

    packing = PackingAgent(env.create_actor_client("PackingAgent-CorrectionActual"))
    packing_response = packing.complete_packing(
        created["id"],
        counted_quantity=95,
        ok_quantity=90,
        correction_quantity=5,
    )

    children = get_direct_correction_children(seeder, created["id"])
    assert len(children) == 1
    assert children[0]["total_quantity"] == 5
    detail = get_work_order_detail(seeder, created["id"])
    assert detail["pending_correction_quantity"] == 5

    return [packing_response]
