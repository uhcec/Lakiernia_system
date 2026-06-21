import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ManagerPanelPage } from "../src/pages/ManagerPanelPage";
import type { WorkOrder } from "../src/types/workOrders";

vi.mock("../src/api/managerApi", () => ({
  assignWorkOrderPlan: vi.fn(),
  fetchCorrectionReasonReport: vi.fn(),
  fetchPlannedWorkOrders: vi.fn(),
  fetchUnplannedWorkOrders: vi.fn(),
  getCorrectionReasonReportExportUrl: vi.fn(() => "/manager/corrections/reason-report/export.csv"),
  reorderWorkOrderQueue: vi.fn(),
  updateWorkOrderProductionType: vi.fn(),
}));

// Keep the page a faithful renderer of backend state — stub the display helpers so the
// test only exercises the plan-draft / suggested-position reconcile, not label logic.
vi.mock("../src/utils/workOrderDisplay", () => ({
  getWorkOrderActiveCorrectionsText: () => null,
  getWorkOrderAttentionBadges: () => [],
  getWorkOrderBadgeStack: () => [],
  getWorkOrderDiscrepancyText: () => null,
  getHistoricalWorkOrderResultText: () => "",
  getWorkOrderProgressText: () => "0 / 0 szt.",
  getWorkOrderStatusSummary: () => "Status testowy",
}));

const managerApi = await import("../src/api/managerApi");

const fetchUnplannedWorkOrdersMock = vi.mocked(managerApi.fetchUnplannedWorkOrders);
const fetchPlannedWorkOrdersMock = vi.mocked(managerApi.fetchPlannedWorkOrders);
const fetchCorrectionReasonReportMock = vi.mocked(managerApi.fetchCorrectionReasonReport);

function buildWorkOrder(id: number, orderNumber: string, queuePosition: number | null): WorkOrder {
  return {
    id,
    order_number: orderNumber,
    external_order_number: null,
    title: orderNumber,
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
    paint_code: "P-9005",
    paint_producer: "Test",
    predicted_paint_quantity_kg: null,
    current_paint_stock_quantity_kg: 30,
    paint_inventory_insufficient_for_prediction: false,
    paint_inventory_shortage_quantity_kg: null,
    paint_stock_snapshot_quantity_kg: 30,
    consumed_paint_quantity_kg: 0,
    status: { value: "ASSIGNED", label: "Przypisane" },
    process_status: queuePosition === null
      ? { value: "TO_BE_PLANNED", label: "Do zaplanowania" }
      : { value: "PRODUCTION", label: "Produkcja" },
    coating_type: { value: "RAL", label: "RAL" },
    queue_blocked_by_resource: null,
    queue_blocked_reason: null,
    production_type: queuePosition === null ? null : { value: "MANUAL", label: "Ręczna" },
    queue_namespace: { value: "MAIN", label: "Główna" },
    queue_position: queuePosition,
    stage_states: [],
    batches: [],
    received_date: "2026-05-27",
    planned_pickup_date: null,
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
    created_at: "2026-05-27T08:00:00Z",
    updated_at: `2026-05-27T08:0${queuePosition ?? 0}:00Z`,
  };
}

beforeEach(() => {
  fetchUnplannedWorkOrdersMock.mockReset();
  fetchPlannedWorkOrdersMock.mockReset();
  fetchCorrectionReasonReportMock.mockReset();
  fetchCorrectionReasonReportMock.mockResolvedValue([]);
});

afterEach(() => {
  vi.clearAllMocks();
});

describe("manager plan-draft reconcile on planned -> unplanned transition (NA31)", () => {
  it("offers position 1 for a returned correction after a background poll, without manual refresh", async () => {
    // Initial state: WO-1 is the only PLANNED order (active queue position 1), nothing unplanned.
    fetchUnplannedWorkOrdersMock.mockResolvedValueOnce([]);
    fetchPlannedWorkOrdersMock.mockResolvedValueOnce([buildWorkOrder(1, "WO-1", 1)]);

    // Background poll after a packing correction sends WO-1 back to planning: WO-1 is now
    // UNPLANNED and the active queue is empty.
    fetchUnplannedWorkOrdersMock.mockResolvedValue([buildWorkOrder(1, "WO-1", null)]);
    fetchPlannedWorkOrdersMock.mockResolvedValue([]);

    render(<ManagerPanelPage />);

    // Let the initial foreground load resolve and render the active queue.
    await screen.findByText("Aktywne");

    // Initially WO-1 is planned (it shows in the active queue), so the "Do zaplanowania"
    // list is empty — there is no "Zaplanuj" form yet and no position spinbutton.
    expect(screen.queryByRole("button", { name: "Zaplanuj" })).toBeNull();
    expect(screen.queryByRole("spinbutton")).toBeNull();

    // Drive one background poll (the transition the user used to have to fix with F5).
    // usePolling re-fires its callback immediately on visibilitychange while visible,
    // so dispatching the event triggers a background loadManagerData without timers.
    await act(async () => {
      document.dispatchEvent(new Event("visibilitychange"));
      await Promise.resolve();
    });

    // WO-1 now appears in the unplanned planning list (the "Zaplanuj" form is rendered).
    await waitFor(() => expect(screen.getByRole("button", { name: "Zaplanuj" })).toBeTruthy());

    // The suggested queue position must be 1 (queue is empty), not a stale length+1.
    const positionInput = screen.getByRole("spinbutton") as HTMLInputElement;
    expect(positionInput.value).toBe("1");

    // And planning at position 1 is accepted from the UI with no manual refresh.
    fireEvent.click(screen.getByRole("button", { name: "Zaplanuj" }));
    await waitFor(() =>
      expect(managerApi.assignWorkOrderPlan).toHaveBeenCalledWith(1, {
        production_type: "MANUAL",
        queue_position: 1,
      }),
    );
  });
});
