import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { PackingWorkOrdersPage } from "../src/components/PackingWorkOrdersPage";
import { StageWorkOrdersPage } from "../src/components/StageWorkOrdersPage";
import { ApiError } from "../src/api/apiError";
import { ManagerPanelPage } from "../src/pages/ManagerPanelPage";
import type { StageWorkOrder } from "../src/types/process";
import type { WorkOrder } from "../src/types/workOrders";

vi.mock("../src/api/managerApi", () => ({
  assignWorkOrderPlan: vi.fn(),
  fetchPlannedWorkOrders: vi.fn(),
  fetchUnplannedWorkOrders: vi.fn(),
  reorderWorkOrderQueue: vi.fn(),
}));

vi.mock("../src/api/processApi", () => ({
  completePacking: vi.fn(),
  fetchStageWorkOrders: vi.fn(),
  transitionStage: vi.fn(),
}));

vi.mock("../src/api/workOrdersApi", () => ({
  fetchWorkOrder: vi.fn(),
}));

vi.mock("../src/utils/workOrderDisplay", () => ({
  formatWorkOrderPrimaryInfo: (workOrder: { order_number: string; customer_name?: string | null }) =>
    `${workOrder.order_number} :: ${workOrder.customer_name ?? "Brak firmy"}`,
  getStageWorkOrderBadgeStack: () => [],
  getStageWorkOrderProgressText: (workOrder: { planned_quantity?: number; total_quantity: number }) =>
    `${workOrder.planned_quantity ?? workOrder.total_quantity} / ${workOrder.total_quantity} szt.`,
  getWorkOrderActiveCorrectionsText: () => null,
  getWorkOrderAttentionBadges: () => [],
  getWorkOrderBadgeStack: () => [],
  getWorkOrderProgressText: (workOrder: { total_quantity: number }) => `${workOrder.total_quantity} / ${workOrder.total_quantity} szt.`,
  getWorkOrderStatusSummary: () => "Status testowy",
}));

const managerApi = await import("../src/api/managerApi");
const processApi = await import("../src/api/processApi");
const workOrdersApi = await import("../src/api/workOrdersApi");

const fetchUnplannedWorkOrdersMock = vi.mocked(managerApi.fetchUnplannedWorkOrders);
const fetchPlannedWorkOrdersMock = vi.mocked(managerApi.fetchPlannedWorkOrders);
const reorderWorkOrderQueueMock = vi.mocked(managerApi.reorderWorkOrderQueue);
const fetchStageWorkOrdersMock = vi.mocked(processApi.fetchStageWorkOrders);
const transitionStageMock = vi.mocked(processApi.transitionStage);
const completePackingMock = vi.mocked(processApi.completePacking);
const fetchWorkOrderMock = vi.mocked(workOrdersApi.fetchWorkOrder);

function buildWorkOrder(id: number, orderNumber: string, queuePosition: number, customerName = "Klient"): WorkOrder {
  return {
    id,
    order_number: orderNumber,
    title: orderNumber,
    total_quantity: 10,
    completed_quantity: 0,
    current_active_quantity: 10,
    waiting_ok_quantity: 0,
    pending_correction_quantity: 0,
    total_progress_quantity: 0,
    is_correction: false,
    parent_order: null,
    correction_orders: [],
    description: null,
    customer_name: customerName,
    ral_code: "RAL 9005",
    paint_producer: "Test",
    status: { value: "ASSIGNED", label: "Przypisane" },
    process_status: { value: "PACKING", label: "Pakowanie" },
    coating_type: { value: "RAL", label: "RAL" },
    production_type: { value: "MANUAL", label: "Ręczna" },
    queue_namespace: { value: "MAIN", label: "Główna" },
    queue_position: queuePosition,
    stage_states: [],
    batches: [],
    received_date: "2026-05-27",
    planned_pickup_date: null,
    total_area_m2: null,
    is_incomplete_on_arrival: false,
    profiles_quantity: null,
    profiles_to_count: false,
    accessories_quantity: null,
    accessories_to_count: false,
    notes: null,
    created_at: "2026-05-27T08:00:00Z",
    updated_at: `2026-05-27T08:0${queuePosition}:00Z`,
  };
}

