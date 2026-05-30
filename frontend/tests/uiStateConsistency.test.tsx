import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { PackingWorkOrdersPage } from "../src/components/PackingWorkOrdersPage";
import { StageWorkOrdersPage } from "../src/components/StageWorkOrdersPage";
import { WorkOrdersTable } from "../src/components/WorkOrdersTable";
import { ApiError } from "../src/api/apiError";
import { CreateWorkOrderPage } from "../src/pages/CreateWorkOrderPage";
import { ManagerPanelPage } from "../src/pages/ManagerPanelPage";
import { WorkOrderDetailPage } from "../src/pages/WorkOrderDetailPage";
import type { StageWorkOrder } from "../src/types/process";
import type { WorkOrder } from "../src/types/workOrders";

vi.mock("../src/api/managerApi", () => ({
  assignWorkOrderPlan: vi.fn(),
  fetchPlannedWorkOrders: vi.fn(),
  fetchUnplannedWorkOrders: vi.fn(),
  reorderWorkOrderQueue: vi.fn(),
}));

vi.mock("../src/api/auditApi", () => ({
  fetchWorkOrderAuditEvents: vi.fn(),
}));

vi.mock("../src/api/processApi", () => ({
  completePacking: vi.fn(),
  fetchStageWorkOrders: vi.fn(),
  transitionStage: vi.fn(),
}));

vi.mock("../src/api/workOrdersApi", () => ({
  createWorkOrder: vi.fn(),
  deleteWorkOrderAttachment: vi.fn(),
  fetchWorkOrder: vi.fn(),
  fetchWorkOrderAttachments: vi.fn(),
  getWorkOrderAttachmentDownloadUrl: vi.fn(),
  markWorkOrderCompleteArrival: vi.fn(),
  uploadWorkOrderAttachment: vi.fn(),
}));

vi.mock("../src/utils/workOrderDisplay", () => ({
  formatWorkOrderPrimaryInfo: (workOrder: { order_number: string; customer_name?: string | null }) =>
    `${workOrder.order_number} :: ${workOrder.customer_name ?? "Brak firmy"}`,
  getHistoricalStageWorkOrderResultText: (workOrder: { counted_quantity?: number | null; batch_quantity?: number | null; planned_quantity: number }) =>
    `Wynik końcowy: ${workOrder.counted_quantity ?? workOrder.batch_quantity ?? workOrder.planned_quantity} szt.`,
  getHistoricalWorkOrderResultText: (workOrder: { completed_quantity: number }) => `Wynik końcowy: ${workOrder.completed_quantity} szt.`,
  getStageWorkOrderBadgeStack: () => [],
  getStageWorkOrderProgressText: (workOrder: { batch_quantity?: number | null; current_active_quantity: number; total_quantity: number }) =>
    `${workOrder.batch_quantity ?? workOrder.current_active_quantity} / ${workOrder.total_quantity} szt.`,
  getWorkOrderActiveCorrectionsText: () => null,
  getWorkOrderAttentionBadges: () => [],
  getWorkOrderBadgeStack: () => [],
  getWorkOrderCorrectionContextText: () => null,
  getWorkOrderProgressText: (workOrder: { total_quantity: number }) => `${workOrder.total_quantity} / ${workOrder.total_quantity} szt.`,
  getWorkOrderStatusSummary: () => "Status testowy",
}));

const managerApi = await import("../src/api/managerApi");
const auditApi = await import("../src/api/auditApi");
const processApi = await import("../src/api/processApi");
const workOrdersApi = await import("../src/api/workOrdersApi");

const fetchWorkOrderAuditEventsMock = vi.mocked(auditApi.fetchWorkOrderAuditEvents);
const fetchUnplannedWorkOrdersMock = vi.mocked(managerApi.fetchUnplannedWorkOrders);
const fetchPlannedWorkOrdersMock = vi.mocked(managerApi.fetchPlannedWorkOrders);
const reorderWorkOrderQueueMock = vi.mocked(managerApi.reorderWorkOrderQueue);
const fetchStageWorkOrdersMock = vi.mocked(processApi.fetchStageWorkOrders);
const transitionStageMock = vi.mocked(processApi.transitionStage);
const completePackingMock = vi.mocked(processApi.completePacking);
const createWorkOrderMock = vi.mocked(workOrdersApi.createWorkOrder);
const fetchWorkOrderMock = vi.mocked(workOrdersApi.fetchWorkOrder);
const fetchWorkOrderAttachmentsMock = vi.mocked(workOrdersApi.fetchWorkOrderAttachments);

