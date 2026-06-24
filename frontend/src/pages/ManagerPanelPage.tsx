import { DragEvent, useEffect, useRef, useState } from "react";

import { usePolling, STATION_POLL_INTERVAL_MS } from "../hooks/usePolling";
import {
  assignWorkOrderPlan,
  fetchAutoScheduleProposal,
  fetchCorrectionReasonReport,
  fetchPlannedWorkOrders,
  fetchScheduleConfig,
  fetchUnplannedWorkOrders,
  getCorrectionReasonReportExportUrl,
  reorderWorkOrderQueue,
  setWorkOrderPlanningPriority,
  updateScheduleConfig,
  updateWorkOrderProductionType,
} from "../api/managerApi";
import type {
  AutoScheduleProposal,
  CorrectionReasonReportItem,
  ScheduleRuleConfigItem,
} from "../types/manager";
import type { PlanningPriorityValue, ProductionTypeValue, WorkOrder } from "../types/workOrders";
import { isApiError } from "../api/apiError";
import { getMutationErrorMessage } from "../utils/mutationError";
import {
  assignSequentialQueuePositions,
  buildQueueReorderRequest,
  getQueueRevisionFromPlannedOrders,
  moveWorkOrderWithinQueueSlots,
} from "../utils/queueReorder";
import { buildWorkOrderDetailHref } from "../api/stationContext";
import { WorkOrderPrimaryInfoLine } from "../components/WorkOrderPrimaryInfoLine";
import { CapacityBoard } from "../components/CapacityBoard";
import {
  getWorkOrderActiveCorrectionsText,
  getWorkOrderAttentionBadges,
  getWorkOrderBadgeStack,
  getWorkOrderDiscrepancyText,
  getHistoricalWorkOrderResultText,
  getWorkOrderProgressText,
  type DisplayBadge,
} from "../utils/workOrderDisplay";

type QueueFilter = "ALL" | "NORMAL" | "CORRECTIONS";
type UnplannedSort = "NONE" | "COLOR" | "COMPANY" | "DEADLINE";

interface AuthoritativeQueueSnapshot {
  active: WorkOrder[];
  completed: WorkOrder[];
}

// Both production lines, in the order they are shown left-to-right on the boards.
const PRODUCTION_LINES: Array<{ value: ProductionTypeValue; label: string }> = [
  { value: "AUTOMATIC", label: "Automat" },
  { value: "MANUAL", label: "Ręczna" },
];

const productionTypeOptions = PRODUCTION_LINES;

function getProductionTypeLabel(value: ProductionTypeValue | null | undefined): string {
  if (value === "MANUAL") {
    return "Ręczna";
  }

  if (value === "AUTOMATIC") {
    return "Automat";
  }

  return "-";
}

function isOnLine(workOrder: WorkOrder, line: ProductionTypeValue): boolean {
  return workOrder.production_type?.value === line;
}

function formatDate(value: string | null | undefined): string {
  if (!value) {
    return "-";
  }

  const [year, month, day] = value.split("-").map(Number);
  if (year && month && day) {
    return new Intl.DateTimeFormat("pl-PL").format(new Date(year, month - 1, day));
  }

  return new Intl.DateTimeFormat("pl-PL").format(new Date(value));
}

function splitPlannedWorkOrders(workOrders: WorkOrder[]) {
  return {
    active: workOrders.filter((workOrder) => workOrder.process_status.value !== "READY"),
    completed: workOrders.filter((workOrder) => workOrder.process_status.value === "READY"),
  };
}

function sortUnplannedWorkOrders(workOrders: WorkOrder[], sort: UnplannedSort): WorkOrder[] {
  if (sort === "NONE") {
    return workOrders;
  }

  return [...workOrders].sort((a, b) => {
    if (sort === "COLOR") {
      return a.ral_code.localeCompare(b.ral_code, "pl");
    }
    if (sort === "COMPANY") {
      return a.customer_name.localeCompare(b.customer_name, "pl");
    }
    if (sort === "DEADLINE") {
      if (!a.planned_pickup_date && !b.planned_pickup_date) return 0;
      if (!a.planned_pickup_date) return 1;
      if (!b.planned_pickup_date) return -1;
      return a.planned_pickup_date.localeCompare(b.planned_pickup_date);
    }
    return 0;
  });
}

function filterQueueByType(workOrders: WorkOrder[], queueFilter: QueueFilter): WorkOrder[] {
  if (queueFilter === "NORMAL") {
    return workOrders.filter((workOrder) => !workOrder.is_correction);
  }
  if (queueFilter === "CORRECTIONS") {
    return workOrders.filter((workOrder) => workOrder.is_correction);
  }
  return workOrders;
}

function buildCorrectionReference(workOrder: WorkOrder): string {
  if (!workOrder.is_correction) {
    return "";
  }

  if (workOrder.parent_order?.order_number) {
    return `Poprawka do ${workOrder.parent_order.order_number}`;
  }

  return "Poprawka do zlecenia nadrzędnego";
}

function buildCorrectionQuantityContext(workOrder: WorkOrder): string {
  if (!workOrder.is_correction) {
    return "";
  }

  if (!workOrder.is_historical_correction) {
    return "";
  }

  const parentQuantity = workOrder.parent_order?.total_quantity;
  if (typeof parentQuantity === "number") {
    return `Poprawiono ${workOrder.total_quantity} z ${parentQuantity} szt.`;
  }

  return `Poprawiono ${workOrder.total_quantity} szt.`;
}

function buildOriginalPickupContext(workOrder: WorkOrder): string {
  if (!workOrder.is_correction) {
    return "";
  }

  return `Termin oryginału: ${formatDate(workOrder.parent_order?.planned_pickup_date ?? workOrder.planned_pickup_date)}`;
}

function formatCorrectionReasonCategory(category: string | null): string {
  return category?.trim() || "Bez kategorii";
}

function badgeClasses(tone: DisplayBadge["tone"]): string {
  switch (tone) {
    case "info":
      return "bg-sky-100 text-sky-800";
    case "warning":
      return "bg-amber-100 text-amber-800";
    case "success":
      return "bg-emerald-100 text-emerald-700";
    case "accent":
      return "bg-violet-100 text-violet-800";
    case "danger":
      return "bg-rose-100 text-rose-700";
    case "neutral":
      return "bg-slate-100 text-slate-700";
  }
}

function formatPaintKg(value: number | null | undefined): string {
  if (value === null || value === undefined) {
    return "-";
  }

  return `${value} kg`;
}

function renderPaintShortageWarning(workOrder: WorkOrder) {
  if (!workOrder.paint_inventory_insufficient_for_prediction) {
    return null;
  }

  return (
    <div className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
      <p className="font-semibold">Farby nie starczy na to zlecenie.</p>
      <p className="mt-1">
        Predykcja: {formatPaintKg(workOrder.predicted_paint_quantity_kg)}. Aktualny stan: {formatPaintKg(workOrder.current_paint_stock_quantity_kg)}.
        Brakuje około {formatPaintKg(workOrder.paint_inventory_shortage_quantity_kg)} i trzeba domówić farbę.
      </p>
    </div>
  );
}

