import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { PackingWorkOrdersPage } from "../src/components/PackingWorkOrdersPage";
import { StageWorkOrdersPage } from "../src/components/StageWorkOrdersPage";
import { WorkOrdersTable } from "../src/components/WorkOrdersTable";
import { ApiError } from "../src/api/apiError";
import { PaintInventoryPage } from "../src/pages/PaintInventoryPage";
import { AutomaticProductionPage } from "../src/pages/AutomaticProductionPage";
import { CreateWorkOrderPage } from "../src/pages/CreateWorkOrderPage";
import { ManagerPanelPage } from "../src/pages/ManagerPanelPage";
import { WorkOrdersListPage } from "../src/pages/WorkOrdersListPage";
import { WorkOrderDetailPage } from "../src/pages/WorkOrderDetailPage";
import type { StageWorkOrder } from "../src/types/process";
import type { WorkOrder, WorkOrderRelationSummary } from "../src/types/workOrders";

vi.mock("../src/api/managerApi", () => ({
  assignWorkOrderPlan: vi.fn(),
  fetchCorrectionReasonReport: vi.fn(),
  fetchPlannedWorkOrders: vi.fn(),
  fetchUnplannedWorkOrders: vi.fn(),
  getCorrectionReasonReportExportUrl: vi.fn(() => "/manager/corrections/reason-report/export.csv"),
  reorderWorkOrderQueue: vi.fn(),
}));

vi.mock("../src/api/auditApi", () => ({
  fetchWorkOrderAuditEvents: vi.fn(),
}));

vi.mock("../src/api/processApi", () => ({
  completePacking: vi.fn(),
  fetchStageWorkOrders: vi.fn(),
  recordAutomaticPaintConsumption: vi.fn(),
  transitionStage: vi.fn(),
}));

vi.mock("../src/api/paintsApi", () => ({
  fetchPaintMovements: vi.fn(),
  fetchPaints: vi.fn(),
  lookupPaintStock: vi.fn(),
  recordPaintAdjustment: vi.fn(),
  recordPaintDelivery: vi.fn(),
}));

vi.mock("../src/api/workOrdersApi", () => ({
  createWorkOrder: vi.fn(),
  deleteWorkOrderAttachment: vi.fn(),
  fetchWorkOrders: vi.fn(),
  fetchWorkOrder: vi.fn(),
  fetchWorkOrderAttachments: vi.fn(),
  getWorkOrderAttachmentDownloadUrl: vi.fn(),
  markWorkOrderCompleteArrival: vi.fn(),
  updateWorkOrderReleaseStatus: vi.fn(),
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
  getWorkOrderAttentionBadges: (workOrder: { surface_preparation_quantity_difference?: number | null }) =>
    workOrder.surface_preparation_quantity_difference
      ? [{ label: `RÓŻNICA: ${workOrder.surface_preparation_quantity_difference} SZT.`, tone: "warning" }]
      : [],
  getWorkOrderBadgeStack: (workOrder: { process_status?: { value: string }; is_released_to_client?: boolean }) =>
    workOrder.process_status?.value === "READY"
      ? [{ label: workOrder.is_released_to_client ? "WYDANE" : "DO WYDANIA", tone: workOrder.is_released_to_client ? "success" : "warning" }]
      : [],
  getWorkOrderCorrectionContextText: () => null,
  getWorkOrderDiscrepancyText: (workOrder: { total_quantity: number; surface_preparation_counted_quantity?: number | null; surface_preparation_quantity_difference?: number | null }) =>
    workOrder.surface_preparation_counted_quantity !== null &&
    workOrder.surface_preparation_counted_quantity !== undefined &&
    workOrder.surface_preparation_quantity_difference
      ? `Przygotowanie: zadeklarowano ${workOrder.total_quantity}, policzono ${workOrder.surface_preparation_counted_quantity} (${workOrder.surface_preparation_quantity_difference} szt.)`
      : null,
  getWorkOrderProgressText: (workOrder: { total_quantity: number }) => `${workOrder.total_quantity} / ${workOrder.total_quantity} szt.`,
  getWorkOrderStatusSummary: () => "Status testowy",
}));

const managerApi = await import("../src/api/managerApi");
const auditApi = await import("../src/api/auditApi");
const paintsApi = await import("../src/api/paintsApi");
const processApi = await import("../src/api/processApi");
const workOrdersApi = await import("../src/api/workOrdersApi");

