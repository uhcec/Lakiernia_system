import { describe, expect, it } from "vitest";

import { getWorkOrderAttentionBadges } from "../src/utils/workOrderDisplay";
import type { WorkOrder } from "../src/types/workOrders";

function buildWorkOrder(overrides: Partial<WorkOrder> = {}): WorkOrder {
  return {
    id: 1,
    order_number: "WO-TEST",
    external_order_number: null,
    title: "WO-TEST",
    total_quantity: 10,
    completed_quantity: 0,
    current_active_quantity: 10,
    waiting_ok_quantity: 0,
    pending_correction_quantity: 0,
    total_progress_quantity: 0,
    is_correction: false,
    is_historical_correction: false,
    correction_reason_category: null,
    correction_reason_note: null,
    parent_order: null,
    correction_orders: [],
    description: null,
    customer_name: "Klient",
    ral_code: "RAL 9005",
    paint_producer: "Test",
    status: { value: "ASSIGNED", label: "Przypisane" },
    process_status: { value: "HANGING", label: "Zawieszanie" },
    coating_type: { value: "RAL", label: "RAL" },
    queue_blocked_by_resource: null,
    queue_blocked_reason: null,
    production_type: { value: "AUTOMATIC", label: "Automatyczna" },
    queue_namespace: { value: "MAIN", label: "Główna" },
    queue_position: 1,
    stage_states: [],
    batches: [],
    received_date: "2026-05-30",
    planned_pickup_date: null,
    total_area_m2: null,
    is_incomplete_on_arrival: false,
    profiles_quantity: null,
    profiles_to_count: false,
    accessories_quantity: null,
    accessories_to_count: false,
    notes: null,
    created_at: "2026-05-30T08:00:00Z",
    updated_at: "2026-05-30T08:00:00Z",
    ...overrides,
  };
}

describe("work order display helpers", () => {
  it("shows a warning badge for manager queue resource blocks", () => {
    const badges = getWorkOrderAttentionBadges(
      buildWorkOrder({
        queue_blocked_by_resource: "AUTOMATIC_LINE",
        queue_blocked_reason: "Linia automatyczna zajęta",
      }),
    );

    expect(badges).toContainEqual({ label: "CZEKA: Linia automatyczna zajęta", tone: "warning" });
  });
});