function buildStageWorkOrder(
  overrides: Partial<StageWorkOrder> & Pick<StageWorkOrder, "id" | "order_number" | "stage_status">,
): StageWorkOrder {
  return {
    id: overrides.id,
    batch_id: overrides.batch_id ?? null,
    is_correction: overrides.is_correction ?? false,
    order_number: overrides.order_number,
    title: overrides.title ?? overrides.order_number,
    ral_code: overrides.ral_code ?? "RAL 9005",
    total_area_m2: overrides.total_area_m2 ?? null,
    total_quantity: overrides.total_quantity ?? 10,
    current_active_quantity: overrides.current_active_quantity ?? 10,
    batch_quantity: overrides.batch_quantity ?? null,
    planned_quantity: overrides.planned_quantity ?? 10,
    counted_quantity: overrides.counted_quantity ?? null,
    quantity_difference: overrides.quantity_difference ?? null,
    customer_name: overrides.customer_name ?? "Klient",
    queue_position: overrides.queue_position ?? 1,
    queue_namespace: overrides.queue_namespace ?? { value: "MAIN", label: "Główna" },
    production_type: overrides.production_type ?? { value: "MANUAL", label: "Ręczna" },
    coating_type: overrides.coating_type ?? { value: "RAL", label: "RAL" },
    batch_type: overrides.batch_type ?? "MAIN",
    batch_is_partial: overrides.batch_is_partial ?? false,
    stage_status: overrides.stage_status,
  };
}

beforeEach(() => {
  fetchUnplannedWorkOrdersMock.mockReset();
  fetchPlannedWorkOrdersMock.mockReset();
  reorderWorkOrderQueueMock.mockReset();
  fetchStageWorkOrdersMock.mockReset();
  transitionStageMock.mockReset();
  completePackingMock.mockReset();
  fetchWorkOrderMock.mockReset();
});

afterEach(() => {
  vi.clearAllMocks();
});