function buildWorkOrder(id: number, orderNumber: string, queuePosition: number, customerName = "Klient"): WorkOrder {
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
    correction_reason_category: null,
    correction_reason_note: null,
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
    is_historical_correction: overrides.is_historical_correction ?? false,
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
  fetchWorkOrderAuditEventsMock.mockReset();
  fetchWorkOrderAuditEventsMock.mockResolvedValue([]);
  fetchUnplannedWorkOrdersMock.mockReset();
  fetchPlannedWorkOrdersMock.mockReset();
  reorderWorkOrderQueueMock.mockReset();
  fetchStageWorkOrdersMock.mockReset();
  transitionStageMock.mockReset();
  completePackingMock.mockReset();
  createWorkOrderMock.mockReset();
  fetchWorkOrderMock.mockReset();
  fetchWorkOrderAttachmentsMock.mockReset();
  fetchWorkOrderAttachmentsMock.mockResolvedValue([]);
});

afterEach(() => {
  vi.clearAllMocks();
});

describe("frontend state consistency", () => {
  function renderWorkOrderDetail(workOrderId = 1) {
    return render(
      <MemoryRouter initialEntries={[`/zlecenia/${workOrderId}`]}>
        <Routes>
          <Route path="/zlecenia/:id" element={<WorkOrderDetailPage />} />
        </Routes>
      </MemoryRouter>,
    );
  }

  it("submits external order number from the create form", async () => {
    createWorkOrderMock.mockResolvedValue({ ...buildWorkOrder(90, "WO-CREATE", 1), external_order_number: "EXT-77" });

    render(
      <MemoryRouter>
        <CreateWorkOrderPage />
      </MemoryRouter>,
    );

    fireEvent.change(screen.getByLabelText("Nr zewnętrzny"), { target: { value: " EXT-77 " } });
    fireEvent.change(screen.getByLabelText("Klient"), { target: { value: "ACME" } });
    fireEvent.change(screen.getByLabelText("Technologia"), { target: { value: "RAL" } });
    fireEvent.change(screen.getByLabelText("Kod RAL"), { target: { value: "RAL 7016" } });
    fireEvent.change(screen.getByLabelText("Producent farby"), { target: { value: "AkzoNobel" } });
    fireEvent.change(screen.getByLabelText("Data przyjęcia"), { target: { value: "2026-05-30" } });
    screen.getAllByLabelText("Do policzenia na produkcji").forEach((checkbox) => fireEvent.click(checkbox));
    fireEvent.click(screen.getByRole("button", { name: "Zapisz" }));

    await waitFor(() => {
      expect(createWorkOrderMock).toHaveBeenCalledWith(
        expect.objectContaining({
          external_order_number: "EXT-77",
          customer_name: "ACME",
          coating_type: "RAL",
        }),
      );
    });
  });

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

  it("starts surface preparation without count and submits counted quantity on finish", async () => {
    fetchStageWorkOrdersMock
      .mockResolvedValueOnce([
        buildStageWorkOrder({
          id: 11,
          order_number: "WO-SURFACE",
          planned_quantity: 10,
          counted_quantity: null,
          quantity_difference: null,
          stage_status: { stage: "SURFACE_PREPARATION", status: { value: "NOT_STARTED", label: "Nie rozpoczęto" } },
        }),
      ])
      .mockResolvedValueOnce([
        buildStageWorkOrder({
          id: 11,
          order_number: "WO-SURFACE",
          planned_quantity: 10,
          counted_quantity: null,
          quantity_difference: null,
          stage_status: { stage: "SURFACE_PREPARATION", status: { value: "IN_PROGRESS", label: "W toku" } },
        }),
      ])
      .mockResolvedValueOnce([
        buildStageWorkOrder({
          id: 11,
          order_number: "WO-SURFACE",
          planned_quantity: 10,
          counted_quantity: 8,
          quantity_difference: -2,
          stage_status: { stage: "SURFACE_PREPARATION", status: { value: "DONE", label: "Zakończone" } },
        }),
      ]);
    transitionStageMock.mockResolvedValue({} as never);

    render(
      <StageWorkOrdersPage
        stage="SURFACE_PREPARATION"
        title="Przygotowanie"
        emptyMessage="Brak zleceń"
      />,
    );

    await screen.findByText("WO-SURFACE :: Klient");
    fireEvent.click(screen.getByRole("button", { name: "Rozpocznij" }));

    await waitFor(() => {
      expect(transitionStageMock).toHaveBeenCalledWith(11, "SURFACE_PREPARATION", "start", undefined, undefined);
    });
    await screen.findByRole("button", { name: "Zakończ" });

    const finishButton = screen.getByRole("button", { name: "Zakończ" });
    expect((finishButton as HTMLButtonElement).disabled).toBe(true);

    fireEvent.change(screen.getByRole("spinbutton"), { target: { value: "8" } });
    fireEvent.click(finishButton);

    await waitFor(() => {
      expect(transitionStageMock).toHaveBeenLastCalledWith(
        11,
        "SURFACE_PREPARATION",
        "finish",
        undefined,
        { counted_quantity: 8 },
      );
    });
  });

  it("allows finishing automatic hanging from hanging station", async () => {
    fetchStageWorkOrdersMock
      .mockResolvedValueOnce([
        buildStageWorkOrder({
          id: 12,
          order_number: "WO-AUTO-HANG",
          production_type: { value: "AUTOMATIC", label: "Automatyczna" },
          stage_status: { stage: "HANGING", status: { value: "IN_PROGRESS", label: "W toku" } },
        }),
      ])
      .mockResolvedValueOnce([
        buildStageWorkOrder({
          id: 12,
          order_number: "WO-AUTO-HANG",
          production_type: { value: "AUTOMATIC", label: "Automatyczna" },
          stage_status: { stage: "HANGING", status: { value: "DONE", label: "Zakończone" } },
        }),
      ]);
    transitionStageMock.mockResolvedValue({} as never);

    render(
      <StageWorkOrdersPage
        stage="HANGING"
        title="Zawieszanie"
        emptyMessage="Brak zleceń"
      />,
    );

    await screen.findByText("WO-AUTO-HANG :: Klient");
    fireEvent.click(screen.getByRole("button", { name: "Zakończ" }));

    await waitFor(() => {
      expect(transitionStageMock).toHaveBeenCalledWith(12, "HANGING", "finish", undefined, undefined);
    });
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
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "niedomalowanie" } });
    fireEvent.click(screen.getByRole("button", { name: "Zatwierdź pakowanie" }));

    await screen.findByText("Nieprawidłowa ilość pakowania");
    await screen.findByText("WO-PACK :: Backend");
    await waitFor(() => expect(fetchStageWorkOrdersMock).toHaveBeenCalledTimes(2));
    await waitFor(() => {
      const reloadedInputs = screen.getAllByRole("spinbutton") as HTMLInputElement[];
      expect(reloadedInputs.map((input) => input.value)).toEqual(["5", "5", "0"]);
    });
  });

  it("requires a correction reason before submitting packing corrections", async () => {
    fetchStageWorkOrdersMock.mockResolvedValue([
      buildStageWorkOrder({
        id: 31,
        order_number: "WO-PACK-REASON",
        current_active_quantity: 4,
        planned_quantity: 4,
        stage_status: { stage: "PACKING", status: { value: "IN_PROGRESS", label: "W toku" } },
      }),
    ]);
    completePackingMock.mockResolvedValue({} as never);

    render(<PackingWorkOrdersPage />);

    await screen.findByText("WO-PACK-REASON :: Klient");

    const inputs = screen.getAllByRole("spinbutton");
    fireEvent.change(inputs[0], { target: { value: "4" } });
    fireEvent.change(inputs[1], { target: { value: "3" } });
    fireEvent.change(inputs[2], { target: { value: "1" } });

    const submitButton = screen.getByRole("button", { name: "Zatwierdź pakowanie" }) as HTMLButtonElement;
    expect(submitButton.disabled).toBe(true);

    fireEvent.change(screen.getByRole("combobox"), { target: { value: "inne" } });
    fireEvent.change(screen.getByPlaceholderText("Notatka"), { target: { value: "ryska przy profilu" } });
    await waitFor(() => expect(submitButton.disabled).toBe(false));
    fireEvent.click(submitButton);

    await waitFor(() => {
      expect(completePackingMock).toHaveBeenCalledWith(
        31,
        {
          counted_quantity: 4,
          ok_quantity: 3,
          correction_quantity: 1,
          correction_reason_category: "inne",
          correction_reason_note: "ryska przy profilu",
        },
        undefined,
      );
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

  it("does not render 0/X batch progress for merged correction in completed stage tab", async () => {
    fetchStageWorkOrdersMock.mockResolvedValue([
      buildStageWorkOrder({
        id: 60,
        order_number: "WO-CORR-ZERO",
        is_correction: true,
        is_historical_correction: true,
        total_quantity: 5,
        current_active_quantity: 0,
        batch_quantity: null,
        planned_quantity: 5,
        stage_status: { stage: "HANGING", status: { value: "DONE", label: "Zakończone" } },
      }),
    ]);
    fetchWorkOrderMock.mockResolvedValue({
      parent_order: { order_number: "WO-PARENT", total_quantity: 12 },
    } as never);

    render(
      <StageWorkOrdersPage
        stage="HANGING"
        title="Zawieszanie"
        emptyMessage="Brak zleceń"
      />,
    );

    await screen.findByRole("button", { name: "Pokaż zakończone" });
    fireEvent.click(screen.getByRole("button", { name: "Pokaż zakończone" }));

    await screen.findByText("Poprawiono 5 z 12 szt.");
    expect(screen.queryByText("Postęp partii: 0 / 5 szt.")).toBeNull();
  });

  it("renders only final result for completed normal work order in completed stage tab", async () => {
    fetchStageWorkOrdersMock.mockResolvedValue([
      buildStageWorkOrder({
        id: 63,
        order_number: "WO-STAGE-DONE",
        is_correction: false,
        total_quantity: 8,
        current_active_quantity: 0,
        batch_quantity: 8,
        planned_quantity: 8,
        stage_status: { stage: "HANGING", status: { value: "DONE", label: "Zakończone" } },
      }),
    ]);

    render(
      <StageWorkOrdersPage
        stage="HANGING"
        title="Zawieszanie"
        emptyMessage="Brak zleceń"
      />,
    );

    await screen.findByRole("button", { name: "Pokaż zakończone" });
    fireEvent.click(screen.getByRole("button", { name: "Pokaż zakończone" }));

    await screen.findByText("Wynik końcowy: 8 szt.");
    expect(screen.queryByText("Postęp partii: 8 / 8 szt.")).toBeNull();
  });

  it("renders batch progress for completed correction row until backend marks it as historical", async () => {
    fetchStageWorkOrdersMock.mockResolvedValue([
      buildStageWorkOrder({
        id: 62,
        order_number: "WO-CORR-ACTIVE",
        is_correction: true,
        is_historical_correction: false,
        total_quantity: 5,
        current_active_quantity: 2,
        batch_quantity: 2,
        planned_quantity: 5,
        stage_status: { stage: "HANGING", status: { value: "DONE", label: "Zakończone" } },
      }),
    ]);
    fetchWorkOrderMock.mockResolvedValue({
      parent_order: { order_number: "WO-PARENT", total_quantity: 12 },
    } as never);

    render(
      <StageWorkOrdersPage
        stage="HANGING"
        title="Zawieszanie"
        emptyMessage="Brak zleceń"
      />,
    );

    await screen.findByRole("button", { name: "Pokaż zakończone" });
    fireEvent.click(screen.getByRole("button", { name: "Pokaż zakończone" }));

    await screen.findByText("Postęp partii: 2 / 5 szt.");
    expect(screen.getByText("5 szt. poprawki z 12")).toBeTruthy();
  });

  it("does not render X/X batch progress for merged correction in completed packing tab and keeps only delta summary", async () => {
    fetchStageWorkOrdersMock.mockResolvedValue([
      buildStageWorkOrder({
        id: 61,
        order_number: "WO-CORR-FULL",
        is_correction: true,
        is_historical_correction: true,
        total_quantity: 5,
        current_active_quantity: 0,
        batch_quantity: 5,
        planned_quantity: 5,
        stage_status: { stage: "PACKING", status: { value: "DONE", label: "Zakończone" } },
      }),
    ]);
    fetchWorkOrderMock.mockResolvedValue({
      parent_order: { order_number: "WO-PARENT", total_quantity: 12 },
    } as never);

    render(<PackingWorkOrdersPage />);

    await screen.findByRole("button", { name: "Pokaż zakończone" });
    fireEvent.click(screen.getByRole("button", { name: "Pokaż zakończone" }));

    await screen.findByText("Poprawiono 5 z 12 szt.");
    expect(screen.queryByText("Postęp partii: 5 / 5 szt.")).toBeNull();
    expect(screen.getByText("Poprawiono 5 z 12 szt.")).toBeTruthy();
  });

  it("renders only final result for completed normal work order in completed packing tab", async () => {
    fetchStageWorkOrdersMock.mockResolvedValue([
      buildStageWorkOrder({
        id: 64,
        order_number: "WO-PACK-DONE",
        is_correction: false,
        total_quantity: 6,
        current_active_quantity: 0,
        counted_quantity: 6,
        planned_quantity: 6,
        stage_status: { stage: "PACKING", status: { value: "DONE", label: "Zakończone" } },
      }),
    ]);

    render(<PackingWorkOrdersPage />);

    await screen.findByRole("button", { name: "Pokaż zakończone" });
    fireEvent.click(screen.getByRole("button", { name: "Pokaż zakończone" }));

    await screen.findByText("Wynik końcowy: 6 szt.");
    expect(screen.queryByText("Postęp partii: 0 / 6 szt.")).toBeNull();
  });

  it("keeps progress visible for active normal work order rows", async () => {
    fetchStageWorkOrdersMock.mockResolvedValue([
      buildStageWorkOrder({
        id: 65,
        order_number: "WO-STAGE-ACTIVE",
        is_correction: false,
        total_quantity: 7,
        current_active_quantity: 3,
        batch_quantity: 3,
        planned_quantity: 7,
        stage_status: { stage: "HANGING", status: { value: "IN_PROGRESS", label: "W toku" } },
      }),
    ]);

    render(
      <StageWorkOrdersPage
        stage="HANGING"
        title="Zawieszanie"
        emptyMessage="Brak zleceń"
      />,
    );

    await screen.findByText("Postęp partii: 3 / 7 szt.");
    expect(screen.queryByText("Wynik końcowy: 3 szt.")).toBeNull();
  });

  it("renders READY rows in the work orders table as historical results only", () => {
    render(
      <MemoryRouter>
        <WorkOrdersTable
          workOrders={[
            {
              ...buildWorkOrder(80, "WO-TABLE-READY", 1, "Hotel"),
              completed_quantity: 10,
              current_active_quantity: 0,
              total_progress_quantity: 10,
              process_status: { value: "READY", label: "Gotowe" },
            },
          ]}
        />
      </MemoryRouter>,
    );

    expect(screen.getByText("Wynik końcowy: 10 szt.")).toBeTruthy();
    expect(screen.queryByText("10 / 10 szt.")).toBeNull();
    expect(screen.queryByText(/Aktywne/)).toBeNull();
  });

  it("keeps active progress visible in the work orders table", () => {
    render(
      <MemoryRouter>
        <WorkOrdersTable workOrders={[buildWorkOrder(81, "WO-TABLE-ACTIVE", 1, "India")]} />
      </MemoryRouter>,
    );

    expect(screen.getByText("10 / 10 szt.")).toBeTruthy();
    expect(screen.getAllByText(/Aktywne/).length).toBeGreaterThan(0);
  });

  it("does not use historical correction wording for active manager correction cards", async () => {
    fetchUnplannedWorkOrdersMock.mockResolvedValue([
      {
        ...buildWorkOrder(82, "WO-CORR-ACTIVE-MGR", 1, "Juliet"),
        total_quantity: 4,
        completed_quantity: 0,
        current_active_quantity: 4,
        total_progress_quantity: 0,
        is_correction: true,
        is_historical_correction: false,
        queue_namespace: { value: "CORRECTIONS", label: "Corrections" },
        parent_order: {
          id: 83,
          order_number: "WO-PARENT-MGR",
          title: "WO-PARENT-MGR",
          customer_name: "Juliet",
          ral_code: "RAL 9005",
          total_area_m2: null,
          total_quantity: 10,
          completed_quantity: 6,
          current_active_quantity: 0,
          is_correction: false,
          is_historical_correction: false,
          process_status: { value: "WAITING_FOR_CORRECTIONS", label: "Czeka na poprawki" },
        },
      },
    ]);
    fetchPlannedWorkOrdersMock.mockResolvedValue([]);

    render(<ManagerPanelPage />);

    await screen.findByText("WO-CORR-ACTIVE-MGR :: Juliet");
    expect(screen.getByText("Postęp: 4 / 4 szt.")).toBeTruthy();
    expect(screen.queryByText(/Poprawiono/)).toBeNull();
  });

  it("renders completed correction quantity context from manager payload after decoral merge", async () => {
    fetchUnplannedWorkOrdersMock.mockResolvedValue([]);
    fetchPlannedWorkOrdersMock.mockResolvedValue([
      {
        ...buildWorkOrder(1, "WO-PARENT", 1, "Alpha"),
        total_quantity: 10,
        completed_quantity: 10,
        current_active_quantity: 0,
        process_status: { value: "READY", label: "Gotowe" },
        coating_type: { value: "DECORAL", label: "Decoral" },
        correction_orders: [
          {
            id: 2,
            order_number: "WO-CORR",
            title: "WO-CORR",
            customer_name: "Alpha",
            ral_code: "RAL 9005",
            total_area_m2: null,
            total_quantity: 3,
            completed_quantity: 3,
            current_active_quantity: 0,
            is_correction: true,
            is_historical_correction: true,
            process_status: { value: "READY", label: "Gotowe" },
          },
        ],
      },
      {
        ...buildWorkOrder(2, "WO-CORR", 2, "Alpha"),
        total_quantity: 3,
        completed_quantity: 3,
        current_active_quantity: 0,
        is_correction: true,
        is_historical_correction: true,
        process_status: { value: "READY", label: "Gotowe" },
        coating_type: { value: "DECORAL", label: "Decoral" },
        queue_namespace: { value: "CORRECTIONS", label: "Corrections" },
        parent_order: {
          id: 1,
          order_number: "WO-PARENT",
          title: "WO-PARENT",
          customer_name: "Alpha",
          ral_code: "RAL 9005",
          total_area_m2: null,
          total_quantity: 10,
          completed_quantity: 10,
          current_active_quantity: 0,
          is_correction: false,
          is_historical_correction: false,
          process_status: { value: "READY", label: "Gotowe" },
        },
      },
    ]);

    render(<ManagerPanelPage />);

    await screen.findByRole("button", { name: "Pokaż zakończone" });
    fireEvent.click(screen.getByRole("button", { name: "Pokaż zakończone" }));

    await screen.findByText("Poprawka do WO-PARENT · Poprawiono 3 z 10 szt.");
    expect(screen.queryByText("0 / 3 szt.")).toBeNull();
  });

  it("shows only historical final result for completed normal work order in manager tab", async () => {
    fetchUnplannedWorkOrdersMock.mockResolvedValue([]);
    fetchPlannedWorkOrdersMock.mockResolvedValue([
      {
        ...buildWorkOrder(3, "WO-MANAGER-DONE", 1, "Gamma"),
        total_quantity: 9,
        completed_quantity: 9,
        current_active_quantity: 0,
        total_progress_quantity: 9,
        process_status: { value: "READY", label: "Gotowe" },
      },
    ]);

    render(<ManagerPanelPage />);

    await screen.findByRole("button", { name: "Pokaż zakończone" });
    fireEvent.click(screen.getByRole("button", { name: "Pokaż zakończone" }));

    await screen.findByText("Wynik końcowy: 9 szt.");
    expect(screen.queryByText("Postęp: 9 / 9 szt.")).toBeNull();
  });

  it("shows only final result for READY work order detail", async () => {
    fetchWorkOrderMock.mockResolvedValue({
      ...buildWorkOrder(70, "WO-READY-DETAIL", 1, "Delta"),
      completed_quantity: 10,
      current_active_quantity: 0,
      total_progress_quantity: 10,
      process_status: { value: "READY", label: "Gotowe" },
      status: { value: "FINISHED", label: "Zakończone" },
    });

    renderWorkOrderDetail(70);

    await screen.findAllByText("Wynik końcowy: 10 szt.");
    expect(screen.queryByText(/Postęp/)).toBeNull();
    expect(screen.queryByText(/Aktywne/)).toBeNull();
  });

  it("renders work order audit history on detail page", async () => {
    fetchWorkOrderMock.mockResolvedValue(buildWorkOrder(73, "WO-AUDIT-DETAIL", 1, "Foxtrot"));
    fetchWorkOrderAuditEventsMock.mockResolvedValue([
      {
        id: 1,
        event_type: "work_order.created",
        station_id: "OFFICE",
        work_order_id: 73,
        target_type: "work_order",
        target_id: 73,
        request_id: "trace-created",
        summary: "Created work order WO-AUDIT-DETAIL.",
        details: { order_number: "WO-AUDIT-DETAIL", is_incomplete_on_arrival: false },
        created_at: "2026-05-29T10:00:00Z",
      },
      {
        id: 2,
        event_type: "work_order.updated",
        station_id: "MANAGER",
        work_order_id: 73,
        target_type: "work_order",
        target_id: 73,
        request_id: "trace-updated",
        summary: "Updated work order WO-AUDIT-DETAIL.",
        details: { updated_fields: ["title"] },
        created_at: "2026-05-29T10:05:00Z",
      },
    ]);

    renderWorkOrderDetail(73);

    await screen.findByText("Historia zmian");
    expect(screen.getByText("Created work order WO-AUDIT-DETAIL.")).toBeTruthy();
    expect(screen.getByText("Updated work order WO-AUDIT-DETAIL.")).toBeTruthy();
    expect(screen.getByText("Biuro")).toBeTruthy();
    expect(screen.getByText("Kierownik")).toBeTruthy();
    expect(screen.getByText("Zmieniono: title")).toBeTruthy();
  });

  it("renders historical correction children in detail as delta only", async () => {
    fetchWorkOrderMock.mockResolvedValue({
      ...buildWorkOrder(71, "WO-PARENT-DETAIL", 1, "Echo"),
      total_quantity: 12,
      completed_quantity: 12,
      current_active_quantity: 0,
      total_progress_quantity: 12,
      process_status: { value: "READY", label: "Gotowe" },
      status: { value: "FINISHED", label: "Zakończone" },
      correction_orders: [
        {
          id: 72,
          order_number: "WO-CORR-DETAIL",
          title: "WO-CORR-DETAIL",
          customer_name: "Echo",
          ral_code: "RAL 9005",
          total_area_m2: null,
          total_quantity: 3,
          completed_quantity: 3,
          current_active_quantity: 0,
          is_correction: true,
          is_historical_correction: true,
          process_status: { value: "READY", label: "Gotowe" },
        },
      ],
    });

    renderWorkOrderDetail(71);

    await screen.findAllByText("Poprawiono 3 z 12 szt.");
    expect(screen.queryByText(/Postęp/)).toBeNull();
    expect(screen.queryByText(/Aktywne/)).toBeNull();
    expect(screen.queryByText("3/3")).toBeNull();
  });

  it("renders active correction children in detail with backend progress state", async () => {
    fetchWorkOrderMock.mockResolvedValue({
      ...buildWorkOrder(74, "WO-PARENT-ACTIVE-CORR", 1, "Golf"),
      process_status: { value: "WAITING_FOR_CORRECTIONS", label: "Czeka na poprawki" },
      correction_orders: [
        {
          id: 75,
          order_number: "WO-CORR-ACTIVE",
          title: "WO-CORR-ACTIVE",
          customer_name: "Golf",
          ral_code: "RAL 9005",
          total_area_m2: null,
          total_quantity: 4,
          completed_quantity: 1,
          current_active_quantity: 3,
          is_correction: true,
          is_historical_correction: false,
          process_status: { value: "PACKING", label: "Pakowanie" },
        },
      ],
    });

    renderWorkOrderDetail(74);

    await screen.findByText("WO-CORR-ACTIVE");
    expect(screen.getByText("Status: Pakowanie · Postęp: 1/4")).toBeTruthy();
    expect(screen.getByText("Postęp: 1/4 · Aktywne: 3")).toBeTruthy();
    expect(screen.queryByText("Poprawiono 4 z 10 szt.")).toBeNull();
  });
});
