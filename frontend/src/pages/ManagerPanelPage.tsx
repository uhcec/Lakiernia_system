import { DragEvent, FormEvent, useEffect, useRef, useState } from "react";

import {
  assignWorkOrderPlan,
  fetchPlannedWorkOrders,
  fetchUnplannedWorkOrders,
  reorderWorkOrderQueue,
} from "../api/managerApi";
import type { ProductionTypeValue, WorkOrder } from "../types/workOrders";
import { isApiError } from "../api/apiError";
import { getMutationErrorMessage } from "../utils/mutationError";
import {
  assignSequentialQueuePositions,
  buildQueueReorderRequest,
  getQueueRevisionFromPlannedOrders,
  moveWorkOrderWithinQueueSlots,
} from "../utils/queueReorder";
import {
  formatWorkOrderPrimaryInfo,
  getWorkOrderActiveCorrectionsText,
  getWorkOrderAttentionBadges,
  getWorkOrderBadgeStack,
  getHistoricalWorkOrderResultText,
  getWorkOrderProgressText,
  getWorkOrderStatusSummary,
  type DisplayBadge,
} from "../utils/workOrderDisplay";

interface PlanDraft {
  productionType: ProductionTypeValue;
  queuePosition: string;
}

type QueueFilter = "ALL" | "NORMAL" | "CORRECTIONS";

interface AuthoritativeQueueSnapshot {
  active: WorkOrder[];
  completed: WorkOrder[];
  queueRevision: string | null;
}

const productionTypeOptions: Array<{ value: ProductionTypeValue; label: string }> = [
  { value: "MANUAL", label: "Ręczna" },
  { value: "AUTOMATIC", label: "Automat" },
];

function getProductionTypeLabel(value: ProductionTypeValue | null | undefined): string {
  if (value === "MANUAL") {
    return "Ręczna";
  }

  if (value === "AUTOMATIC") {
    return "Automat";
  }

  return "-";
}

function createPlanDrafts(workOrders: WorkOrder[]): Record<number, PlanDraft> {
  return workOrders.reduce<Record<number, PlanDraft>>((drafts, workOrder, index) => {
    drafts[workOrder.id] = {
      productionType: "MANUAL",
      queuePosition: String(index + 1),
    };
    return drafts;
  }, {});
}

function splitPlannedWorkOrders(workOrders: WorkOrder[]) {
  return {
    active: workOrders.filter((workOrder) => workOrder.process_status.value !== "READY"),
    completed: workOrders.filter((workOrder) => workOrder.process_status.value === "READY"),
  };
}

function summarizeQueueOrders(workOrders: WorkOrder[]) {
  return workOrders.map((workOrder) => ({
    id: workOrder.id,
    order_number: workOrder.order_number,
    queue_position: workOrder.queue_position,
    is_correction: workOrder.is_correction,
    process_status: workOrder.process_status.value,
  }));
}

