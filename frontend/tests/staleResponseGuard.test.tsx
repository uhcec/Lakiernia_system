import { act, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { StageWorkOrdersPage } from "../src/components/StageWorkOrdersPage";
import type { StageWorkOrder } from "../src/types/process";

// CHANGES #16b: a slow foreground load racing a background poll must never present data OLDER
// than what a fresher response already put on screen. The boards take a ticket per load and only
// the latest ticket may apply state — this test resolves the requests out of order to prove it.

vi.mock("../src/api/processApi", () => ({
  fetchStageWorkOrders: vi.fn(),
  recordAutomaticPaintConsumption: vi.fn(),
  transitionStage: vi.fn(),
}));

vi.mock("../src/utils/correctionContext", () => ({
  loadCorrectionContexts: vi.fn().mockResolvedValue({ contexts: {}, failedCount: 0 }),
}));

vi.mock("../src/components/StationPresenceWidget", () => ({
  StationPresenceWidget: () => null,
}));

vi.mock("../src/components/TechnicalDrawingLinks", () => ({
  TechnicalDrawingLinks: () => null,
}));

const processApi = await import("../src/api/processApi");
const fetchStageWorkOrdersMock = vi.mocked(processApi.fetchStageWorkOrders);

function buildStageWorkOrder(id: number, orderNumber: string): StageWorkOrder {
  return {
    id,
    batch_id: null,
    is_correction: false,
    is_historical_correction: false,
    work_order_kind: { value: "STANDARD", label: "Standardowe" },
    is_ocynk: false,
    order_number: orderNumber,
    title: orderNumber,
    ral_code: "RAL 9005",
    paint_code: "P-9005",
    paint_producer: "Test",
    current_paint_stock_quantity_kg: 30,
    paint_stock_snapshot_quantity_kg: 30,
    consumed_paint_quantity_kg: 0,
    total_area_m2: null,
    total_quantity: 10,
    current_active_quantity: 10,
    operational_quantity: 10,
    batch_quantity: null,
    planned_quantity: 10,
    counted_quantity: null,
    quantity_difference: null,
    customer_name: "Klient",
    profiles_quantity: null,
    profiles_to_count: false,
    accessories_quantity: null,
    accessories_to_count: false,
    queue_position: 1,
    shared_stage_line_label: null,
    is_next_at_shared_stage: false,
    queue_namespace: { value: "MAIN", label: "Główna" },
    production_type: { value: "MANUAL", label: "Ręczna" },
    coating_type: { value: "RAL", label: "RAL" },
    technical_drawings: [],
    batch_type: "MAIN",
    batch_is_partial: false,
    is_being_packed: false,
    holds_packing_slot: false,
    packing_slots_total: 2,
    can_complete_packing: true,
    packing_blocked_reason: null,
    stage_status: { stage: "HANGING", status: { value: "NOT_STARTED", label: "Nie rozpoczęto" } },
  } as StageWorkOrder;
}

function setHidden(hidden: boolean) {
  Object.defineProperty(document, "hidden", { configurable: true, value: hidden });
  document.dispatchEvent(new Event("visibilitychange"));
}

describe("stale-response guard on polling boards (CHANGES #16b)", () => {
  beforeEach(() => {
    fetchStageWorkOrdersMock.mockReset();
    setHidden(false);
  });

  it("ignores a slow response that resolves after a fresher poll already rendered", async () => {
    let resolveSlowLoad: (items: StageWorkOrder[]) => void = () => undefined;
    const slowLoad = new Promise<StageWorkOrder[]>((resolve) => {
      resolveSlowLoad = resolve;
    });

    // 1st call = the mount load (instant); 2nd = a slow background poll that hangs;
    // 3rd = a later background poll that returns fresher data immediately.
    fetchStageWorkOrdersMock
      .mockResolvedValueOnce([buildStageWorkOrder(1, "WO-INITIAL")])
      .mockReturnValueOnce(slowLoad)
      .mockResolvedValueOnce([buildStageWorkOrder(2, "WO-FRESH")]);

    render(<StageWorkOrdersPage stage="HANGING" title="Zawieszanie" emptyMessage="Brak zleceń" />);
    await screen.findAllByText(/WO-INITIAL/);

    // Hide + show the tab: usePolling fires an immediate background refresh on return.
    act(() => setHidden(true));
    act(() => setHidden(false)); // -> slow poll (hangs)
    act(() => setHidden(true));
    act(() => setHidden(false)); // -> fresh poll (instant)

    await screen.findAllByText(/WO-FRESH/);

    // Now the SLOW response finally arrives carrying pre-refresh (stale) data — it must be dropped.
    await act(async () => {
      resolveSlowLoad([buildStageWorkOrder(3, "WO-STALE")]);
      await slowLoad;
    });

    expect(screen.queryAllByText(/WO-STALE/)).toHaveLength(0);
    expect(screen.getAllByText(/WO-FRESH/).length).toBeGreaterThan(0);
    expect(fetchStageWorkOrdersMock).toHaveBeenCalledTimes(3);
  });
});
