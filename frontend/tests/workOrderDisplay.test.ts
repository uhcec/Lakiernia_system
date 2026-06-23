import { describe, expect, it } from "vitest";

import { getWorkOrderAttentionBadges, getWorkOrderBadgeStack, getWorkOrderDiscrepancyText } from "../src/utils/workOrderDisplay";
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
    work_order_kind: { value: "STANDARD", label: "Standardowe" },
    is_ocynk: false,
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
    is_overdue: false,
    is_released_to_client: false,
    released_to_client_at: null,
    total_area_m2: null,
    is_incomplete_on_arrival: false,
    surface_preparation_counted_quantity: null,
    surface_preparation_quantity_difference: null,
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

  it("shows release state badges for ready work orders", () => {
    const unreleasedBadges = getWorkOrderBadgeStack(
      buildWorkOrder({
        process_status: { value: "READY", label: "Gotowe" },
        is_released_to_client: false,
      }),
    );

    const releasedBadges = getWorkOrderBadgeStack(
      buildWorkOrder({
        process_status: { value: "READY", label: "Gotowe" },
        is_released_to_client: true,
      }),
    );

    expect(unreleasedBadges).toContainEqual({ label: "DO WYDANIA", tone: "warning" });
    expect(releasedBadges).toContainEqual({ label: "WYDANE", tone: "success" });
  });

  it("shows discrepancy text and badge from backend read-model fields", () => {
    const workOrder = buildWorkOrder({
      surface_preparation_counted_quantity: 8,
      surface_preparation_quantity_difference: -2,
    });

    expect(getWorkOrderDiscrepancyText(workOrder)).toBe("Przygotowanie: zadeklarowano 10, policzono 8 (-2 szt.)");
    expect(getWorkOrderAttentionBadges(workOrder)).toContainEqual({ label: "RÓŻNICA: -2 SZT.", tone: "warning" });
  });

  it("shows the PO TERMINIE badge from the backend is_overdue flag, not a client clock", () => {
    expect(getWorkOrderAttentionBadges(buildWorkOrder({ is_overdue: true }))).toContainEqual({
      label: "PO TERMINIE",
      tone: "danger",
    });
    expect(getWorkOrderAttentionBadges(buildWorkOrder({ is_overdue: false }))).not.toContainEqual({
      label: "PO TERMINIE",
      tone: "danger",
    });
  });

  it("shows work-type badges for Przemalowanka and Ocynk", () => {
    const badges = getWorkOrderBadgeStack(
      buildWorkOrder({
        work_order_kind: { value: "PRZEMALOWANKA", label: "Przemalowanka" },
        is_ocynk: true,
      }),
    );

    expect(badges).toContainEqual({ label: "PRZEMALOWANKA", tone: "danger" });
    expect(badges).toContainEqual({ label: "OCYNK", tone: "info" });
  });
});
