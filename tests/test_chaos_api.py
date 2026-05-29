from __future__ import annotations

from pathlib import Path

import pytest

from tests.chaos.harness import ChaosEnvironment
from tests.chaos.invariants import assert_global_invariants
from tests.chaos.scenarios import (
    scenario_attachment_upload_delete_detail_reload,
    scenario_correction_uses_actual_split,
    scenario_double_click_packing_complete,
    scenario_invalid_patch_during_planning,
    scenario_office_edits_order_while_manager_plans_it,
    scenario_office_mark_complete_while_manager_plans,
    scenario_office_patch_races_complete_arrival,
    scenario_packing_actual_expected_mismatch,
    scenario_parallel_hanging_start,
    scenario_parallel_normal_and_correction_creation,
    scenario_packing_creates_correction_while_manager_reorders,
    scenario_operator_double_finishes_same_stage,
    scenario_queue_position_patch_collides_with_bulk_reorder,
    scenario_repeated_correction_split_does_not_duplicate_child,
    scenario_stale_queue_payload_submit,
    scenario_two_managers_reorder_same_queue,
)


@pytest.fixture
def chaos_environment(tmp_path: Path) -> ChaosEnvironment:
    env = ChaosEnvironment(tmp_path / "chaos.sqlite")
    try:
        yield env
    finally:
        env.close()


@pytest.mark.parametrize(
    ("scenario_name", "scenario_runner"),
    [
        ("two_managers_reorder_same_queue", scenario_two_managers_reorder_same_queue),
        ("stale_queue_payload_submit", scenario_stale_queue_payload_submit),
        ("queue_position_patch_collides_with_bulk_reorder", scenario_queue_position_patch_collides_with_bulk_reorder),
        ("operator_double_finishes_same_stage", scenario_operator_double_finishes_same_stage),
        ("double_click_packing_complete", scenario_double_click_packing_complete),
        ("packing_creates_correction_while_manager_reorders", scenario_packing_creates_correction_while_manager_reorders),
        ("parallel_hanging_start", scenario_parallel_hanging_start),
        ("packing_actual_expected_mismatch", scenario_packing_actual_expected_mismatch),
        ("correction_uses_actual_split", scenario_correction_uses_actual_split),
        ("repeated_correction_split_does_not_duplicate_child", scenario_repeated_correction_split_does_not_duplicate_child),
        ("parallel_normal_and_correction_creation", scenario_parallel_normal_and_correction_creation),
        ("office_edits_order_while_manager_plans_it", scenario_office_edits_order_while_manager_plans_it),
        ("office_mark_complete_while_manager_plans", scenario_office_mark_complete_while_manager_plans),
        ("office_patch_races_complete_arrival", scenario_office_patch_races_complete_arrival),
        ("invalid_patch_during_planning", scenario_invalid_patch_during_planning),
        ("attachment_upload_delete_detail_reload", scenario_attachment_upload_delete_detail_reload),
    ],
)
def test_chaos_scenarios_preserve_global_invariants(
    chaos_environment: ChaosEnvironment,
    scenario_name: str,
    scenario_runner,
) -> None:
    _ = scenario_name
    responses = scenario_runner(chaos_environment)

    for response in responses:
        assert response.status_code in {200, 201, 204, 409, 422}

    with chaos_environment.create_session() as session:
        assert_global_invariants(session, chaos_environment.event_log)