const fetchWorkOrderAuditEventsMock = vi.mocked(auditApi.fetchWorkOrderAuditEvents);
const fetchCorrectionReasonReportMock = vi.mocked(managerApi.fetchCorrectionReasonReport);
const fetchUnplannedWorkOrdersMock = vi.mocked(managerApi.fetchUnplannedWorkOrders);
const fetchPlannedWorkOrdersMock = vi.mocked(managerApi.fetchPlannedWorkOrders);
const fetchPaintsMock = vi.mocked(paintsApi.fetchPaints);
const fetchPaintMovementsMock = vi.mocked(paintsApi.fetchPaintMovements);
const lookupPaintStockMock = vi.mocked(paintsApi.lookupPaintStock);
const recordPaintDeliveryMock = vi.mocked(paintsApi.recordPaintDelivery);
const recordPaintAdjustmentMock = vi.mocked(paintsApi.recordPaintAdjustment);
const assignWorkOrderPlanMock = vi.mocked(managerApi.assignWorkOrderPlan);
const reorderWorkOrderQueueMock = vi.mocked(managerApi.reorderWorkOrderQueue);
const fetchStageWorkOrdersMock = vi.mocked(processApi.fetchStageWorkOrders);
const recordAutomaticPaintConsumptionMock = vi.mocked(processApi.recordAutomaticPaintConsumption);
const transitionStageMock = vi.mocked(processApi.transitionStage);
const completePackingMock = vi.mocked(processApi.completePacking);
const createWorkOrderMock = vi.mocked(workOrdersApi.createWorkOrder);
const fetchWorkOrdersMock = vi.mocked(workOrdersApi.fetchWorkOrders);
const fetchWorkOrderMock = vi.mocked(workOrdersApi.fetchWorkOrder);
const fetchWorkOrderAttachmentsMock = vi.mocked(workOrdersApi.fetchWorkOrderAttachments);
const getWorkOrderAttachmentDownloadUrlMock = vi.mocked(workOrdersApi.getWorkOrderAttachmentDownloadUrl);
const updateWorkOrderReleaseStatusMock = vi.mocked(workOrdersApi.updateWorkOrderReleaseStatus);

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
    work_order_kind: { value: "STANDARD", label: "Standardowe" },
    is_ocynk: false,
    correction_reason_category: null,
    correction_reason_note: null,
    parent_order: null,
    correction_orders: [],
    description: null,
    customer_name: customerName,
    ral_code: "RAL 9005",
    paint_code: "P-9005",
    paint_producer: "Test",
    paint_stock_snapshot_quantity_kg: 30,
    consumed_paint_quantity_kg: 0,
    status: { value: "ASSIGNED", label: "Przypisane" },
    process_status: { value: "PACKING", label: "Pakowanie" },
    coating_type: { value: "RAL", label: "RAL" },
    queue_blocked_by_resource: null,
    queue_blocked_reason: null,
    production_type: { value: "MANUAL", label: "Ręczna" },
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
    work_order_kind: overrides.work_order_kind ?? { value: "STANDARD", label: "Standardowe" },
    is_ocynk: overrides.is_ocynk ?? false,
    order_number: overrides.order_number,
    title: overrides.title ?? overrides.order_number,
    ral_code: overrides.ral_code ?? "RAL 9005",
    paint_code: overrides.paint_code ?? "P-9005",
    paint_producer: overrides.paint_producer ?? "Test",
    paint_stock_snapshot_quantity_kg: overrides.paint_stock_snapshot_quantity_kg ?? 30,
    consumed_paint_quantity_kg: overrides.consumed_paint_quantity_kg ?? 0,
    total_area_m2: overrides.total_area_m2 ?? null,
    total_quantity: overrides.total_quantity ?? 10,
    current_active_quantity: overrides.current_active_quantity ?? 10,
    batch_quantity: overrides.batch_quantity ?? null,
    planned_quantity: overrides.planned_quantity ?? 10,
    counted_quantity: overrides.counted_quantity ?? null,
    quantity_difference: overrides.quantity_difference ?? null,
    customer_name: overrides.customer_name ?? "Klient",
    profiles_quantity: overrides.profiles_quantity ?? null,
    profiles_to_count: overrides.profiles_to_count ?? false,
    accessories_quantity: overrides.accessories_quantity ?? null,
    accessories_to_count: overrides.accessories_to_count ?? false,
    queue_position: overrides.queue_position ?? 1,
    queue_namespace: overrides.queue_namespace ?? { value: "MAIN", label: "Główna" },
    production_type: overrides.production_type ?? { value: "MANUAL", label: "Ręczna" },
    coating_type: overrides.coating_type ?? { value: "RAL", label: "RAL" },
    batch_type: overrides.batch_type ?? "MAIN",
    batch_is_partial: overrides.batch_is_partial ?? false,
    stage_status: overrides.stage_status,
  };
}

function buildWorkOrderRelationSummary(
  overrides: Partial<WorkOrderRelationSummary> & Pick<WorkOrderRelationSummary, "id" | "order_number">,
): WorkOrderRelationSummary {
  return {
    id: overrides.id,
    order_number: overrides.order_number,
    external_order_number: overrides.external_order_number ?? null,
    title: overrides.title ?? overrides.order_number,
    customer_name: overrides.customer_name ?? "Klient",
    ral_code: overrides.ral_code ?? "RAL 9005",
    paint_code: overrides.paint_code ?? "P-9005",
    paint_stock_snapshot_quantity_kg: overrides.paint_stock_snapshot_quantity_kg ?? null,
    total_area_m2: overrides.total_area_m2 ?? null,
    total_quantity: overrides.total_quantity ?? 10,
    completed_quantity: overrides.completed_quantity ?? 0,
    current_active_quantity: overrides.current_active_quantity ?? 0,
    planned_pickup_date: overrides.planned_pickup_date ?? null,
    is_correction: overrides.is_correction ?? false,
    is_historical_correction: overrides.is_historical_correction ?? false,
    work_order_kind: overrides.work_order_kind ?? { value: "STANDARD", label: "Standardowe" },
    is_ocynk: overrides.is_ocynk ?? false,
    correction_reason_category: overrides.correction_reason_category ?? null,
    correction_reason_note: overrides.correction_reason_note ?? null,
    process_status: overrides.process_status ?? { value: "TO_BE_PLANNED", label: "Do zaplanowania" },
  };
}

beforeEach(() => {
  fetchWorkOrderAuditEventsMock.mockReset();
  fetchWorkOrderAuditEventsMock.mockResolvedValue([]);
  fetchCorrectionReasonReportMock.mockReset();
  fetchCorrectionReasonReportMock.mockResolvedValue([]);
  fetchUnplannedWorkOrdersMock.mockReset();
  fetchPlannedWorkOrdersMock.mockReset();
  assignWorkOrderPlanMock.mockReset();
  reorderWorkOrderQueueMock.mockReset();
  fetchStageWorkOrdersMock.mockReset();
  recordAutomaticPaintConsumptionMock.mockReset();
  transitionStageMock.mockReset();
  completePackingMock.mockReset();
  createWorkOrderMock.mockReset();
  fetchWorkOrdersMock.mockReset();
  fetchPaintsMock.mockReset();
  fetchPaintMovementsMock.mockReset();
  lookupPaintStockMock.mockReset();
  recordPaintDeliveryMock.mockReset();
  recordPaintAdjustmentMock.mockReset();
  fetchWorkOrderMock.mockReset();
  fetchWorkOrderAttachmentsMock.mockReset();
  getWorkOrderAttachmentDownloadUrlMock.mockReset();
  updateWorkOrderReleaseStatusMock.mockReset();
  fetchWorkOrderAttachmentsMock.mockResolvedValue([]);
  getWorkOrderAttachmentDownloadUrlMock.mockImplementation((workOrderId, attachmentId) => `/work-orders/${workOrderId}/attachments/${attachmentId}/download`);
});