export function ManagerPanelPage() {
  const [queueFilter, setQueueFilter] = useState<QueueFilter>("ALL");
  const [unplannedSort, setUnplannedSort] = useState<UnplannedSort>("NONE");
  const [unplannedWorkOrders, setUnplannedWorkOrders] = useState<WorkOrder[]>([]);
  const [activePlannedWorkOrders, setActivePlannedWorkOrders] = useState<WorkOrder[]>([]);
  const [completedPlannedWorkOrders, setCompletedPlannedWorkOrders] = useState<WorkOrder[]>([]);
  const [correctionReasonReport, setCorrectionReasonReport] = useState<CorrectionReasonReportItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [planningWorkOrderId, setPlanningWorkOrderId] = useState<number | null>(null);
  const [isSavingQueueOrder, setIsSavingQueueOrder] = useState(false);
  const [hasPendingQueueChanges, setHasPendingQueueChanges] = useState(false);
  const [draggedWorkOrderId, setDraggedWorkOrderId] = useState<number | null>(null);
  const [changingProductionTypeId, setChangingProductionTypeId] = useState<number | null>(null);
  const [changingPriorityId, setChangingPriorityId] = useState<number | null>(null);
  const [showCompleted, setShowCompleted] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const [editLine, setEditLine] = useState<ProductionTypeValue>("AUTOMATIC");
  const [scheduleProposal, setScheduleProposal] = useState<AutoScheduleProposal | null>(null);
  const [isAutoArranging, setIsAutoArranging] = useState(false);
  const [scheduleRules, setScheduleRules] = useState<ScheduleRuleConfigItem[] | null>(null);
  const [showRulesConfig, setShowRulesConfig] = useState(false);
  const [isSavingRules, setIsSavingRules] = useState(false);
  const authoritativeQueueRef = useRef<AuthoritativeQueueSnapshot | null>(null);

  const isAllQueueFilter = queueFilter === "ALL";
  const correctionReasonReportExportUrl = getCorrectionReasonReportExportUrl();

  const filteredUnplannedWorkOrders = sortUnplannedWorkOrders(
    filterQueueByType(unplannedWorkOrders, queueFilter),
    unplannedSort,
  );

  function lineActiveOrders(line: ProductionTypeValue): WorkOrder[] {
    return assignSequentialQueuePositions(
      activePlannedWorkOrders.filter((workOrder) => isOnLine(workOrder, line)),
    );
  }

  function lineCompletedOrders(line: ProductionTypeValue): WorkOrder[] {
    const active = activePlannedWorkOrders.filter((workOrder) => isOnLine(workOrder, line));
    return assignSequentialQueuePositions(
      completedPlannedWorkOrders.filter((workOrder) => isOnLine(workOrder, line)),
      active.length + 1,
    );
  }

  function getLineRevision(line: ProductionTypeValue): string | null {
    const snapshot = authoritativeQueueRef.current;
    if (!snapshot) {
      return null;
    }

    const lineOrders = [...snapshot.active, ...snapshot.completed].filter((workOrder) => isOnLine(workOrder, line));
    return getQueueRevisionFromPlannedOrders(lineOrders);
  }

  function restoreAuthoritativeQueueSnapshot() {
    const authoritativeQueue = authoritativeQueueRef.current;

    if (!authoritativeQueue) {
      return;
    }

    setActivePlannedWorkOrders(authoritativeQueue.active);
    setCompletedPlannedWorkOrders(authoritativeQueue.completed);
  }

  async function loadManagerData(options?: { preserveErrorMessage?: boolean; background?: boolean }): Promise<boolean> {
    const background = options?.background ?? false;
    if (!background) {
      setIsLoading(true);
      if (!options?.preserveErrorMessage) {
        setErrorMessage(null);
      }
    }

    try {
      const [unplanned, planned, nextCorrectionReasonReport] = await Promise.all([
        fetchUnplannedWorkOrders(),
        fetchPlannedWorkOrders(),
        fetchCorrectionReasonReport(),
      ]);
      const splitPlanned = splitPlannedWorkOrders(planned);

      setUnplannedWorkOrders(unplanned);
      setActivePlannedWorkOrders(splitPlanned.active);
      setCompletedPlannedWorkOrders(splitPlanned.completed);
      setCorrectionReasonReport(nextCorrectionReasonReport);
      if (!background) {
        setHasPendingQueueChanges(false);
      }
      authoritativeQueueRef.current = {
        active: splitPlanned.active,
        completed: splitPlanned.completed,
      };
      return true;
    } catch (error) {
      if (!background) {
        setErrorMessage(error instanceof Error ? error.message : "Nie udało się pobrać panelu kierownika");
      }
      return false;
    } finally {
      if (!background) {
        setIsLoading(false);
      }
    }
  }

  useEffect(() => {
    void loadManagerData();
  }, []);

  // Auto-refresh so the planning queue reflects changes from other devices without a
  // reload. Paused whenever the manager is mid-edit (planning, dragging, saving, or
  // has unsaved queue changes) so a poll never overwrites local edits.
  usePolling(
    () => {
      void loadManagerData({ background: true });
    },
    STATION_POLL_INTERVAL_MS,
    !hasPendingQueueChanges &&
      !isSavingQueueOrder &&
      planningWorkOrderId === null &&
      draggedWorkOrderId === null &&
      changingProductionTypeId === null,
  );

  function replaceLineActiveOrders(line: ProductionTypeValue, nextLineActive: WorkOrder[]) {
    setActivePlannedWorkOrders((current) => {
      const otherLines = current.filter((workOrder) => !isOnLine(workOrder, line));
      return [...otherLines, ...nextLineActive];
    });
  }

  async function handlePlanWorkOrder(workOrderId: number) {
    setPlanningWorkOrderId(workOrderId);
    setErrorMessage(null);
    setSuccessMessage(null);

    try {
      // No position — the backend appends the order to the end of the selected line's queue.
      await assignWorkOrderPlan(workOrderId, { production_type: editLine });
      await loadManagerData();
      setSuccessMessage("Zlecenie trafiło na koniec planu");
    } catch (error) {
      const message = getMutationErrorMessage(
        error,
        "Nie udało się zaplanować zlecenia. Panel został odświeżony do aktualnego stanu.",
      );
      const reloaded = await loadManagerData({ preserveErrorMessage: true });

      if (reloaded) {
        setErrorMessage(message);
      }
    } finally {
      setPlanningWorkOrderId(null);
    }
  }

  async function saveLineQueueOrder(lineActive: WorkOrder[], line: ProductionTypeValue) {
    const revision = getLineRevision(line);
    if (!revision) {
      setHasPendingQueueChanges(true);
      setErrorMessage("Nie udało się odczytać wersji kolejki. Odśwież panel kierownika i spróbuj ponownie.");
      return;
    }

    const payload = buildQueueReorderRequest(lineActive, revision, line);

    setIsSavingQueueOrder(true);
    setErrorMessage(null);
    setSuccessMessage(null);

    try {
      await reorderWorkOrderQueue(payload);
      await loadManagerData();
      setSuccessMessage("Kolejność została zaktualizowana");
    } catch (error) {
      restoreAuthoritativeQueueSnapshot();
      setHasPendingQueueChanges(false);

      const message = isApiError(error) && error.status === 409
        ? "Konflikt zapisu kolejki. Odświeżono panel do aktualnego stanu backendu."
        : getMutationErrorMessage(error, "Nie udało się zapisać kolejności. Odświeżono panel do aktualnego stanu backendu.");
      const reloaded = await loadManagerData({ preserveErrorMessage: true });

      if (reloaded) {
        setErrorMessage(message);
      }
    } finally {
      setIsSavingQueueOrder(false);
    }
  }

  async function handleSaveQueueOrder() {
    const lineActive = lineActiveOrders(editLine);
    if (lineActive.length === 0) {
      return;
    }

    await saveLineQueueOrder(lineActive, editLine);
  }

  // Painting auto-scheduler (NA33) — AUTOMATIC line only in v1. While the manager is idle on the
  // automatic plan, refresh the rule config (once) and a non-committal proposal so the "lepsze
  // ułożenie" suggestion banner can show. Skipped mid-edit so it never fights local drag/preview.
  useEffect(() => {
    if (!isEditing || editLine !== "AUTOMATIC") {
      return;
    }
    let cancelled = false;
    void (async () => {
      try {
        if (scheduleRules === null) {
          const config = await fetchScheduleConfig("AUTOMATIC");
          if (!cancelled) {
            setScheduleRules(config.rules);
          }
        }
        if (!hasPendingQueueChanges && !isSavingQueueOrder && !isLoading) {
          const proposal = await fetchAutoScheduleProposal("AUTOMATIC");
          if (!cancelled) {
            setScheduleProposal(proposal);
          }
        }
      } catch {
        // The suggestion is best-effort; a failure must not break planning.
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isEditing, editLine, hasPendingQueueChanges, isSavingQueueOrder, isLoading, activePlannedWorkOrders]);

  async function handleAutoArrange() {
    setIsAutoArranging(true);
    setErrorMessage(null);
    setSuccessMessage(null);
    try {
      const proposal = await fetchAutoScheduleProposal(editLine);
      setScheduleProposal(proposal);
      if (proposal.proposed_order.length === 0) {
        setSuccessMessage("Brak zleceń do ułożenia na tej linii.");
        return;
      }
      replaceLineActiveOrders(editLine, proposal.proposed_order);
      setHasPendingQueueChanges(true);
      const reduction = proposal.colour_changeover_reduction;
      setSuccessMessage(
        reduction > 0
          ? `Proponowana kolejność: o ${reduction} mniej zmian koloru. Sprawdź i zapisz.`
          : "Kolejność jest już optymalna — możesz zapisać bez zmian.",
      );
    } catch (error) {
      setErrorMessage(getMutationErrorMessage(error, "Nie udało się ułożyć kolejności automatycznie."));
    } finally {
      setIsAutoArranging(false);
    }
  }

  function handleMoveRule(index: number, direction: -1 | 1) {
    setScheduleRules((current) => {
      if (!current) {
        return current;
      }
      const target = index + direction;
      if (target < 0 || target >= current.length) {
        return current;
      }
      const next = [...current];
      [next[index], next[target]] = [next[target], next[index]];
      return next;
    });
  }

  function handleToggleRule(index: number) {
    setScheduleRules((current) =>
      current ? current.map((rule, i) => (i === index ? { ...rule, enabled: !rule.enabled } : rule)) : current,
    );
  }

  async function handleSaveRules() {
    if (!scheduleRules) {
      return;
    }
    setIsSavingRules(true);
    setErrorMessage(null);
    setSuccessMessage(null);
    try {
      const updated = await updateScheduleConfig(editLine, {
        rules: scheduleRules.map((rule) => ({ key: rule.key, enabled: rule.enabled })),
      });
      setScheduleRules(updated.rules);
      setSuccessMessage("Reguły układania zapisane.");
      const proposal = await fetchAutoScheduleProposal(editLine);
      setScheduleProposal(proposal);
    } catch (error) {
      setErrorMessage(getMutationErrorMessage(error, "Nie udało się zapisać reguł układania."));
    } finally {
      setIsSavingRules(false);
    }
  }

  function handleQueueDragStart(event: DragEvent<HTMLElement>, workOrderId: number) {
    if (!isAllQueueFilter) {
      return;
    }

    if (event.dataTransfer) {
      event.dataTransfer.effectAllowed = "move";
      if (typeof event.dataTransfer.setData === "function") {
        event.dataTransfer.setData("text/plain", String(workOrderId));
      }
    }
    setDraggedWorkOrderId(workOrderId);
    setSuccessMessage(null);
  }

  function handleQueueDragOver(event: DragEvent<HTMLElement>) {
    event.preventDefault();
    event.dataTransfer.dropEffect = "move";
  }

  function handleQueueDragEnd() {
    setDraggedWorkOrderId(null);
  }

  function handleQueueDrop(event: DragEvent<HTMLElement>, targetWorkOrderId: number) {
    event.preventDefault();
    if (!isAllQueueFilter) {
      return;
    }

    const dragPayload = event.dataTransfer && typeof event.dataTransfer.getData === "function"
      ? event.dataTransfer.getData("text/plain").trim()
      : "";
    const fallbackDraggedWorkOrderId = dragPayload ? Number(dragPayload) : null;
    const resolvedDraggedWorkOrderId = draggedWorkOrderId ?? fallbackDraggedWorkOrderId;

    if (resolvedDraggedWorkOrderId === null || Number.isNaN(resolvedDraggedWorkOrderId)) {
      return;
    }

    const lineActive = lineActiveOrders(editLine);
    const reorderedWorkOrders = moveWorkOrderWithinQueueSlots(
      lineActive,
      resolvedDraggedWorkOrderId,
      targetWorkOrderId,
    );
    setDraggedWorkOrderId(null);

    if (reorderedWorkOrders === lineActive) {
      return;
    }

    replaceLineActiveOrders(editLine, reorderedWorkOrders);
    setHasPendingQueueChanges(true);
    void saveLineQueueOrder(reorderedWorkOrders, editLine);
  }

  function canChangeProductionType(workOrder: WorkOrder): boolean {
    if (workOrder.process_status.value === "READY") return false;
    if (!workOrder.production_type) return false;
    const blockingStages = new Set(["HANGING", "PRODUCTION"]);
    const blockingStatuses = new Set(["IN_PROGRESS", "DONE"]);
    return !workOrder.stage_states.some(
      (ss) => blockingStages.has(ss.stage.value) && blockingStatuses.has(ss.status.value),
    );
  }

  async function handleChangeProductionType(workOrderId: number, newType: ProductionTypeValue) {
    setChangingProductionTypeId(workOrderId);
    setErrorMessage(null);
    setSuccessMessage(null);

    try {
      await updateWorkOrderProductionType(workOrderId, { production_type: newType });
      await loadManagerData();
      setSuccessMessage("Zlecenie przeniesiono na koniec drugiego planu");
    } catch (error) {
      const message = getMutationErrorMessage(error, "Nie udało się zmienić typu produkcji");
      await loadManagerData({ preserveErrorMessage: true });
      setErrorMessage(message);
    } finally {
      setChangingProductionTypeId(null);
    }
  }

  async function handleSetPlanningPriority(
    workOrderId: number,
    priority: PlanningPriorityValue | null,
  ) {
    setChangingPriorityId(workOrderId);
    setErrorMessage(null);
    setSuccessMessage(null);

    try {
      await setWorkOrderPlanningPriority(workOrderId, { planning_priority: priority });
      await loadManagerData();
      setSuccessMessage(
        priority === "PINNED"
          ? "Zlecenie przypięte — układanie automatyczne nie ruszy go z miejsca"
          : priority === "URGENT"
            ? "Zlecenie oznaczone jako pilne — trafi na początek linii"
            : "Zdjęto blokadę planowania",
      );
    } catch (error) {
      const message = getMutationErrorMessage(error, "Nie udało się zmienić priorytetu planowania");
      await loadManagerData({ preserveErrorMessage: true });
      setErrorMessage(message);
    } finally {
      setChangingPriorityId(null);
    }
  }

  function renderPlanningPriorityControls(workOrder: WorkOrder) {
    const current = workOrder.planning_priority;
    const isChanging = changingPriorityId === workOrder.id;
    const toggles: { value: PlanningPriorityValue; label: string; activeLabel: string }[] = [
      { value: "PINNED", label: "Przypnij", activeLabel: "Przypięte" },
      { value: "URGENT", label: "Pilne", activeLabel: "Pilne" },
    ];
    return (
      <div className="inline-flex items-center gap-1">
        {toggles.map((toggle) => {
          const isActive = current === toggle.value;
          return (
            <button
              key={toggle.value}
              type="button"
              disabled={isChanging}
              aria-pressed={isActive}
              onClick={() =>
                void handleSetPlanningPriority(workOrder.id, isActive ? null : toggle.value)
              }
              className={[
                "rounded-full border px-3 py-1 text-xs font-semibold transition disabled:cursor-not-allowed",
                isActive
                  ? toggle.value === "URGENT"
                    ? "border-rose-300 bg-rose-100 text-rose-800"
                    : "border-accent/40 bg-accent/10 text-accent"
                  : "border-line bg-white text-steel hover:border-accent/40 hover:text-accent",
              ].join(" ")}
              title={
                toggle.value === "PINNED"
                  ? "Zablokuj zlecenie na bieżącej pozycji — „Ułóż automatycznie” go nie ruszy"
                  : "Wymuś zlecenie na początek linii"
              }
            >
              {isChanging ? "..." : isActive ? `✓ ${toggle.activeLabel}` : toggle.label}
            </button>
          );
        })}
      </div>
    );
  }

  function renderActiveQueue(workOrders: WorkOrder[]) {
    return (
      <div className="space-y-2">
        {workOrders.map((workOrder) => {
          const isDragged = draggedWorkOrderId === workOrder.id;

          return (
            <article
              key={workOrder.id}
              draggable={!isSavingQueueOrder && isAllQueueFilter}
              onDragStart={(event) => handleQueueDragStart(event, workOrder.id)}
              onDragOver={handleQueueDragOver}
              onDrop={(event) => handleQueueDrop(event, workOrder.id)}
              onDragEnd={handleQueueDragEnd}
              className={[
                "flex cursor-grab flex-col gap-3 rounded-2xl border bg-white px-4 py-3 transition sm:flex-row sm:items-center sm:justify-between",
                workOrder.is_correction
                  ? "border-amber-300 bg-amber-50/60"
                  : isDragged
                    ? "border-accent/60 bg-mist/60 opacity-70"
                    : "border-line/80",
              ].join(" ")}
            >
              <div className="flex items-start gap-3">
                <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-mist text-sm font-semibold text-ink">
                  {workOrder.queue_position ?? "-"}
                </div>
                <div className="space-y-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="text-xs font-semibold uppercase tracking-[0.14em] text-accent">{workOrder.order_number}</p>
                    {workOrder.is_correction ? (
                      <span className="inline-flex rounded-full bg-amber-100 px-2 py-1 text-[11px] font-semibold uppercase tracking-[0.08em] text-amber-800">
                        POPRAWKA
                      </span>
                    ) : null}
                    {workOrder.planning_priority === "URGENT" ? (
                      <span className="inline-flex rounded-full bg-rose-100 px-2 py-1 text-[11px] font-semibold uppercase tracking-[0.08em] text-rose-800">
                        PILNE
                      </span>
                    ) : workOrder.planning_priority === "PINNED" ? (
                      <span className="inline-flex rounded-full bg-accent/10 px-2 py-1 text-[11px] font-semibold uppercase tracking-[0.08em] text-accent">
                        PRZYPIĘTE
                      </span>
                    ) : null}
                    <span className="inline-flex rounded-full bg-white px-2 py-1 text-[11px] font-semibold text-steel shadow-sm">
                      {isAllQueueFilter
                        ? "Przeciągnij, aby zmienić kolejność"
                        : "Przełącz na Wszystkie, aby zmieniać kolejność"}
                    </span>
                  </div>
                  <h4 className="text-base font-semibold text-ink"><WorkOrderPrimaryInfoLine workOrder={workOrder} /></h4>
                  <div className="flex flex-wrap gap-2">
                    {[...getWorkOrderBadgeStack(workOrder), ...getWorkOrderAttentionBadges(workOrder)].map((badge) => (
                      <span
                        key={`${workOrder.id}-${badge.label}`}
                        className={["inline-flex rounded-full px-2 py-1 text-[11px] font-semibold", badgeClasses(badge.tone)].join(" ")}
                      >
                        {badge.label}
                      </span>
                    ))}
                  </div>
                  <p className="text-xs font-semibold text-ink">{workOrder.process_status.label}</p>
                  <p className="text-xs text-steel">Postęp: {getWorkOrderProgressText(workOrder)}</p>
                  {getWorkOrderDiscrepancyText(workOrder) ? (
                    <p className="text-xs font-medium text-amber-700">{getWorkOrderDiscrepancyText(workOrder)}</p>
                  ) : null}
                  {workOrder.is_correction ? (
                    <div className="space-y-1 text-sm">
                      <p className="font-medium text-amber-800">
                        {workOrder.parent_order ? (
                          <a href={buildWorkOrderDetailHref(workOrder.parent_order.id, "MANAGER")} className="text-amber-800 underline-offset-2 hover:underline">
                            {buildCorrectionReference(workOrder)}
                          </a>
                        ) : (
                          buildCorrectionReference(workOrder)
                        )}
                      </p>
                      <p className="text-amber-700">{buildCorrectionQuantityContext(workOrder)}</p>
                      <p className="text-amber-700">{buildOriginalPickupContext(workOrder)}</p>
                    </div>
                  ) : null}
                  {getWorkOrderActiveCorrectionsText(workOrder) ? (
                    <p className="text-sm text-rose-700">{getWorkOrderActiveCorrectionsText(workOrder)}</p>
                  ) : null}
                  {renderPaintShortageWarning(workOrder)}
                </div>
              </div>

              <div className="flex flex-wrap items-center gap-3 text-sm text-steel">
                {canChangeProductionType(workOrder) ? (
                  <div className="inline-flex rounded-2xl border border-line bg-mist p-0.5">
                    {productionTypeOptions.map((option) => {
                      const isSelected = workOrder.production_type?.value === option.value;
                      const isChanging = changingProductionTypeId === workOrder.id;
                      return (
                        <button
                          key={option.value}
                          type="button"
                          disabled={isChanging}
                          onClick={() => {
                            if (!isSelected) {
                              void handleChangeProductionType(workOrder.id, option.value);
                            }
                          }}
                          className={[
                            "rounded-xl px-3 py-1.5 text-xs font-semibold transition",
                            isSelected
                              ? "bg-white text-ink shadow-sm"
                              : "text-steel hover:text-accent disabled:cursor-not-allowed",
                          ].join(" ")}
                        >
                          {isChanging && !isSelected ? "..." : option.label}
                        </button>
                      );
                    })}
                  </div>
                ) : (
                  <span className="inline-flex rounded-full bg-mist px-3 py-1 font-medium text-ink">
                    {getProductionTypeLabel(workOrder.production_type?.value)}
                  </span>
                )}
                {renderPlanningPriorityControls(workOrder)}
                <a
                  href={buildWorkOrderDetailHref(workOrder.id, "MANAGER")}
                  className="inline-flex rounded-full border border-line bg-white px-3 py-1 font-medium text-accent transition hover:border-accent/50"
                >
                  Szczegóły
                </a>
              </div>
            </article>
          );
        })}
      </div>
    );
  }

  function renderCompletedWorkOrdersTable(workOrders: WorkOrder[]) {
    return (
      <div className="overflow-hidden rounded-3xl border border-line bg-white shadow-panel">
        <div className="overflow-x-auto">
          <table className="min-w-full border-collapse text-left text-sm">
            <thead className="bg-mist text-steel">
              <tr>
                <th className="px-5 py-4 font-semibold">Pozycja</th>
                <th className="px-5 py-4 font-semibold">Numer</th>
                <th className="px-5 py-4 font-semibold">Dane główne</th>
                <th className="px-5 py-4 font-semibold">Typ zlecenia</th>
                <th className="px-5 py-4 font-semibold">Podsumowanie historyczne</th>
                <th className="px-5 py-4 font-semibold">Typ produkcji</th>
              </tr>
            </thead>
            <tbody>
              {workOrders.map((workOrder) => (
                <tr key={workOrder.id} className="border-t border-line/80 text-ink">
                    <td className="px-5 py-4 font-semibold">{workOrder.queue_position ?? "-"}</td>
                    <td className="px-5 py-4 font-semibold">{workOrder.order_number}</td>
                    <td className="px-5 py-4 text-steel"><WorkOrderPrimaryInfoLine workOrder={workOrder} /></td>
                    <td className="px-5 py-4">
                      {workOrder.is_correction ? (
                        <span className="inline-flex rounded-full bg-amber-100 px-3 py-1 text-xs font-semibold text-amber-800">
                          POPRAWKA
                        </span>
                      ) : (
                        <span className="inline-flex rounded-full bg-mist px-3 py-1 text-xs font-semibold text-ink">Zwykłe</span>
                      )}
                    </td>
                    <td className="px-5 py-4 text-steel">
                      {workOrder.is_correction
                        ? `${buildCorrectionReference(workOrder)} · ${buildCorrectionQuantityContext(workOrder)}`
                        : getHistoricalWorkOrderResultText(workOrder)}
                    </td>
                    <td className="px-5 py-4 text-steel">{getProductionTypeLabel(workOrder.production_type?.value)}</td>
                  </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    );
  }

  // Compact read-only board shown on the entry screen (one per production line).
  function renderReadOnlyBoard(line: ProductionTypeValue, label: string) {
    const active = lineActiveOrders(line);
    const completed = lineCompletedOrders(line);

    return (
      <div className="flex flex-col gap-4 rounded-[2rem] border border-white/70 bg-white/80 p-6 shadow-panel backdrop-blur">
        <div className="flex items-center justify-between">
          <h3 className="text-xl font-semibold text-ink">{label}</h3>
          <span className="inline-flex rounded-full bg-mist px-3 py-1 text-sm font-medium text-steel">
            {active.length} w kolejce
          </span>
        </div>

        {active.length === 0 ? (
          <div className="rounded-3xl border border-dashed border-line bg-mist px-5 py-8 text-center text-sm text-steel">
            Brak zaplanowanych zleceń na tej linii
          </div>
        ) : (
          <ol className="space-y-2">
            {active.map((workOrder) => (
              <li
                key={workOrder.id}
                className={[
                  "flex items-start gap-3 rounded-2xl border px-4 py-3",
                  workOrder.is_correction ? "border-amber-300 bg-amber-50/60" : "border-line/80 bg-white",
                ].join(" ")}
              >
                <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-mist text-sm font-semibold text-ink">
                  {workOrder.queue_position ?? "-"}
                </span>
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-xs font-semibold uppercase tracking-[0.12em] text-accent">{workOrder.order_number}</span>
                    {workOrder.is_correction ? (
                      <span className="inline-flex rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.08em] text-amber-800">
                        POPRAWKA
                      </span>
                    ) : null}
                  </div>
                  <p className="truncate text-sm font-semibold text-ink"><WorkOrderPrimaryInfoLine workOrder={workOrder} /></p>
                  <p className="text-xs text-steel">{workOrder.process_status.label}</p>
                </div>
              </li>
            ))}
          </ol>
        )}

        {completed.length > 0 ? (
          <p className="text-xs text-steel">+ {completed.length} zakończonych (poglądowo)</p>
        ) : null}
      </div>
    );
  }

  function renderQueueFilterTabs() {
    return (
      <div className="inline-flex rounded-full border border-line bg-mist p-1">
        {(
          [
            { value: "ALL", label: "Wszystkie" },
            { value: "NORMAL", label: "Zwykłe" },
            { value: "CORRECTIONS", label: "Poprawki" },
          ] as Array<{ value: QueueFilter; label: string }>
        ).map((option) => (
          <button
            key={option.value}
            type="button"
            onClick={() => setQueueFilter(option.value)}
            className={[
              "rounded-full px-4 py-2 text-sm font-medium transition",
              queueFilter === option.value ? "bg-white text-ink shadow-sm" : "text-steel hover:text-accent",
            ].join(" ")}
          >
            {option.label}
          </button>
        ))}
      </div>
    );
  }

  function renderUnplannedColumn() {
    return (
      <div className="flex flex-col rounded-3xl border border-white/70 bg-white/80 p-4 shadow-panel backdrop-blur lg:h-full lg:min-h-0">
        <div className="mb-3 space-y-2">
          <div>
            <h3 className="text-xl font-semibold text-ink">Do zaplanowania</h3>
            <p className="mt-1 text-sm text-steel">
              Kliknij „Zaplanuj", a zlecenie trafi na koniec planu {editLine === "AUTOMATIC" ? "automatu" : "ręcznej"}.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs font-semibold uppercase tracking-[0.12em] text-steel">Sortowanie:</span>
            <div className="inline-flex flex-wrap rounded-2xl border border-line bg-mist p-1 gap-1">
              {(
                [
                  { value: "NONE", label: "Domyślnie" },
                  { value: "COLOR", label: "Kolor" },
                  { value: "COMPANY", label: "Firma" },
                  { value: "DEADLINE", label: "Termin" },
                ] as Array<{ value: UnplannedSort; label: string }>
              ).map((option) => (
                <button
                  key={option.value}
                  type="button"
                  onClick={() => setUnplannedSort(option.value)}
                  className={[
                    "rounded-xl px-3 py-1.5 text-xs font-semibold transition",
                    unplannedSort === option.value ? "bg-white text-ink shadow-sm" : "text-steel hover:text-accent",
                  ].join(" ")}
                >
                  {option.label}
                </button>
              ))}
            </div>
          </div>
        </div>

        {isLoading ? (
          <div className="rounded-3xl border border-dashed border-line bg-mist px-6 py-12 text-center text-base text-steel">
            Ładowanie...
          </div>
        ) : filteredUnplannedWorkOrders.length === 0 ? (
          <div className="rounded-3xl border border-dashed border-line bg-mist px-6 py-12 text-center text-base text-steel">
            Wszystkie zlecenia są już zaplanowane
          </div>
        ) : (
          <div className="space-y-2 pr-1 lg:flex-1 lg:min-h-0 lg:overflow-y-auto">
            {filteredUnplannedWorkOrders.map((workOrder) => {
              const isSubmitting = planningWorkOrderId === workOrder.id;
              const paintWarning = renderPaintShortageWarning(workOrder);

              return (
                <article key={workOrder.id} className="rounded-2xl border border-line/80 bg-white px-4 py-3">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0 space-y-1">
                      <div className="flex flex-wrap items-center gap-1.5">
                        <span className="text-xs font-semibold uppercase tracking-[0.12em] text-accent">{workOrder.order_number}</span>
                        {[...getWorkOrderBadgeStack(workOrder), ...getWorkOrderAttentionBadges(workOrder)].map((badge) => (
                          <span
                            key={`${workOrder.id}-${badge.label}`}
                            className={["inline-flex rounded-full px-2 py-0.5 text-[10px] font-semibold", badgeClasses(badge.tone)].join(" ")}
                          >
                            {badge.label}
                          </span>
                        ))}
                      </div>
                      <p className="truncate text-sm font-semibold text-ink"><WorkOrderPrimaryInfoLine workOrder={workOrder} /></p>
                      <p className="text-xs font-semibold text-ink">{workOrder.process_status.label}</p>
                      <p className="text-xs text-steel">Postęp: {getWorkOrderProgressText(workOrder)}</p>
                      {workOrder.is_correction ? (
                        <div className="space-y-0.5 text-xs text-amber-700">
                          <p className="font-medium text-amber-800">
                            {workOrder.parent_order ? (
                              <a href={buildWorkOrderDetailHref(workOrder.parent_order.id, "MANAGER")} className="underline-offset-2 hover:underline">
                                {buildCorrectionReference(workOrder)}
                              </a>
                            ) : (
                              buildCorrectionReference(workOrder)
                            )}
                            {buildCorrectionQuantityContext(workOrder) ? ` · ${buildCorrectionQuantityContext(workOrder)}` : ""}
                          </p>
                          <p>{buildOriginalPickupContext(workOrder)}</p>
                        </div>
                      ) : null}
                      {getWorkOrderActiveCorrectionsText(workOrder) ? (
                        <p className="text-xs text-rose-700">{getWorkOrderActiveCorrectionsText(workOrder)}</p>
                      ) : null}
                    </div>

                    <div className="flex shrink-0 flex-col items-stretch gap-1.5">
                      <button
                        type="button"
                        disabled={isSubmitting}
                        onClick={() => void handlePlanWorkOrder(workOrder.id)}
                        className="inline-flex items-center justify-center rounded-full bg-accent px-4 py-1.5 text-sm font-semibold text-white transition hover:bg-brand-800 disabled:cursor-not-allowed disabled:bg-brand-100 disabled:text-brand-muted"
                      >
                        {isSubmitting ? "..." : "Zaplanuj"}
                      </button>
                      <a
                        href={buildWorkOrderDetailHref(workOrder.id, "MANAGER")}
                        className="inline-flex items-center justify-center rounded-full border border-line bg-white px-4 py-1.5 text-xs font-medium text-accent transition hover:border-accent/50"
                      >
                        Szczegóły
                      </a>
                    </div>
                  </div>
                  {paintWarning ? <div className="mt-2">{paintWarning}</div> : null}
                </article>
              );
            })}
          </div>
        )}
      </div>
    );
  }

  function renderRulesConfig() {
    return (
      <div className="mb-4 space-y-3 rounded-3xl border border-line/80 bg-mist/60 px-5 py-4">
        <div>
          <h4 className="text-base font-semibold text-ink">Reguły układania (Automat)</h4>
          <p className="mt-1 text-xs text-steel">
            Kolejność reguł = priorytet układania (od najważniejszej). Przestaw strzałkami i włącz/wyłącz.
          </p>
        </div>
        {scheduleRules === null ? (
          <p className="text-sm text-steel">Ładowanie reguł...</p>
        ) : (
          <>
            <ol className="space-y-2">
              {scheduleRules.map((rule, index) => (
                <li
                  key={rule.key}
                  className="flex items-center gap-3 rounded-2xl border border-line bg-white px-4 py-3"
                >
                  <span className="text-sm font-semibold text-steel">{index + 1}.</span>
                  <div className="min-w-0 flex-1">
                    <p className={["text-sm font-semibold", rule.enabled ? "text-ink" : "text-slate-400"].join(" ")}>
                      {rule.label}
                    </p>
                    <p className="text-xs text-steel">{rule.description}</p>
                  </div>
                  <label className="flex shrink-0 items-center gap-1.5 text-xs font-medium text-steel">
                    <input
                      type="checkbox"
                      checked={rule.enabled}
                      onChange={() => handleToggleRule(index)}
                      aria-label={`Włącz regułę: ${rule.label}`}
                    />
                    {rule.enabled ? "Aktywna" : "Wyłączona"}
                  </label>
                  <div className="flex shrink-0 flex-col gap-1">
                    <button
                      type="button"
                      disabled={index === 0}
                      onClick={() => handleMoveRule(index, -1)}
                      aria-label={`Wyżej: ${rule.label}`}
                      className="rounded-lg border border-line px-2 text-xs text-steel transition hover:border-accent hover:text-accent disabled:cursor-not-allowed disabled:text-slate-300"
                    >
                      ▲
                    </button>
                    <button
                      type="button"
                      disabled={index === scheduleRules.length - 1}
                      onClick={() => handleMoveRule(index, 1)}
                      aria-label={`Niżej: ${rule.label}`}
                      className="rounded-lg border border-line px-2 text-xs text-steel transition hover:border-accent hover:text-accent disabled:cursor-not-allowed disabled:text-slate-300"
                    >
                      ▼
                    </button>
                  </div>
                </li>
              ))}
            </ol>
            <div className="flex justify-end">
              <button
                type="button"
                disabled={isSavingRules}
                onClick={() => void handleSaveRules()}
                className="inline-flex items-center justify-center rounded-full bg-accent px-4 py-2 text-sm font-semibold text-white transition hover:bg-brand-800 disabled:cursor-not-allowed disabled:bg-brand-100 disabled:text-brand-muted"
              >
                {isSavingRules ? "Zapisywanie..." : "Zapisz reguły"}
              </button>
            </div>
          </>
        )}
      </div>
    );
  }

  function renderPlannedColumn() {
    const lineActive = filterQueueByType(lineActiveOrders(editLine), queueFilter);
    const lineCompleted = filterQueueByType(lineCompletedOrders(editLine), queueFilter);

    return (
      <div className="flex flex-col rounded-3xl border border-white/70 bg-white/80 p-4 shadow-panel backdrop-blur lg:h-full lg:min-h-0">
        <div className="mb-3 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h3 className="text-xl font-semibold text-ink">
              Plan: {editLine === "AUTOMATIC" ? "Automat" : "Ręczna"}
            </h3>
            <p className="mt-1 text-sm text-steel">Przeciągnij zlecenia, aby ustawić kolejność. Zmiany zapisują się same.</p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {editLine === "AUTOMATIC" ? (
              <>
                <button
                  type="button"
                  disabled={isAutoArranging || isSavingQueueOrder || lineActiveOrders(editLine).length < 2 || !isAllQueueFilter}
                  onClick={() => void handleAutoArrange()}
                  className="inline-flex items-center justify-center rounded-full bg-accent px-4 py-2 text-sm font-semibold text-white transition hover:bg-brand-800 disabled:cursor-not-allowed disabled:bg-brand-100 disabled:text-brand-muted"
                >
                  {isAutoArranging ? "Układanie..." : "Ułóż automatycznie"}
                </button>
                <button
                  type="button"
                  onClick={() => setShowRulesConfig((current) => !current)}
                  className="inline-flex items-center justify-center rounded-full border border-line bg-white px-4 py-2 text-sm font-medium text-steel transition hover:border-accent hover:text-accent"
                >
                  {showRulesConfig ? "Ukryj reguły" : "Reguły układania"}
                </button>
              </>
            ) : null}
            <button
              type="button"
              disabled={isSavingQueueOrder || lineActiveOrders(editLine).length < 2 || !isAllQueueFilter}
              onClick={() => void handleSaveQueueOrder()}
              className="inline-flex items-center justify-center rounded-full border border-line bg-white px-4 py-2 text-sm font-medium text-steel transition hover:border-accent hover:text-accent disabled:cursor-not-allowed disabled:border-line disabled:text-slate-400"
            >
              {isSavingQueueOrder ? "Zapisywanie..." : hasPendingQueueChanges ? "Zapisz kolejność" : "Kolejność zapisana"}
            </button>
          </div>
        </div>

        {editLine === "AUTOMATIC" &&
        isAllQueueFilter &&
        !hasPendingQueueChanges &&
        scheduleProposal &&
        scheduleProposal.colour_changeover_reduction > 0 ? (
          <div className="mb-4 flex flex-col gap-2 rounded-3xl border border-amber-200 bg-amber-50 px-5 py-3 text-sm text-amber-800 sm:flex-row sm:items-center sm:justify-between">
            <span>
              Lepsze ułożenie dostępne — o {scheduleProposal.colour_changeover_reduction}{" "}
              {scheduleProposal.colour_changeover_reduction === 1 ? "zmianę" : "zmian"} koloru mniej.
            </span>
            <button
              type="button"
              disabled={isAutoArranging}
              onClick={() => void handleAutoArrange()}
              className="inline-flex shrink-0 items-center justify-center rounded-full bg-amber-600 px-4 py-1.5 text-xs font-semibold text-white transition hover:bg-amber-700 disabled:cursor-not-allowed disabled:bg-amber-200"
            >
              Pokaż propozycję
            </button>
          </div>
        ) : null}

        {editLine === "AUTOMATIC" && showRulesConfig ? renderRulesConfig() : null}

        {!isAllQueueFilter ? (
          <div className="mb-4 rounded-3xl border border-dashed border-line bg-mist px-6 py-4 text-center text-sm text-steel">
            Zmiana kolejności działa dla pełnej kolejki. Przełącz filtr na Wszystkie, aby zmienić kolejność.
          </div>
        ) : null}

        <div className="space-y-6 pr-1 lg:flex-1 lg:min-h-0 lg:overflow-y-auto">
          {isLoading ? (
            <div className="rounded-3xl border border-dashed border-line bg-mist px-6 py-12 text-center text-base text-steel">
              Ładowanie...
            </div>
          ) : lineActive.length === 0 ? (
            <div className="rounded-3xl border border-dashed border-line bg-mist px-6 py-12 text-center text-base text-steel">
              Brak zaplanowanych zleceń na tej linii
            </div>
          ) : (
            renderActiveQueue(lineActive)
          )}

          {lineCompleted.length > 0 ? (
            <div className="space-y-4 rounded-3xl border border-line/80 bg-mist/50 p-5">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <h4 className="text-lg font-semibold text-ink">Zakończone</h4>
                  <p className="mt-1 text-sm text-steel">Ukończone zlecenia pozostają w kolejce wyłącznie poglądowo.</p>
                </div>
                <button
                  type="button"
                  onClick={() => setShowCompleted((current) => !current)}
                  className="inline-flex items-center justify-center rounded-full border border-line bg-white px-4 py-2 text-sm font-medium text-steel transition hover:border-accent hover:text-accent"
                >
                  {showCompleted ? "Ukryj zakończone" : "Pokaż zakończone"}
                </button>
              </div>

              {showCompleted ? renderCompletedWorkOrdersTable(lineCompleted) : null}
            </div>
          ) : null}
        </div>
      </div>
    );
  }

  function renderEditOverlay() {
    return (
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Układanie planu"
        className="fixed inset-0 z-40 flex flex-col bg-shell/95 backdrop-blur"
      >
        <header className="flex flex-col gap-4 border-b border-line/70 bg-white/80 px-6 py-4 backdrop-blur lg:flex-row lg:items-center lg:justify-between">
          <div className="flex flex-wrap items-center gap-4">
            <h2 className="text-2xl font-semibold text-ink">Układanie planu</h2>
            {renderQueueFilterTabs()}
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <span className="text-xs font-semibold uppercase tracking-[0.12em] text-steel">Plan:</span>
            <div className="inline-flex rounded-2xl border border-line bg-mist p-1">
              {PRODUCTION_LINES.map((line) => (
                <button
                  key={line.value}
                  type="button"
                  aria-label={`Plan ${line.label.toLowerCase()}`}
                  onClick={() => setEditLine(line.value)}
                  className={[
                    "rounded-xl px-5 py-2 text-sm font-semibold transition",
                    editLine === line.value ? "bg-white text-ink shadow-sm" : "text-steel hover:text-accent",
                  ].join(" ")}
                >
                  {line.label}
                </button>
              ))}
            </div>
            <button
              type="button"
              onClick={() => setIsEditing(false)}
              className="inline-flex items-center justify-center rounded-full bg-accent px-5 py-2 text-sm font-medium text-white transition hover:bg-brand-800"
            >
              Gotowe
            </button>
          </div>
        </header>

        {errorMessage ? (
          <div className="mx-6 mt-4 rounded-2xl border border-rose-200 bg-rose-50 px-5 py-3 text-sm text-rose-700">{errorMessage}</div>
        ) : null}
        {successMessage ? (
          <div className="mx-6 mt-4 rounded-2xl border border-emerald-200 bg-emerald-50 px-5 py-3 text-sm text-emerald-700">{successMessage}</div>
        ) : null}

        <div className="grid flex-1 min-h-0 grid-cols-1 gap-6 overflow-y-auto p-6 lg:grid-cols-2 lg:overflow-hidden">
          {renderUnplannedColumn()}
          {renderPlannedColumn()}
        </div>
      </div>
    );
  }

  return (
    <main className="flex w-full flex-col gap-5 px-1 pb-5">
      <section className="rounded-[2rem] border border-white/70 bg-white/80 p-6 shadow-panel backdrop-blur sm:p-8">
        <div className="flex flex-col gap-6">
          <div className="space-y-2 text-center">
            <p className="text-sm font-semibold uppercase tracking-[0.18em] text-accent">Panel kierownika</p>
            <h2 className="text-3xl font-semibold text-ink sm:text-4xl">Planowanie produkcji</h2>
            <p className="mx-auto max-w-2xl text-sm leading-6 text-steel sm:text-base">
              Dwa osobne plany — automat i ręczna. Kliknij „Edytuj plan", aby układać kolejność i dodawać zlecenia.
            </p>
          </div>
          <div className="flex justify-center">
            <button
              type="button"
              onClick={() => setIsEditing(true)}
              className="inline-flex items-center justify-center rounded-full bg-accent px-8 py-4 text-base font-semibold text-white shadow-panel transition hover:bg-brand-800"
            >
              Edytuj plan
            </button>
          </div>
        </div>
      </section>

      {errorMessage && !isEditing ? (
        <section className="rounded-2xl border border-rose-200 bg-rose-50 px-5 py-4 text-sm text-rose-700">{errorMessage}</section>
      ) : null}

      {successMessage && !isEditing ? (
        <section className="rounded-2xl border border-emerald-200 bg-emerald-50 px-5 py-4 text-sm text-emerald-700">
          {successMessage}
        </section>
      ) : null}

      {isLoading ? (
        <section className="rounded-[2rem] border border-dashed border-line bg-mist px-6 py-12 text-center text-base text-steel">
          Ładowanie...
        </section>
      ) : (
        <section className="grid gap-6 lg:grid-cols-2">
          {PRODUCTION_LINES.map((line) => (
            <div key={line.value}>{renderReadOnlyBoard(line.value, line.label)}</div>
          ))}
        </section>
      )}

      {!isLoading ? <CapacityBoard /> : null}

      <section className="rounded-[2rem] border border-white/70 bg-white/80 p-6 shadow-panel backdrop-blur sm:p-8">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h3 className="text-2xl font-semibold text-ink">Statystyka poprawek</h3>
          </div>
          <a
            href={correctionReasonReportExportUrl}
            className="inline-flex items-center justify-center rounded-full border border-line bg-white px-5 py-3 text-sm font-medium text-accent transition hover:border-accent/50"
          >
            Eksport CSV
          </a>
        </div>

        {isLoading ? (
          <div className="mt-5 rounded-3xl border border-dashed border-line bg-mist px-6 py-10 text-center text-base text-steel">
            Ładowanie...
          </div>
        ) : correctionReasonReport.length === 0 ? (
          <div className="mt-5 rounded-3xl border border-dashed border-line bg-mist px-6 py-10 text-center text-base text-steel">
            Brak poprawek
          </div>
        ) : (
          <div className="mt-5 overflow-hidden rounded-3xl border border-line bg-white">
            <div className="hidden grid-cols-[minmax(160px,1fr)_140px_160px] gap-4 border-b border-line bg-mist px-5 py-3 text-xs font-semibold uppercase text-steel md:grid">
              <span>Kategoria</span>
              <span>Zlecenia</span>
              <span>Ilość</span>
            </div>
            <div className="divide-y divide-line">
              {correctionReasonReport.map((item) => (
                <div
                  key={item.correction_reason_category ?? "__uncategorized__"}
                  className="grid gap-2 px-5 py-4 text-sm text-ink md:grid-cols-[minmax(160px,1fr)_140px_160px] md:gap-4"
                >
                  <span className="font-semibold">{formatCorrectionReasonCategory(item.correction_reason_category)}</span>
                  <span className="text-steel">{item.work_order_count}</span>
                  <span className="text-steel">{item.total_correction_quantity} szt.</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </section>

      {isEditing ? renderEditOverlay() : null}
    </main>
  );
}