describe("frontend state consistency", () => {
  it("resets manager reorder UI to backend state after save failure", async () => {
    fetchUnplannedWorkOrdersMock.mockResolvedValue([]);
    fetchPlannedWorkOrdersMock
      .mockResolvedValueOnce([
        buildWorkOrder(1, "WO-1", 1, "Alpha"),
        buildWorkOrder(2, "WO-2", 2, "Beta"),
      ])
      .mockResolvedValueOnce([
        buildWorkOrder(1, "WO-1", 1, "Alpha"),
        buildWorkOrder(2, "WO-2", 2, "Beta"),
      ]);
    reorderWorkOrderQueueMock.mockRejectedValue(new ApiError(409, "Stale queue"));

    const { container } = render(<ManagerPanelPage />);

    await screen.findByText("WO-1 :: Alpha");

    const getQueueOrder = () => Array.from(container.querySelectorAll("article")).map((item) => item.textContent ?? "");
    expect(getQueueOrder()[0]).toContain("WO-1");
    expect(getQueueOrder()[1]).toContain("WO-2");

    const source = screen.getByText("WO-2 :: Beta").closest("article");
    const target = screen.getByText("WO-1 :: Alpha").closest("article");

    expect(source).not.toBeNull();
    expect(target).not.toBeNull();

    fireEvent.dragStart(source as HTMLElement, { dataTransfer: { dropEffect: "move" } });
    fireEvent.dragOver(target as HTMLElement, { dataTransfer: { dropEffect: "move" } });
    fireEvent.drop(target as HTMLElement, { dataTransfer: { dropEffect: "move" } });

    await screen.findByText("Konflikt zapisu kolejki. Odświeżono panel do aktualnego stanu backendu.");
    await waitFor(() => expect(fetchPlannedWorkOrdersMock).toHaveBeenCalledTimes(2));

    expect(getQueueOrder()[0]).toContain("WO-1");
    expect(getQueueOrder()[1]).toContain("WO-2");
  });

  it("reloads stage view after action failure", async () => {
    fetchStageWorkOrdersMock
      .mockResolvedValueOnce([
        buildStageWorkOrder({
          id: 10,
          order_number: "WO-STAGE",
          customer_name: "Przed zapisem",
          stage_status: { stage: "HANGING", status: { value: "NOT_STARTED", label: "Nie rozpoczęto" } },
        }),
      ])
      .mockResolvedValueOnce([
        buildStageWorkOrder({
          id: 10,
          order_number: "WO-STAGE",
          customer_name: "Stan z backendu",
          stage_status: { stage: "HANGING", status: { value: "NOT_STARTED", label: "Nie rozpoczęto" } },
        }),
      ]);
    transitionStageMock.mockRejectedValue(new ApiError(409, "Konflikt etapu"));

    render(
      <StageWorkOrdersPage
        stage="HANGING"
        title="Zawieszanie"
        emptyMessage="Brak zleceń"
      />,
    );

    await screen.findByText("WO-STAGE :: Przed zapisem");

    fireEvent.click(screen.getByRole("button", { name: "Rozpocznij" }));

    await screen.findByText("Konflikt etapu");
    await screen.findByText("WO-STAGE :: Stan z backendu");
    await waitFor(() => expect(fetchStageWorkOrdersMock).toHaveBeenCalledTimes(2));
  });

  it("reloads packing view and discards local draft after submit failure", async () => {
    fetchStageWorkOrdersMock
      .mockResolvedValueOnce([
        buildStageWorkOrder({
          id: 30,
          order_number: "WO-PACK",
          batch_id: 300,
          customer_name: "Roboczy",
          current_active_quantity: 4,
          planned_quantity: 4,
          stage_status: { stage: "PACKING", status: { value: "IN_PROGRESS", label: "W toku" } },
        }),
      ])
      .mockResolvedValueOnce([
        buildStageWorkOrder({
          id: 30,
          order_number: "WO-PACK",
          batch_id: 300,
          customer_name: "Backend",
          counted_quantity: 5,
          current_active_quantity: 5,
          planned_quantity: 5,
          stage_status: { stage: "PACKING", status: { value: "IN_PROGRESS", label: "W toku" } },
        }),
      ]);
    completePackingMock.mockRejectedValue(new ApiError(422, "Nieprawidłowa ilość pakowania"));

    render(<PackingWorkOrdersPage />);

    await screen.findByText("WO-PACK :: Roboczy");

    const inputs = screen.getAllByRole("spinbutton");
    fireEvent.change(inputs[0], { target: { value: "4" } });
    fireEvent.change(inputs[1], { target: { value: "3" } });
    fireEvent.change(inputs[2], { target: { value: "1" } });
    fireEvent.click(screen.getByRole("button", { name: "Zatwierdź pakowanie" }));

    await screen.findByText("Nieprawidłowa ilość pakowania");
    await screen.findByText("WO-PACK :: Backend");
    await waitFor(() => expect(fetchStageWorkOrdersMock).toHaveBeenCalledTimes(2));
    await waitFor(() => {
      const reloadedInputs = screen.getAllByRole("spinbutton") as HTMLInputElement[];
      expect(reloadedInputs.map((input) => input.value)).toEqual(["5", "5", "0"]);
    });
  });

  it("keeps stage list visible when one correction detail fetch fails", async () => {
    fetchStageWorkOrdersMock.mockResolvedValue([
      buildStageWorkOrder({
        id: 50,
        order_number: "WO-CORR",
        is_correction: true,
        stage_status: { stage: "HANGING", status: { value: "NOT_STARTED", label: "Nie rozpoczęto" } },
      }),
    ]);
    fetchWorkOrderMock.mockRejectedValue(new Error("detail failed"));

    render(
      <StageWorkOrdersPage
        stage="HANGING"
        title="Zawieszanie"
        emptyMessage="Brak zleceń"
      />,
    );

    await screen.findByText("WO-CORR :: Klient");
    await screen.findByText("Nie udało się pobrać pełnego kontekstu dla części poprawek. Lista pozostaje dostępna.");
    expect(screen.getByText("Poprawka do zlecenia nadrzędnego")).toBeTruthy();
  });
});