afterEach(() => {
  vi.clearAllMocks();
});

describe("frontend state consistency", () => {
  function renderWorkOrderDetail(workOrderId = 1, search = "") {
    return render(
      <MemoryRouter initialEntries={[`/zlecenia/${workOrderId}${search}`]}>
        <Routes>
          <Route path="/zlecenia/:id" element={<WorkOrderDetailPage />} />
        </Routes>
      </MemoryRouter>,
    );
  }

  it("submits external order number from the create form", async () => {
    createWorkOrderMock.mockResolvedValue({ ...buildWorkOrder(90, "WO-CREATE", 1), external_order_number: "EXT-77" });
    lookupPaintStockMock.mockResolvedValue({
      paint_id: 1,
      ral_code: "RAL 7016",
      paint_producer: "AkzoNobel",
      paint_code: "P-7016",
      current_quantity_kg: 30,
      exists_in_inventory: true,
    });

    render(
      <MemoryRouter>
        <CreateWorkOrderPage />
      </MemoryRouter>,
    );

    fireEvent.change(screen.getByLabelText("Nr zewnętrzny"), { target: { value: " EXT-77 " } });
    fireEvent.change(screen.getByLabelText("Klient"), { target: { value: "ACME" } });
    fireEvent.change(screen.getByLabelText("Technologia"), { target: { value: "RAL" } });
    fireEvent.change(screen.getByLabelText("Rodzaj zlecenia"), { target: { value: "PRZEMALOWANKA" } });
    fireEvent.click(screen.getByLabelText("Ocynk"));
    fireEvent.change(screen.getByLabelText("Kod RAL"), { target: { value: "RAL 7016" } });
    fireEvent.change(screen.getByLabelText("Producent farby"), { target: { value: "AkzoNobel" } });
    fireEvent.change(screen.getByLabelText("Kod farby"), { target: { value: "P-7016" } });
    await screen.findByText(/aktualny stan 30 kg/i);
    fireEvent.change(screen.getByLabelText("Data przyjęcia"), { target: { value: "2026-05-30" } });
    screen.getAllByLabelText("Do policzenia na produkcji").forEach((checkbox) => fireEvent.click(checkbox));
    fireEvent.click(screen.getByRole("button", { name: "Zapisz" }));

    await waitFor(() => {
      expect(createWorkOrderMock).toHaveBeenCalledWith(
        expect.objectContaining({
          external_order_number: "EXT-77",
          customer_name: "ACME",
          coating_type: "RAL",
          work_order_kind: "PRZEMALOWANKA",
          is_ocynk: true,
          paint_code: "P-7016",
        }),
      );
    });
  });

  it("requires known profile and accessory quantities to sum to the total quantity", async () => {
    createWorkOrderMock.mockResolvedValue({ ...buildWorkOrder(91, "WO-CATEGORY-SUM", 1), total_quantity: 10, profiles_quantity: 8, accessories_quantity: 2 });
    lookupPaintStockMock.mockResolvedValue({
      paint_id: 1,
      ral_code: "RAL 7016",
      paint_producer: "AkzoNobel",
      paint_code: "P-7016",
      current_quantity_kg: 30,
      exists_in_inventory: true,
    });

    render(
      <MemoryRouter>
        <CreateWorkOrderPage />
      </MemoryRouter>,
    );

    fireEvent.change(screen.getByLabelText("Klient"), { target: { value: "ACME" } });
    fireEvent.change(screen.getByLabelText("Technologia"), { target: { value: "RAL" } });
    fireEvent.change(screen.getByLabelText("Kod RAL"), { target: { value: "RAL 7016" } });
    fireEvent.change(screen.getByLabelText("Producent farby"), { target: { value: "AkzoNobel" } });
    fireEvent.change(screen.getByLabelText("Kod farby"), { target: { value: "P-7016" } });
    await screen.findByText(/aktualny stan 30 kg/i);
    fireEvent.change(screen.getByLabelText("Data przyjęcia"), { target: { value: "2026-05-30" } });
    fireEvent.change(screen.getByLabelText("Ilość całkowita"), { target: { value: "10" } });
    const categoryInputs = screen.getAllByPlaceholderText("Podaj ilość");
    fireEvent.change(categoryInputs[0], { target: { value: "8" } });
    fireEvent.change(categoryInputs[1], { target: { value: "1" } });
    expect(screen.getByText("Suma kategorii: 9 / 10. Brakuje 1 szt.")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Zapisz" }));

    expect(await screen.findByText("Suma profili i akcesoriów musi być równa ilości całkowitej")).toBeTruthy();
    expect(createWorkOrderMock).not.toHaveBeenCalled();

    fireEvent.change(categoryInputs[1], { target: { value: "2" } });
    expect(screen.getByText("Suma kategorii: 10 / 10")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Zapisz" }));

    await waitFor(() => {
      expect(createWorkOrderMock).toHaveBeenCalledWith(
        expect.objectContaining({
          total_quantity: 10,
          profiles_quantity: 8,
          accessories_quantity: 2,
        }),
      );
    });
  });

  it("records delivery and manual adjustment on the paint inventory page", async () => {
    fetchPaintsMock
      .mockResolvedValueOnce({
        items: [
          {
            id: 11,
            ral_code: "RAL 7016",
            paint_producer: "AkzoNobel",
            paint_code: "P-7016",
            current_quantity_kg: 30,
            created_at: "2026-06-02T10:00:00Z",
            updated_at: "2026-06-02T10:00:00Z",
          },
        ],
        total: 1,
        limit: 100,
        offset: 0,
      })
      .mockResolvedValueOnce({
        items: [
          {
            id: 11,
            ral_code: "RAL 7016",
            paint_producer: "AkzoNobel",
            paint_code: "P-7016",
            current_quantity_kg: 45,
            created_at: "2026-06-02T10:00:00Z",
            updated_at: "2026-06-02T11:00:00Z",
          },
        ],
        total: 1,
        limit: 100,
        offset: 0,
      })
      .mockResolvedValueOnce({
        items: [
          {
            id: 11,
            ral_code: "RAL 7016",
            paint_producer: "AkzoNobel",
            paint_code: "P-7016",
            current_quantity_kg: 42,
            created_at: "2026-06-02T10:00:00Z",
            updated_at: "2026-06-02T12:00:00Z",
          },
        ],
        total: 1,
        limit: 100,
        offset: 0,
      });
    fetchPaintMovementsMock
      .mockResolvedValueOnce({
        items: [],
        total: 0,
        limit: 100,
        offset: 0,
      })
      .mockResolvedValueOnce({
        items: [
          {
            id: 1,
            paint_id: 11,
            work_order_id: null,
            movement_type: { value: "DELIVERY", label: "Dostawa" },
            quantity_delta_kg: 15,
            resulting_quantity_kg: 45,
            movement_date: "2026-06-02",
            note: "Dostawa poranna",
            created_at: "2026-06-02T11:00:00Z",
          },
        ],
        total: 1,
        limit: 100,
        offset: 0,
      })
      .mockResolvedValueOnce({
        items: [
          {
            id: 2,
            paint_id: 11,
            work_order_id: null,
            movement_type: { value: "MANUAL_ADJUSTMENT", label: "Korekta ręczna" },
            quantity_delta_kg: -3,
            resulting_quantity_kg: 42,
            movement_date: "2026-06-02",
            note: "Korekta stanu",
            created_at: "2026-06-02T12:00:00Z",
          },
        ],
        total: 1,
        limit: 100,
        offset: 0,
      });
    recordPaintDeliveryMock.mockResolvedValue({
      id: 11,
      ral_code: "RAL 7016",
      paint_producer: "AkzoNobel",
      paint_code: "P-7016",
      current_quantity_kg: 45,
      created_at: "2026-06-02T10:00:00Z",
      updated_at: "2026-06-02T11:00:00Z",
    });
    recordPaintAdjustmentMock.mockResolvedValue({
      id: 11,
      ral_code: "RAL 7016",
      paint_producer: "AkzoNobel",
      paint_code: "P-7016",
      current_quantity_kg: 42,
      created_at: "2026-06-02T10:00:00Z",
      updated_at: "2026-06-02T12:00:00Z",
    });

    render(
      <MemoryRouter>
        <PaintInventoryPage />
      </MemoryRouter>,
    );

    await screen.findByText("RAL 7016");
    fireEvent.change(screen.getAllByPlaceholderText("RAL")[0], { target: { value: "RAL 7016" } });
    fireEvent.change(screen.getAllByPlaceholderText("Producent farby")[0], { target: { value: "AkzoNobel" } });
    fireEvent.change(screen.getAllByPlaceholderText("Kod farby")[0], { target: { value: "P-7016" } });
    fireEvent.change(screen.getByPlaceholderText("Ilość [kg]"), { target: { value: "15" } });
    fireEvent.change(screen.getByPlaceholderText("Notatka opcjonalna"), { target: { value: "Dostawa poranna" } });
    fireEvent.click(screen.getByRole("button", { name: "Zapisz dostawę" }));

    await waitFor(() => {
      expect(recordPaintDeliveryMock).toHaveBeenCalledWith(
        expect.objectContaining({
          ral_code: "RAL 7016",
          paint_producer: "AkzoNobel",
          paint_code: "P-7016",
          quantity_kg: 15,
        }),
      );
    });

    fireEvent.change(screen.getAllByPlaceholderText("RAL")[1], { target: { value: "RAL 7016" } });
    fireEvent.change(screen.getAllByPlaceholderText("Producent farby")[1], { target: { value: "AkzoNobel" } });
    fireEvent.change(screen.getAllByPlaceholderText("Kod farby")[1], { target: { value: "P-7016" } });
    fireEvent.change(screen.getByPlaceholderText("Korekta [+/- kg]"), { target: { value: "-3" } });
    fireEvent.change(screen.getByPlaceholderText("Powód korekty"), { target: { value: "Korekta stanu" } });
    fireEvent.click(screen.getByRole("button", { name: "Zapisz korektę" }));

    await waitFor(() => {
      expect(recordPaintAdjustmentMock).toHaveBeenCalledWith(
        expect.objectContaining({
          ral_code: "RAL 7016",
          paint_producer: "AkzoNobel",
          paint_code: "P-7016",
          quantity_delta_kg: -3,
          note: "Korekta stanu",
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

  it("shows correction reason report in the manager panel", async () => {
    fetchUnplannedWorkOrdersMock.mockResolvedValue([]);
    fetchPlannedWorkOrdersMock.mockResolvedValue([]);
    fetchCorrectionReasonReportMock.mockResolvedValue([
      {
        correction_reason_category: "niedomalowanie",
        work_order_count: 2,
        total_correction_quantity: 7,
      },
      {
        correction_reason_category: null,
        work_order_count: 1,
        total_correction_quantity: 3,
      },
    ]);

    render(<ManagerPanelPage />);

    await screen.findByText("Statystyka poprawek");
    expect(await screen.findByText("niedomalowanie")).toBeTruthy();
    expect(screen.getByText("Bez kategorii")).toBeTruthy();
    expect(screen.getByText("7 szt.")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Eksport CSV" }).getAttribute("href")).toBe(
      "/manager/corrections/reason-report/export.csv",
    );
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

  it("shows verification columns on surface preparation without generic metadata columns", async () => {
    fetchStageWorkOrdersMock.mockResolvedValueOnce([
      buildStageWorkOrder({
        id: 31,
        order_number: "WO-VERIFY",
        customer_name: "ACME",
        profiles_quantity: 42,
        accessories_quantity: null,
        accessories_to_count: true,
        stage_status: { stage: "SURFACE_PREPARATION", status: { value: "NOT_STARTED", label: "Nie rozpoczęto" } },
      }),
    ]);

    render(
      <StageWorkOrdersPage
        stage="SURFACE_PREPARATION"
        title="Przygotowanie"
        emptyMessage="Brak zleceń"
      />,
    );

    expect(await screen.findByText("WO-VERIFY :: ACME")).toBeTruthy();
    expect(screen.queryByRole("table")).toBeNull();
    expect(screen.getByText("Profile")).toBeTruthy();
    expect(screen.getByText("Akcesoria")).toBeTruthy();
    expect(screen.getByText("42 szt.")).toBeTruthy();
    expect(screen.getByText("Do policzenia")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Szczegóły / załączniki" }).getAttribute("href")).toBe("/zlecenia/31");
    expect(screen.queryByText("Metraż")).toBeNull();
    expect(screen.queryByText("Technologia")).toBeNull();
    expect(screen.queryByText("Typ produkcji")).toBeNull();
    expect(screen.queryByText("Partia")).toBeNull();
  });

  it("shows area and paint columns on production stations", async () => {
    fetchStageWorkOrdersMock.mockResolvedValueOnce([
      buildStageWorkOrder({
        id: 32,
        order_number: "WO-PROD-READ",
        customer_name: "ACME",
        total_area_m2: 12.5,
        paint_producer: "Tiger",
        ral_code: "RAL 7016",
        stage_status: { stage: "PRODUCTION", status: { value: "NOT_STARTED", label: "Nie rozpoczęto" } },
      }),
    ]);

    render(
      <StageWorkOrdersPage
        stage="PRODUCTION"
        productionType="MANUAL"
        title="Produkcja ręczna"
        emptyMessage="Brak zleceń"
      />,
    );

    expect(await screen.findByText("WO-PROD-READ :: ACME")).toBeTruthy();
    expect(screen.queryByRole("table")).toBeNull();
    expect(screen.getByText("Metraż")).toBeTruthy();
    expect(screen.getByText("12.5 m2")).toBeTruthy();
    expect(screen.getByText("Farba")).toBeTruthy();
    expect(screen.getByText("Tiger / RAL 7016")).toBeTruthy();
    expect(screen.queryByText("Profile")).toBeNull();
    expect(screen.queryByText("Technologia")).toBeNull();
    expect(screen.queryByText("Typ produkcji")).toBeNull();
    expect(screen.queryByText("Partia")).toBeNull();
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

  it("shows the hanging queue in the automatic production panel without stage actions", async () => {
    fetchStageWorkOrdersMock.mockResolvedValueOnce([
      buildStageWorkOrder({
        id: 13,
        order_number: "WO-AUTO-QUEUE",
        production_type: { value: "AUTOMATIC", label: "Automatyczna" },
        stage_status: { stage: "HANGING", status: { value: "NOT_STARTED", label: "Nie rozpoczęte" } },
      }),
    ]);

    render(<AutomaticProductionPage />);

    expect(await screen.findByText("WO-AUTO-QUEUE :: Klient")).toBeTruthy();
    expect(fetchStageWorkOrdersMock).toHaveBeenCalledWith("PRODUCTION", "AUTOMATIC");
    expect(screen.getByText("Kolejka automatu obejmuje zlecenia do zawieszania, w zawieszaniu i na linii automatycznej.")).toBeTruthy();
    expect(screen.getByText("Nie rozpoczęte")).toBeTruthy();
    expect(screen.getByText("Status automatu")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Rozpocznij" })).toBeNull();
    expect(screen.getByText("Zużycie farby wpiszesz po rozpoczęciu zawieszania.")).toBeTruthy();
  });

  it("records paint consumption from the automatic production panel before hanging is finished", async () => {
    fetchStageWorkOrdersMock
      .mockResolvedValueOnce([
        buildStageWorkOrder({
          id: 15,
          order_number: "WO-AUTO-PAINT",
          production_type: { value: "AUTOMATIC", label: "Automatyczna" },
          stage_status: { stage: "HANGING", status: { value: "IN_PROGRESS", label: "W toku" } },
          paint_code: "P-7016-MAT",
          consumed_paint_quantity_kg: 0,
        }),
      ])
      .mockResolvedValueOnce([
        buildStageWorkOrder({
          id: 15,
          order_number: "WO-AUTO-PAINT",
          production_type: { value: "AUTOMATIC", label: "Automatyczna" },
          stage_status: { stage: "HANGING", status: { value: "IN_PROGRESS", label: "W toku" } },
          paint_code: "P-7016-MAT",
          consumed_paint_quantity_kg: 12.5,
        }),
      ]);
    recordAutomaticPaintConsumptionMock.mockResolvedValue({} as never);

    render(<AutomaticProductionPage />);

    await screen.findByText("WO-AUTO-PAINT :: Klient");
    fireEvent.click(screen.getByRole("button", { name: "25 kg" }));
    fireEvent.click(screen.getByRole("button", { name: "Dodaj karton" }));
    fireEvent.change(screen.getByLabelText("Pozostało w ostatnim kartonie [kg]"), { target: { value: "12.5" } });
    expect(screen.getByText("Zużycie do zapisu: 12.5 kg")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Zapisz zużycie farby" }));

    await waitFor(() => {
      expect(recordAutomaticPaintConsumptionMock).toHaveBeenCalledWith(15, { consumed_paint_quantity_kg: 12.5 });
    });
    await screen.findByText("Zużyto: 12.5 kg");
  });

  it("shows automatic active hanging in packing without packing actions", async () => {
    fetchStageWorkOrdersMock.mockResolvedValueOnce([
      buildStageWorkOrder({
        id: 14,
        order_number: "WO-AUTO-PACK-PREVIEW",
        customer_name: "ACME",
        profiles_quantity: 17,
        accessories_to_count: true,
        paint_producer: "Tiger",
        ral_code: "RAL 7016",
        production_type: { value: "AUTOMATIC", label: "Automatyczna" },
        stage_status: { stage: "HANGING", status: { value: "IN_PROGRESS", label: "W toku" } },
      }),
    ]);

    render(<PackingWorkOrdersPage />);

    expect(await screen.findByText("WO-AUTO-PACK-PREVIEW :: ACME")).toBeTruthy();
    expect(fetchStageWorkOrdersMock).toHaveBeenCalledWith("PACKING");
    expect(screen.getByText("Profile")).toBeTruthy();
    expect(screen.getByText("Akcesoria")).toBeTruthy();
    expect(screen.getByText("17 szt.")).toBeTruthy();
    expect(screen.getByText("Do policzenia")).toBeTruthy();
    expect(screen.getByText("Tiger / RAL 7016")).toBeTruthy();
    expect(screen.queryByText("Dane główne")).toBeNull();
    expect(screen.getByText("W zawieszaniu - oczekuje na pakowanie")).toBeTruthy();
    expect(screen.getByText("Czeka na koniec zawieszania")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Zatwierdź pakowanie" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Rozpocznij" })).toBeNull();
    expect(screen.queryAllByRole("spinbutton")).toHaveLength(0);
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
    const correctionInputs = screen.getAllByRole("spinbutton");
    fireEvent.change(correctionInputs[3], { target: { value: "1" } });
    fireEvent.change(correctionInputs[4], { target: { value: "0" } });
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
    const correctionInputs = screen.getAllByRole("spinbutton");
    fireEvent.change(correctionInputs[3], { target: { value: "1" } });
    fireEvent.change(correctionInputs[4], { target: { value: "0" } });

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
          correction_profiles_quantity: 1,
          correction_accessories_quantity: 0,
          correction_reason_category: "inne",
          correction_reason_note: "ryska przy profilu",
        },
        undefined,
      );
    });
  });

  it("shows packing split balance inside the active order card", async () => {
    fetchStageWorkOrdersMock.mockResolvedValue([
      buildStageWorkOrder({
        id: 32,
        order_number: "WO-PACK-CARD",
        customer_name: "Pakowalnia",
        profiles_quantity: 8,
        accessories_quantity: 2,
        current_active_quantity: 6,
        planned_quantity: 6,
        stage_status: { stage: "PACKING", status: { value: "IN_PROGRESS", label: "W toku" } },
      }),
    ]);

    render(<PackingWorkOrdersPage />);

    await screen.findByText("WO-PACK-CARD :: Pakowalnia");
    expect(screen.queryByRole("table")).toBeNull();
    expect(screen.getByText("Bilans pakowania: Wpisz policzoną ilość")).toBeTruthy();

    const inputs = screen.getAllByRole("spinbutton");
    expect(inputs).toHaveLength(3);
    fireEvent.change(inputs[0], { target: { value: "6" } });
    expect(screen.getByText("Bilans pakowania: Suma zgodna")).toBeTruthy();
    fireEvent.change(inputs[1], { target: { value: "4" } });
    expect(screen.getByText("Bilans pakowania: Brakuje 2 szt.")).toBeTruthy();
    fireEvent.change(inputs[2], { target: { value: "2" } });
    expect(screen.getByText("Bilans pakowania: Suma zgodna")).toBeTruthy();
    expect(screen.getByText("Podział poprawki: Brakuje 2 szt.")).toBeTruthy();

    const correctionInputs = screen.getAllByRole("spinbutton");
    expect(correctionInputs).toHaveLength(5);
    fireEvent.change(correctionInputs[3], { target: { value: "1" } });
    expect(screen.getByText("Podział poprawki: Brakuje 1 szt.")).toBeTruthy();
    fireEvent.change(correctionInputs[4], { target: { value: "1" } });
    expect(screen.getByText("Podział poprawki: Suma zgodna")).toBeTruthy();
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

  it("shows backend discrepancy signal in the office table", () => {
    render(
      <MemoryRouter>
        <WorkOrdersTable
          workOrders={[
            {
              ...buildWorkOrder(84, "WO-DISCREPANCY", 1, "Kilo"),
              surface_preparation_counted_quantity: 8,
              surface_preparation_quantity_difference: -2,
            },
          ]}
        />
      </MemoryRouter>,
    );

    expect(screen.getByText("RÓŻNICA: -2 SZT.")).toBeTruthy();
    expect(screen.getByText("Przygotowanie: zadeklarowano 10, policzono 8 (-2 szt.)")).toBeTruthy();
  });

  it("groups office work orders into intake, production, and ready buckets", async () => {
    fetchWorkOrdersMock.mockResolvedValue({
      items: [
        {
          ...buildWorkOrder(91, "WO-OFFICE-INTAKE", 1, "Lima"),
          process_status: { value: "TO_BE_PLANNED", label: "Do zaplanowania" },
        },
        {
          ...buildWorkOrder(92, "WO-OFFICE-PROD", 2, "Mike"),
          process_status: { value: "PACKING", label: "Pakowanie" },
        },
        {
          ...buildWorkOrder(93, "WO-OFFICE-READY", 3, "November"),
          completed_quantity: 10,
          current_active_quantity: 0,
          total_progress_quantity: 10,
          process_status: { value: "READY", label: "Gotowe" },
          is_released_to_client: true,
          released_to_client_at: "2026-05-31T08:00:00Z",
        },
      ],
      total: 3,
      limit: 50,
      offset: 0,
    });

    render(
      <MemoryRouter>
        <WorkOrdersListPage />
      </MemoryRouter>,
    );

    expect(await screen.findByText("WO-OFFICE-INTAKE")).toBeTruthy();
    expect(screen.getByRole("button", { name: /Zlecenia 1/ })).toBeTruthy();
    expect(screen.getByRole("button", { name: /Na produkcji 1/ })).toBeTruthy();
    expect(screen.getByRole("button", { name: /Gotowe 1/ })).toBeTruthy();
    expect(screen.queryByText("WO-OFFICE-PROD")).toBeNull();
    expect(screen.queryByText("WO-OFFICE-READY")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: /Na produkcji 1/ }));

    expect(await screen.findByText("WO-OFFICE-PROD")).toBeTruthy();
    expect(screen.queryByText("WO-OFFICE-INTAKE")).toBeNull();
    expect(screen.queryByText("WO-OFFICE-READY")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: /Gotowe 1/ }));

    expect(await screen.findByText("WO-OFFICE-READY")).toBeTruthy();
    expect(screen.getByText("Wynik końcowy: 10 szt.")).toBeTruthy();
    expect(screen.getByText("WYDANE")).toBeTruthy();
    expect(screen.queryByText("WO-OFFICE-PROD")).toBeNull();
  });

  it("submits external order number search from the office list", async () => {
    fetchWorkOrdersMock
      .mockResolvedValueOnce({
        items: [
          {
            ...buildWorkOrder(94, "WO-OFFICE-INITIAL", 1, "Oscar"),
            external_order_number: "CLIENT-1",
            process_status: { value: "TO_BE_PLANNED", label: "Do zaplanowania" },
          },
        ],
        total: 1,
        limit: 50,
        offset: 0,
      })
      .mockResolvedValueOnce({
        items: [
          {
            ...buildWorkOrder(95, "WO-OFFICE-SEARCH", 1, "Papa"),
            external_order_number: "CLIENT-42",
            process_status: { value: "TO_BE_PLANNED", label: "Do zaplanowania" },
          },
        ],
        total: 1,
        limit: 50,
        offset: 0,
      });

    render(
      <MemoryRouter>
        <WorkOrdersListPage />
      </MemoryRouter>,
    );

    expect(await screen.findByText("WO-OFFICE-INITIAL")).toBeTruthy();

    fireEvent.change(screen.getByLabelText("Numer zewnętrzny"), { target: { value: " CLIENT-42 " } });
    fireEvent.click(screen.getByRole("button", { name: "Szukaj" }));

    await waitFor(() => expect(fetchWorkOrdersMock).toHaveBeenLastCalledWith({ externalOrderNumber: "CLIENT-42" }));
    expect(await screen.findByText("WO-OFFICE-SEARCH")).toBeTruthy();
    expect(screen.queryByText("WO-OFFICE-INITIAL")).toBeNull();
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
          external_order_number: null,
          title: "WO-PARENT-MGR",
          customer_name: "Juliet",
          ral_code: "RAL 9005",
          paint_code: "P-9005",
          total_area_m2: null,
          total_quantity: 10,
          completed_quantity: 6,
          current_active_quantity: 0,
          planned_pickup_date: null,
          is_correction: false,
          is_historical_correction: false,
          work_order_kind: { value: "STANDARD", label: "Standardowe" },
          is_ocynk: false,
          correction_reason_category: null,
          correction_reason_note: null,
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

  it("shows original pickup context and active-queue default while planning corrections", async () => {
    const correction = {
      ...buildWorkOrder(91, "WO-CORR-PLAN", 0, "Hotel"),
      total_quantity: 4,
      is_correction: true,
      queue_namespace: { value: "CORRECTIONS", label: "Corrections" },
      process_status: { value: "TO_BE_PLANNED", label: "Do zaplanowania" },
      production_type: null,
      queue_position: null,
      planned_pickup_date: "2026-06-18",
      parent_order: {
        id: 90,
        order_number: "WO-PARENT-PLAN",
        external_order_number: null,
        title: "WO-PARENT-PLAN",
        customer_name: "Hotel",
        ral_code: "RAL 9005",
        paint_code: "P-9005",
        total_area_m2: null,
        total_quantity: 10,
        completed_quantity: 6,
        current_active_quantity: 0,
        planned_pickup_date: "2026-06-18",
        is_correction: false,
        is_historical_correction: false,
        work_order_kind: { value: "STANDARD", label: "Standardowe" },
        is_ocynk: false,
        correction_reason_category: null,
        correction_reason_note: null,
        process_status: { value: "WAITING_FOR_CORRECTIONS", label: "Czeka na poprawki" },
      },
    } satisfies WorkOrder;
    fetchUnplannedWorkOrdersMock.mockResolvedValueOnce([correction]).mockResolvedValueOnce([]);
    fetchPlannedWorkOrdersMock
      .mockResolvedValueOnce([
        buildWorkOrder(1, "WO-ACTIVE-1", 1, "Alpha"),
        buildWorkOrder(2, "WO-ACTIVE-2", 2, "Beta"),
      ])
      .mockResolvedValueOnce([
        buildWorkOrder(1, "WO-ACTIVE-1", 1, "Alpha"),
        buildWorkOrder(2, "WO-ACTIVE-2", 2, "Beta"),
      ]);
    assignWorkOrderPlanMock.mockResolvedValue({
      ...correction,
      production_type: { value: "AUTOMATIC", label: "Automatyczna" },
      queue_position: 3,
    });

    render(<ManagerPanelPage />);

    await screen.findByText("WO-CORR-PLAN :: Hotel");
    expect(screen.getByText("Termin oryginału: 18.06.2026")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Poprawka do WO-PARENT-PLAN" }).getAttribute("href")).toBe(
      "/zlecenia/90?station_context=MANAGER",
    );
    expect((screen.getByLabelText("Pozycja") as HTMLInputElement).value).toBe("3");

    fireEvent.click(screen.getByRole("button", { name: "Automat" }));
    fireEvent.click(screen.getByRole("button", { name: "Zaplanuj" }));

    await waitFor(() => {
      expect(assignWorkOrderPlanMock).toHaveBeenCalledWith(91, {
        production_type: "AUTOMATIC",
        queue_position: 3,
      });
    });
  });

  it("shows backend discrepancy signal in the active manager queue", async () => {
    fetchUnplannedWorkOrdersMock.mockResolvedValue([]);
    fetchPlannedWorkOrdersMock.mockResolvedValue([
      {
        ...buildWorkOrder(85, "WO-MANAGER-DISCREPANCY", 1, "Lemon"),
        surface_preparation_counted_quantity: 8,
        surface_preparation_quantity_difference: -2,
      },
    ]);

    render(<ManagerPanelPage />);

    await screen.findByText("WO-MANAGER-DISCREPANCY");
    expect(screen.getByText("RÓŻNICA: -2 SZT.")).toBeTruthy();
    expect(screen.getByText("Przygotowanie: zadeklarowano 10, policzono 8 (-2 szt.)")).toBeTruthy();
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
          buildWorkOrderRelationSummary({
            id: 2,
            order_number: "WO-CORR",
            customer_name: "Alpha",
            ral_code: "RAL 9005",
            paint_code: "P-9005",
            total_quantity: 3,
            completed_quantity: 3,
            is_correction: true,
            is_historical_correction: true,
            process_status: { value: "READY", label: "Gotowe" },
          }),
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
        parent_order: buildWorkOrderRelationSummary({
          id: 1,
          order_number: "WO-PARENT",
          customer_name: "Alpha",
          ral_code: "RAL 9005",
          paint_code: "P-9005",
          total_quantity: 10,
          completed_quantity: 10,
          current_active_quantity: 0,
          process_status: { value: "READY", label: "Gotowe" },
        }),
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

  it("keeps station-origin work order details read-only while allowing attachment downloads", async () => {
    fetchWorkOrderMock.mockResolvedValue({
      ...buildWorkOrder(71, "WO-STATION-DETAIL", 1, "Echo"),
      completed_quantity: 10,
      current_active_quantity: 0,
      total_progress_quantity: 10,
      process_status: { value: "READY", label: "Gotowe" },
      status: { value: "FINISHED", label: "Zakończone" },
    });
    fetchWorkOrderAttachmentsMock.mockResolvedValue([
      {
        id: 12,
        work_order_id: 71,
        original_filename: "rysunek.pdf",
        stored_filename: "stored.pdf",
        storage_path: "71/stored.pdf",
        content_type: "application/pdf",
        file_size: 1200,
        attachment_type: "RYSUNEK",
        description: null,
        uploaded_at: "2026-05-27T08:00:00Z",
      },
    ]);

    renderWorkOrderDetail(71, "?station_context=PACKING");

    await screen.findByText("rysunek.pdf");
    expect(screen.getByRole("link", { name: "Pobierz" }).getAttribute("href")).toBe(
      "/work-orders/71/attachments/12/download",
    );
    expect(screen.getByRole("link", { name: "Wróć do listy" }).getAttribute("href")).toBe("/pakowanie");
    expect(screen.queryByRole("button", { name: "Dodaj załącznik" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Usuń" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Oznacz jako wydane" })).toBeNull();
  });

  it("shows backend discrepancy signal on work order detail", async () => {
    fetchWorkOrderMock.mockResolvedValue({
      ...buildWorkOrder(71, "WO-DISCREPANCY-DETAIL", 1, "Echo"),
      surface_preparation_counted_quantity: 8,
      surface_preparation_quantity_difference: -2,
    });

    renderWorkOrderDetail(71);

    await screen.findByText("Policzono na przygotowaniu");
    expect(screen.getByText("Rozbieżność ilości")).toBeTruthy();
    expect(screen.getByText("Przygotowanie: zadeklarowano 10, policzono 8 (-2 szt.)")).toBeTruthy();
  });

  it("renders paint snapshot and usage on work order detail", async () => {
    fetchWorkOrderMock.mockResolvedValue({
      ...buildWorkOrder(72, "WO-PAINT-DETAIL", 1, "Paint Client"),
      paint_code: "RAL7016-MAT",
      paint_stock_snapshot_quantity_kg: 12,
      consumed_paint_quantity_kg: 16.2,
    });

    renderWorkOrderDetail(72);

    await screen.findByText("Farba");
    expect(screen.getByText("RAL7016-MAT")).toBeTruthy();
    expect(screen.getByText("12 kg")).toBeTruthy();
    expect(screen.getByText("16.2 kg")).toBeTruthy();
    expect(
      screen.getByText(/Stan przy przyjęciu to historyczny snapshot zapisany automatycznie z magazynu/),
    ).toBeTruthy();
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

  it("updates release status from a ready work order detail page", async () => {
    const readyWorkOrder = {
      ...buildWorkOrder(74, "WO-RELEASE", 1, "Golf"),
      completed_quantity: 10,
      current_active_quantity: 0,
      total_progress_quantity: 10,
      process_status: { value: "READY", label: "Gotowe" } as const,
      status: { value: "FINISHED", label: "Skończone" } as const,
      is_released_to_client: false,
      released_to_client_at: null,
    };
    const releasedWorkOrder = {
      ...readyWorkOrder,
      is_released_to_client: true,
      released_to_client_at: "2026-05-30T12:00:00Z",
    };
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);
    fetchWorkOrderMock.mockResolvedValueOnce(readyWorkOrder).mockResolvedValueOnce(releasedWorkOrder);
    updateWorkOrderReleaseStatusMock.mockResolvedValue(releasedWorkOrder);

    try {
      renderWorkOrderDetail(74);

      fireEvent.click(await screen.findByRole("button", { name: "Oznacz jako wydane" }));

      await waitFor(() => expect(updateWorkOrderReleaseStatusMock).toHaveBeenCalledWith(74, true));
      expect(confirmSpy).toHaveBeenCalledWith("Czy oznaczyć to zlecenie jako wydane klientowi?");
      expect(await screen.findByText("Wydane")).toBeTruthy();
    } finally {
      confirmSpy.mockRestore();
    }
  });

  it("does not show release status action in manager station context", async () => {
    fetchWorkOrderMock.mockResolvedValue({
      ...buildWorkOrder(75, "WO-RELEASE-MANAGER", 1, "Hotel"),
      completed_quantity: 10,
      current_active_quantity: 0,
      total_progress_quantity: 10,
      process_status: { value: "READY", label: "Gotowe" },
      status: { value: "FINISHED", label: "Skończone" },
      is_released_to_client: false,
      released_to_client_at: null,
    });

    renderWorkOrderDetail(75, "?station_context=MANAGER");

    await screen.findByText("Do wydania");
    expect(screen.queryByRole("button", { name: "Oznacz jako wydane" })).toBeNull();
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
          external_order_number: null,
          title: "WO-CORR-DETAIL",
          customer_name: "Echo",
          ral_code: "RAL 9005",
          paint_code: "P-9005",
          total_area_m2: null,
          total_quantity: 3,
          completed_quantity: 3,
          current_active_quantity: 0,
          planned_pickup_date: null,
          is_correction: true,
          is_historical_correction: true,
          work_order_kind: { value: "STANDARD", label: "Standardowe" },
          is_ocynk: false,
          correction_reason_category: null,
          correction_reason_note: null,
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
          external_order_number: null,
          title: "WO-CORR-ACTIVE",
          customer_name: "Golf",
          ral_code: "RAL 9005",
          paint_code: "P-9005",
          total_area_m2: null,
          total_quantity: 4,
          completed_quantity: 1,
          current_active_quantity: 3,
          planned_pickup_date: null,
          is_correction: true,
          is_historical_correction: false,
          work_order_kind: { value: "STANDARD", label: "Standardowe" },
          is_ocynk: false,
          correction_reason_category: null,
          correction_reason_note: null,
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