function logQueueDebug(label: string, payload: unknown) {
  if (!import.meta.env.DEV) {
    return;
  }

  console.groupCollapsed(`[queue-debug] ${label}`);
  console.log(payload);
  console.groupEnd();
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

export function ManagerPanelPage() {
  const [queueFilter, setQueueFilter] = useState<QueueFilter>("ALL");
  const [unplannedWorkOrders, setUnplannedWorkOrders] = useState<WorkOrder[]>([]);
  const [activePlannedWorkOrders, setActivePlannedWorkOrders] = useState<WorkOrder[]>([]);
  const [completedPlannedWorkOrders, setCompletedPlannedWorkOrders] = useState<WorkOrder[]>([]);
  const [planDrafts, setPlanDrafts] = useState<Record<number, PlanDraft>>({});
  const [isLoading, setIsLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [planningWorkOrderId, setPlanningWorkOrderId] = useState<number | null>(null);
  const [isSavingQueueOrder, setIsSavingQueueOrder] = useState(false);
  const [hasPendingQueueChanges, setHasPendingQueueChanges] = useState(false);
  const [draggedWorkOrderId, setDraggedWorkOrderId] = useState<number | null>(null);
  const [showCompleted, setShowCompleted] = useState(false);
  const [queueRevision, setQueueRevision] = useState<string | null>(null);
  const authoritativeQueueRef = useRef<AuthoritativeQueueSnapshot | null>(null);

  const filteredUnplannedWorkOrders = filterQueueByType(unplannedWorkOrders, queueFilter);
  const filteredActivePlannedWorkOrders = filterQueueByType(activePlannedWorkOrders, queueFilter);
  const filteredCompletedPlannedWorkOrders = filterQueueByType(completedPlannedWorkOrders, queueFilter);
  const isAllQueueFilter = queueFilter === "ALL";

  function restoreAuthoritativeQueueSnapshot() {
    const authoritativeQueue = authoritativeQueueRef.current;

    if (!authoritativeQueue) {
      return;
    }

    setActivePlannedWorkOrders(authoritativeQueue.active);
    setCompletedPlannedWorkOrders(authoritativeQueue.completed);
    setQueueRevision(authoritativeQueue.queueRevision);
  }

  async function loadManagerData(options?: { preserveErrorMessage?: boolean }): Promise<boolean> {
    setIsLoading(true);
    if (!options?.preserveErrorMessage) {
      setErrorMessage(null);
    }

    try {
      const [unplanned, planned] = await Promise.all([fetchUnplannedWorkOrders(), fetchPlannedWorkOrders()]);
      const splitPlanned = splitPlannedWorkOrders(planned);
      const normalizedActivePlanned = assignSequentialQueuePositions(splitPlanned.active);
      const normalizedCompletedPlanned = assignSequentialQueuePositions(
        splitPlanned.completed,
        normalizedActivePlanned.length + 1,
      );
      const nextQueueRevision = getQueueRevisionFromPlannedOrders(planned);

      logQueueDebug("planned orders loaded from API", summarizeQueueOrders(planned));
      logQueueDebug("normalized active queue", summarizeQueueOrders(normalizedActivePlanned));
      logQueueDebug("normalized completed queue", summarizeQueueOrders(normalizedCompletedPlanned));

      setUnplannedWorkOrders(unplanned);
      setActivePlannedWorkOrders(normalizedActivePlanned);
      setCompletedPlannedWorkOrders(normalizedCompletedPlanned);
      setQueueRevision(nextQueueRevision);
      setPlanDrafts(createPlanDrafts(unplanned));
      setHasPendingQueueChanges(false);
      authoritativeQueueRef.current = {
        active: normalizedActivePlanned,
        completed: normalizedCompletedPlanned,
        queueRevision: nextQueueRevision,
      };
      return true;
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Nie udało się pobrać panelu kierownika");
      return false;
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    void loadManagerData();
  }, []);

  useEffect(() => {
    logQueueDebug("visible filtered list", {
      filter: queueFilter,
      active: summarizeQueueOrders(filteredActivePlannedWorkOrders),
      completed: summarizeQueueOrders(filteredCompletedPlannedWorkOrders),
    });
  }, [queueFilter, filteredActivePlannedWorkOrders, filteredCompletedPlannedWorkOrders]);

  function updatePlanDraft(workOrderId: number, patch: Partial<PlanDraft>) {
    setPlanDrafts((current) => ({
      ...current,
      [workOrderId]: {
        productionType: current[workOrderId]?.productionType ?? "MANUAL",
        queuePosition: current[workOrderId]?.queuePosition ?? "1",
        ...patch,
      },
    }));
  }

  async function handlePlanSubmit(event: FormEvent<HTMLFormElement>, workOrderId: number) {
    event.preventDefault();

    const draft = planDrafts[workOrderId];
    const parsedQueuePosition = Number(draft?.queuePosition);

    if (!draft || !Number.isInteger(parsedQueuePosition) || parsedQueuePosition < 1) {
      setSuccessMessage(null);
      setErrorMessage("Pozycja w kolejce musi być liczbą większą lub równą 1");
      return;
    }

    setPlanningWorkOrderId(workOrderId);
    setErrorMessage(null);
    setSuccessMessage(null);

    try {
      await assignWorkOrderPlan(workOrderId, {
        production_type: draft.productionType,
        queue_position: parsedQueuePosition,
      });
      await loadManagerData();
      setSuccessMessage("Zlecenie zostało zaplanowane");
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

  async function saveQueueOrder(workOrders: WorkOrder[]) {
    if (!queueRevision) {
      setHasPendingQueueChanges(true);
      setErrorMessage("Nie udało się odczytać wersji kolejki. Odśwież panel kierownika i spróbuj ponownie.");
      return;
    }

    const payload = buildQueueReorderRequest(workOrders, queueRevision);

    logQueueDebug("payload sent to /manager/queue/reorder", payload);

    setIsSavingQueueOrder(true);
    setErrorMessage(null);
    setSuccessMessage(null);

    try {
      const response = await reorderWorkOrderQueue(payload);
      logQueueDebug("backend response from /manager/queue/reorder", summarizeQueueOrders(response));
      await loadManagerData();
      setSuccessMessage("Kolejność została zaktualizowana");
    } catch (error) {
      logQueueDebug("backend error from /manager/queue/reorder", error instanceof Error ? error.message : error);

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
    if (activePlannedWorkOrders.length === 0) {
      return;
    }

    await saveQueueOrder(activePlannedWorkOrders);
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

    const reorderedWorkOrders = moveWorkOrderWithinQueueSlots(
      activePlannedWorkOrders,
      resolvedDraggedWorkOrderId,
      targetWorkOrderId,
    );
    logQueueDebug("drag result order", summarizeQueueOrders(reorderedWorkOrders));
    setDraggedWorkOrderId(null);

    if (reorderedWorkOrders === activePlannedWorkOrders) {
      return;
    }

    setActivePlannedWorkOrders(reorderedWorkOrders);
    setHasPendingQueueChanges(true);
    void saveQueueOrder(reorderedWorkOrders);
  }

  function renderActiveQueue(workOrders: WorkOrder[]) {
    return (
      <div className="space-y-3">
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
                "flex cursor-grab flex-col gap-4 rounded-3xl border bg-white p-5 transition sm:flex-row sm:items-center sm:justify-between",
                workOrder.is_correction
                  ? "border-amber-300 bg-amber-50/60"
                  : isDragged
                    ? "border-accent/60 bg-mist/60 opacity-70"
                    : "border-line/80",
              ].join(" ")}
            >
              <div className="flex items-start gap-4">
                <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-mist text-sm font-semibold text-ink">
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
                    <span className="inline-flex rounded-full bg-white px-2 py-1 text-[11px] font-semibold text-steel shadow-sm">
                      {isAllQueueFilter
                        ? "Przeciągnij, aby zmienić kolejność"
                        : "Przełącz na Wszystkie, aby zmieniać kolejność"}
                    </span>
                  </div>
                  <h4 className="text-lg font-semibold text-ink">{formatWorkOrderPrimaryInfo(workOrder)}</h4>
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
                  <p className="text-sm font-semibold text-ink">{getWorkOrderStatusSummary(workOrder)}</p>
                  <p className="text-sm text-steel">Postęp: {getWorkOrderProgressText(workOrder)}</p>
                  {workOrder.is_correction ? (
                    <div className="space-y-1 text-sm">
                      <p className="font-medium text-amber-800">{buildCorrectionReference(workOrder)}</p>
                      <p className="text-amber-700">{buildCorrectionQuantityContext(workOrder)}</p>
                    </div>
                  ) : null}
                  {getWorkOrderActiveCorrectionsText(workOrder) ? (
                    <p className="text-sm text-rose-700">{getWorkOrderActiveCorrectionsText(workOrder)}</p>
                  ) : null}
                </div>
              </div>

              <div className="flex flex-wrap items-center gap-3 text-sm text-steel">
                <span className="inline-flex rounded-full bg-mist px-3 py-1 font-medium text-ink">
                  {getProductionTypeLabel(workOrder.production_type?.value)}
                </span>
                {workOrder.is_correction ? (
                  <span className="inline-flex rounded-full bg-amber-100 px-3 py-1 text-xs font-semibold text-amber-800">
                    POPRAWKA
                  </span>
                ) : null}
                <span className="font-mono text-base text-accent">::</span>
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
                    <td className="px-5 py-4 text-steel">{formatWorkOrderPrimaryInfo(workOrder)}</td>
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

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-7xl flex-col gap-6 px-4 py-8 sm:px-6 lg:px-8">
      <section className="rounded-[2rem] border border-white/70 bg-white/80 p-6 shadow-panel backdrop-blur sm:p-8">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div className="space-y-2">
            <p className="text-sm font-semibold uppercase tracking-[0.18em] text-accent">Panel kierownika</p>
            <div>
              <h2 className="text-3xl font-semibold text-ink sm:text-4xl">Planowanie produkcji</h2>
              <p className="mt-2 max-w-3xl text-sm leading-6 text-steel sm:text-base">
                Najpierw zaplanuj zlecenie, przypisując typ produkcji i pozycję w kolejce. Dopiero po tym trafi ono do
                widoków etapów produkcyjnych.
              </p>
            </div>
            <div className="mt-3 inline-flex rounded-full border border-line bg-mist p-1">
              <button
                type="button"
                onClick={() => setQueueFilter("ALL")}
                className={[
                  "rounded-full px-4 py-2 text-sm font-medium transition",
                  queueFilter === "ALL" ? "bg-white text-ink shadow-sm" : "text-steel hover:text-accent",
                ].join(" ")}
              >
                Wszystkie
              </button>
              <button
                type="button"
                onClick={() => setQueueFilter("NORMAL")}
                className={[
                  "rounded-full px-4 py-2 text-sm font-medium transition",
                  queueFilter === "NORMAL" ? "bg-white text-ink shadow-sm" : "text-steel hover:text-accent",
                ].join(" ")}
              >
                Zwykłe
              </button>
              <button
                type="button"
                onClick={() => setQueueFilter("CORRECTIONS")}
                className={[
                  "rounded-full px-4 py-2 text-sm font-medium transition",
                  queueFilter === "CORRECTIONS" ? "bg-white text-ink shadow-sm" : "text-steel hover:text-accent",
                ].join(" ")}
              >
                Poprawki
              </button>
            </div>
          </div>
          <div className="rounded-2xl border border-line bg-mist px-4 py-3 text-sm text-steel">
            Do zaplanowania: <span className="font-semibold text-ink">{filteredUnplannedWorkOrders.length}</span>
            <span className="mx-2 text-line">|</span>
            Zaplanowane: <span className="font-semibold text-ink">{filteredActivePlannedWorkOrders.length + filteredCompletedPlannedWorkOrders.length}</span>
          </div>
        </div>
      </section>

      {errorMessage ? (
        <section className="rounded-2xl border border-rose-200 bg-rose-50 px-5 py-4 text-sm text-rose-700">{errorMessage}</section>
      ) : null}

      {successMessage ? (
        <section className="rounded-2xl border border-emerald-200 bg-emerald-50 px-5 py-4 text-sm text-emerald-700">
          {successMessage}
        </section>
      ) : null}

      <section className="grid gap-6 xl:grid-cols-[1.1fr_1.4fr]">
        <div className="rounded-[2rem] border border-white/70 bg-white/80 p-6 shadow-panel backdrop-blur sm:p-8">
          <div className="mb-5 flex items-start justify-between gap-4">
            <div>
              <h3 className="text-2xl font-semibold text-ink">Do zaplanowania</h3>
              <p className="mt-1 text-sm text-steel">Wybierz typ produkcji i nadaj miejsce w kolejce.</p>
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
            <div className="space-y-4">
              {filteredUnplannedWorkOrders.map((workOrder) => {
                const draft = planDrafts[workOrder.id] ?? { productionType: "MANUAL" as const, queuePosition: "1" };
                const isSubmitting = planningWorkOrderId === workOrder.id;

                return (
                  <form
                    key={workOrder.id}
                    onSubmit={(event) => void handlePlanSubmit(event, workOrder.id)}
                    className="rounded-3xl border border-line/80 bg-white p-5"
                  >
                    <div className="flex flex-col gap-4">
                      <div>
                        <p className="text-xs font-semibold uppercase tracking-[0.14em] text-accent">{workOrder.order_number}</p>
                        <h4 className="mt-2 text-lg font-semibold text-ink">{formatWorkOrderPrimaryInfo(workOrder)}</h4>
                        <div className="mt-2 flex flex-wrap gap-2">
                          {[...getWorkOrderBadgeStack(workOrder), ...getWorkOrderAttentionBadges(workOrder)].map((badge) => (
                            <span
                              key={`${workOrder.id}-${badge.label}`}
                              className={["inline-flex rounded-full px-2 py-1 text-[11px] font-semibold", badgeClasses(badge.tone)].join(" ")}
                            >
                              {badge.label}
                            </span>
                          ))}
                        </div>
                        <p className="mt-2 text-sm font-semibold text-ink">{getWorkOrderStatusSummary(workOrder)}</p>
                        <p className="text-sm text-steel">Postęp: {getWorkOrderProgressText(workOrder)}</p>
                        {workOrder.is_correction ? (
                          <div className="mt-2 space-y-1 text-sm">
                            <span className="inline-flex rounded-full bg-amber-100 px-2 py-1 text-[11px] font-semibold uppercase tracking-[0.08em] text-amber-800">
                              POPRAWKA
                            </span>
                            <p className="font-medium text-amber-800">{buildCorrectionReference(workOrder)}</p>
                            <p className="text-amber-700">{buildCorrectionQuantityContext(workOrder)}</p>
                          </div>
                        ) : null}
                        {getWorkOrderActiveCorrectionsText(workOrder) ? (
                          <p className="mt-2 text-sm text-rose-700">{getWorkOrderActiveCorrectionsText(workOrder)}</p>
                        ) : null}
                      </div>

                      <div className="grid gap-4 md:grid-cols-[1fr_160px]">
                        <label className="flex flex-col gap-2">
                          <span className="text-sm font-medium text-ink">Typ produkcji</span>
                          <select
                            value={draft.productionType}
                            onChange={(event) => updatePlanDraft(workOrder.id, { productionType: event.target.value as ProductionTypeValue })}
                            className="rounded-2xl border border-line bg-white px-4 py-3 text-sm text-ink outline-none transition focus:border-accent"
                          >
                            {productionTypeOptions.map((option) => (
                              <option key={option.value} value={option.value}>
                                {option.label}
                              </option>
                            ))}
                          </select>
                        </label>

                        <label className="flex flex-col gap-2">
                          <span className="text-sm font-medium text-ink">Pozycja</span>
                          <input
                            type="number"
                            min={1}
                            value={draft.queuePosition}
                            onChange={(event) => updatePlanDraft(workOrder.id, { queuePosition: event.target.value })}
                            className="rounded-2xl border border-line bg-white px-4 py-3 text-sm text-ink outline-none transition focus:border-accent"
                          />
                        </label>
                      </div>

                      <div className="flex justify-end">
                        <button
                          type="submit"
                          disabled={isSubmitting}
                          className="inline-flex items-center justify-center rounded-full bg-accent px-5 py-3 text-sm font-medium text-white transition hover:bg-teal-700 disabled:cursor-not-allowed disabled:bg-teal-300"
                        >
                          {isSubmitting ? "Zapisywanie..." : "Zaplanuj"}
                        </button>
                      </div>
                    </div>
                  </form>
                );
              })}
            </div>
          )}
        </div>

        <div className="rounded-[2rem] border border-white/70 bg-white/80 p-6 shadow-panel backdrop-blur sm:p-8">
          <div className="mb-5">
            <h3 className="text-2xl font-semibold text-ink">Zaplanowane</h3>
            <p className="mt-1 text-sm text-steel">Lista jest sortowana według pozycji w kolejce.</p>
          </div>

          {isLoading ? (
            <div className="rounded-3xl border border-dashed border-line bg-mist px-6 py-12 text-center text-base text-steel">
              Ładowanie...
            </div>
          ) : filteredActivePlannedWorkOrders.length + filteredCompletedPlannedWorkOrders.length === 0 ? (
            <div className="rounded-3xl border border-dashed border-line bg-mist px-6 py-12 text-center text-base text-steel">
              Brak zaplanowanych zleceń
            </div>
          ) : (
            <div className="space-y-6">
              <div className="space-y-4">
                <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                  <div>
                    <h4 className="text-lg font-semibold text-ink">Aktywne</h4>
                    <p className="mt-1 text-sm text-steel">Przeciągnij zlecenia, aby ustawić kolejkę produkcji. Zmiany zapisują się po upuszczeniu.</p>
                  </div>
                  <button
                    type="button"
                    disabled={isSavingQueueOrder || activePlannedWorkOrders.length < 2 || !isAllQueueFilter}
                    onClick={() => void handleSaveQueueOrder()}
                    className="inline-flex items-center justify-center rounded-full border border-line bg-white px-4 py-2 text-sm font-medium text-steel transition hover:border-accent hover:text-accent disabled:cursor-not-allowed disabled:border-line disabled:text-slate-400"
                  >
                    {isSavingQueueOrder ? "Zapisywanie..." : hasPendingQueueChanges ? "Zapisz kolejność" : "Kolejność zapisana"}
                  </button>
                </div>
                {!isAllQueueFilter ? (
                  <div className="rounded-3xl border border-dashed border-line bg-mist px-6 py-6 text-center text-sm text-steel">
                    Zmiana kolejności działa dla pełnej kolejki. Przełącz filtr na Wszystkie, aby zmienić kolejność.
                  </div>
                ) : null}
                {filteredActivePlannedWorkOrders.length === 0 ? (
                  <div className="rounded-3xl border border-dashed border-line bg-mist px-6 py-12 text-center text-base text-steel">
                    Brak aktywnych zaplanowanych zleceń
                  </div>
                ) : (
                  renderActiveQueue(filteredActivePlannedWorkOrders)
                )}
              </div>

              {filteredCompletedPlannedWorkOrders.length > 0 ? (
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

                  {showCompleted ? renderCompletedWorkOrdersTable(filteredCompletedPlannedWorkOrders) : null}
                </div>
              ) : null}
            </div>
          )}
        </div>
      </section>
    </main>
  );
}