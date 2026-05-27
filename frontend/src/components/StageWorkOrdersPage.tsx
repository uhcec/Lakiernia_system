import { useEffect, useState } from "react";

import { getMutationErrorMessage } from "../utils/mutationError";
import { fetchStageWorkOrders, transitionStage } from "../api/processApi";
import type { ProcessStageValue, StageWorkOrder, StageStatusValue } from "../types/process";
import type { ProductionTypeValue } from "../types/workOrders";
import { loadCorrectionContexts, type CorrectionContext } from "../utils/correctionContext";
import { formatWorkOrderPrimaryInfo, getStageWorkOrderBadgeStack, getStageWorkOrderProgressText, type DisplayBadge } from "../utils/workOrderDisplay";

type QueueFilter = "ALL" | "NORMAL" | "CORRECTIONS";

interface StageWorkOrdersPageProps {
  stage: ProcessStageValue;
  title: string;
  emptyMessage: string;
  productionType?: ProductionTypeValue;
  allowManualStart?: boolean;
  readOnly?: boolean;
  readOnlyLabel?: string;
}

function getActionLabel(status: StageStatusValue): string {
  switch (status) {
    case "NOT_STARTED":
      return "Rozpocznij";
    case "IN_PROGRESS":
      return "Zakończ";
    case "DONE":
      return "Cofnij";
  }
}

function getStageAction(status: StageStatusValue): "start" | "finish" | "reopen" {
  switch (status) {
    case "NOT_STARTED":
      return "start";
    case "IN_PROGRESS":
      return "finish";
    case "DONE":
      return "reopen";
  }
}

function getBatchTypeLabel(batchType: StageWorkOrder["batch_type"]): string {
  if (batchType === "CORRECTION") {
    return "Poprawka";
  }
  if (batchType === "MAIN") {
    return "Partia";
  }
  return "-";
}

function buildCorrectionReference(workOrder: StageWorkOrder, context: CorrectionContext | undefined): string {
  if (!workOrder.is_correction) {
    return "";
  }
  if (context?.parentOrderNumber) {
    return `Poprawka do ${context.parentOrderNumber}`;
  }
  return "Poprawka do zlecenia nadrzędnego";
}

function buildCorrectionQuantityContext(workOrder: StageWorkOrder, context: CorrectionContext | undefined): string {
  if (!workOrder.is_correction) {
    return "";
  }
  if (typeof context?.parentTotalQuantity === "number") {
    return `${workOrder.total_quantity} szt. poprawki z ${context.parentTotalQuantity}`;
  }
  return `${workOrder.total_quantity} szt. poprawki`;
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

export function StageWorkOrdersPage({
  stage,
  title,
  emptyMessage,
  productionType,
  allowManualStart = true,
  readOnly = false,
  readOnlyLabel = "Podgląd",
}: StageWorkOrdersPageProps) {
  const [workOrders, setWorkOrders] = useState<StageWorkOrder[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [queueFilter, setQueueFilter] = useState<QueueFilter>("ALL");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [warningMessage, setWarningMessage] = useState<string | null>(null);
  const [activeWorkOrderId, setActiveWorkOrderId] = useState<number | null>(null);
  const [showCompleted, setShowCompleted] = useState(false);
  const [countedQuantities, setCountedQuantities] = useState<Record<number, string>>({});
  const [correctionContextByOrderId, setCorrectionContextByOrderId] = useState<Record<number, CorrectionContext>>({});

  const isSurfacePreparationStage = stage === "SURFACE_PREPARATION";

  const filteredWorkOrders = workOrders.filter((workOrder) => {
    if (queueFilter === "NORMAL") {
      return !workOrder.is_correction;
    }
    if (queueFilter === "CORRECTIONS") {
      return workOrder.is_correction;
    }
    return true;
  });
  const activeWorkOrders = filteredWorkOrders.filter((workOrder) => workOrder.stage_status.status.value !== "DONE");
  const completedWorkOrders = filteredWorkOrders.filter((workOrder) => workOrder.stage_status.status.value === "DONE");

  async function loadWorkOrders(options?: { preserveErrorMessage?: boolean }): Promise<boolean> {
    setIsLoading(true);
    if (!options?.preserveErrorMessage) {
      setErrorMessage(null);
    }
    setWarningMessage(null);

    try {
      const items = await fetchStageWorkOrders(stage, productionType);
      setWorkOrders(items);
      const correctionContexts = await loadCorrectionContexts(items);
      setCorrectionContextByOrderId(correctionContexts.contexts);

      if (correctionContexts.failedCount > 0) {
        setWarningMessage("Nie udało się pobrać pełnego kontekstu dla części poprawek. Lista pozostaje dostępna.");
      }

      if (stage === "SURFACE_PREPARATION") {
        setCountedQuantities(() => {
          const next: Record<number, string> = {};
          for (const item of items) {
            next[item.id] = item.counted_quantity?.toString() ?? "";
          }
          return next;
        });
      }
      return true;
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Nie udało się pobrać zleceń");
      return false;
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    void loadWorkOrders();
  }, [stage, productionType]);

  function parseCountedQuantity(value: string): number | null {
    if (!value.trim()) {
      return null;
    }

    const parsed = Number(value);
    if (!Number.isInteger(parsed) || parsed <= 0) {
      return null;
    }

    return parsed;
  }

  function formatDifference(value: number): string {
    if (value > 0) {
      return `+${value}`;
    }

    return value.toString();
  }

  async function handleAction(workOrder: StageWorkOrder) {
    setActiveWorkOrderId(workOrder.id);
    setErrorMessage(null);

    const countedQuantity = isSurfacePreparationStage && workOrder.stage_status.status.value === "NOT_STARTED"
      ? parseCountedQuantity(countedQuantities[workOrder.id] ?? "")
      : null;

    try {
      await transitionStage(
        workOrder.id,
        stage,
        getStageAction(workOrder.stage_status.status.value),
        workOrder.batch_id ?? undefined,
        countedQuantity !== null ? { counted_quantity: countedQuantity } : undefined,
      );
      await loadWorkOrders();
    } catch (error) {
      const message = getMutationErrorMessage(
        error,
        "Nie udało się zmienić statusu. Widok został odświeżony do aktualnego stanu backendu.",
      );
      const reloaded = await loadWorkOrders({ preserveErrorMessage: true });

      if (reloaded) {
        setErrorMessage(message);
      }
    } finally {
      setActiveWorkOrderId(null);
    }
  }

  function canTriggerAction(workOrder: StageWorkOrder): boolean {
    if (readOnly) {
      return false;
    }

    if (
      stage === "HANGING" &&
      workOrder.production_type?.value === "AUTOMATIC" &&
      workOrder.stage_status.status.value === "IN_PROGRESS"
    ) {
      return false;
    }

    if (
      stage === "PRODUCTION" &&
      productionType === "AUTOMATIC" &&
      workOrder.stage_status.status.value === "NOT_STARTED" &&
      !allowManualStart
    ) {
      return false;
    }

    return true;
  }

  function isActionEnabled(workOrder: StageWorkOrder): boolean {
    if (!canTriggerAction(workOrder)) {
      return false;
    }

    if (isSurfacePreparationStage && workOrder.stage_status.status.value === "NOT_STARTED") {
      return parseCountedQuantity(countedQuantities[workOrder.id] ?? "") !== null;
    }

    return true;
  }

  function getUnavailableLabel(workOrder: StageWorkOrder): string {
    if (readOnly) {
      return readOnlyLabel;
    }

    if (
      stage === "HANGING" &&
      workOrder.production_type?.value === "AUTOMATIC" &&
      workOrder.stage_status.status.value === "IN_PROGRESS"
    ) {
      return "Dokończ w pakowaniu";
    }

    return "Start po zawieszaniu";
  }

  function renderWorkOrdersTable(items: StageWorkOrder[]) {
    return (
      <div className="overflow-hidden rounded-3xl border border-line bg-white shadow-panel">
        <div className="overflow-x-auto">
          <table className="min-w-full border-collapse text-left text-sm">
            <thead className="bg-mist text-steel">
              <tr>
                <th className="px-5 py-4 font-semibold">Pozycja</th>
                <th className="px-5 py-4 font-semibold">Nr zlecenia</th>
                <th className="px-5 py-4 font-semibold">Dane główne</th>
                <th className="px-5 py-4 font-semibold">Partia</th>
                <th className="px-5 py-4 font-semibold">Plan</th>
                {isSurfacePreparationStage ? <th className="px-5 py-4 font-semibold">Policzono</th> : null}
                {isSurfacePreparationStage ? <th className="px-5 py-4 font-semibold">Różnica</th> : null}
                <th className="px-5 py-4 font-semibold">Technologia</th>
                <th className="px-5 py-4 font-semibold">Typ produkcji</th>
                <th className="px-5 py-4 font-semibold">Status etapu</th>
                <th className="px-5 py-4 font-semibold text-right">Akcje</th>
              </tr>
            </thead>
            <tbody>
              {items.map((workOrder) => {
                const status = workOrder.stage_status.status.value;
                const isSubmitting = activeWorkOrderId === workOrder.id;
                const showActionButton = canTriggerAction(workOrder);
                const isActionButtonEnabled = isActionEnabled(workOrder);
                const rowKey = `${workOrder.id}-${workOrder.batch_id ?? workOrder.id}-${stage}`;
                const countedDraft = countedQuantities[workOrder.id] ?? "";
                const parsedCountedQuantity = parseCountedQuantity(countedDraft);
                const difference =
                  status === "NOT_STARTED"
                    ? parsedCountedQuantity !== null
                      ? parsedCountedQuantity - workOrder.planned_quantity
                      : null
                    : workOrder.quantity_difference;
                const correctionContext = correctionContextByOrderId[workOrder.id];

                return (
                  <tr
                    key={rowKey}
                    className={[
                      "border-t border-line/80 text-ink",
                      workOrder.is_correction ? "bg-amber-50/50" : "",
                    ].join(" ")}
                  >
                    <td className="px-5 py-4 font-semibold">{workOrder.queue_position ?? "-"}</td>
                    <td className="px-5 py-4 font-semibold">
                      <div className="space-y-1">
                        <div>{workOrder.order_number}</div>
                        {workOrder.is_correction ? (
                          <span className="inline-flex rounded-full bg-amber-100 px-2 py-0.5 text-[11px] font-semibold uppercase tracking-[0.08em] text-amber-800">
                            POPRAWKA
                          </span>
                        ) : null}
                      </div>
                    </td>
                    <td className="px-5 py-4 text-steel">
                      <div className="space-y-1">
                        <p>{formatWorkOrderPrimaryInfo(workOrder)}</p>
                        <div className="flex flex-wrap gap-2">
                          {getStageWorkOrderBadgeStack(workOrder).map((badge) => (
                            <span
                              key={`${workOrder.id}-${badge.label}`}
                              className={["inline-flex rounded-full px-2 py-1 text-[11px] font-semibold", badgeClasses(badge.tone)].join(" ")}
                            >
                              {badge.label}
                            </span>
                          ))}
                        </div>
                        <p className="text-sm font-semibold text-ink">{title}</p>
                        <p className="text-sm text-steel">Postęp partii: {getStageWorkOrderProgressText(workOrder)}</p>
                        {workOrder.is_correction ? (
                          <>
                            <p className="font-medium text-amber-800">{buildCorrectionReference(workOrder, correctionContext)}</p>
                            <p className="text-amber-700">{buildCorrectionQuantityContext(workOrder, correctionContext)}</p>
                          </>
                        ) : null}
                      </div>
                    </td>
                    <td className="px-5 py-4 text-steel">
                      <div className="flex flex-wrap gap-2">
                        <span>{getBatchTypeLabel(workOrder.batch_type)}</span>
                        {workOrder.batch_is_partial ? (
                          <span className="inline-flex rounded-full bg-amber-100 px-2 py-0.5 text-[11px] font-semibold text-amber-800">
                            Niepełne
                          </span>
                        ) : null}
                      </div>
                    </td>
                    <td className="px-5 py-4 font-semibold">{workOrder.planned_quantity}</td>
                    {isSurfacePreparationStage ? (
                      <td className="px-5 py-4">
                        {status === "NOT_STARTED" ? (
                          <input
                            type="number"
                            min={1}
                            step={1}
                            value={countedDraft}
                            onChange={(event) => {
                              const { value } = event.target;
                              setCountedQuantities((current) => ({
                                ...current,
                                [workOrder.id]: value,
                              }));
                            }}
                            className="w-28 rounded-2xl border border-line bg-white px-3 py-2 text-sm font-medium text-ink shadow-sm outline-none transition focus:border-accent focus:ring-2 focus:ring-accent/20"
                            placeholder="0"
                          />
                        ) : (
                          <span className="font-semibold text-ink">{workOrder.counted_quantity ?? "-"}</span>
                        )}
                      </td>
                    ) : null}
                    {isSurfacePreparationStage ? (
                      <td className="px-5 py-4">
                        {difference === null ? (
                          <span className="text-steel">-</span>
                        ) : difference === 0 ? (
                          <span className="font-medium text-emerald-700">Brak różnicy</span>
                        ) : (
                          <span className="font-medium text-amber-700">Różnica: {formatDifference(difference)} szt.</span>
                        )}
                      </td>
                    ) : null}
                    <td className="px-5 py-4 text-steel">{workOrder.coating_type.label}</td>
                    <td className="px-5 py-4 text-steel">{workOrder.production_type?.label ?? "-"}</td>
                    <td className="px-5 py-4">
                      <span className="inline-flex rounded-full bg-mist px-3 py-1 text-xs font-semibold text-ink">
                        {workOrder.stage_status.status.label}
                      </span>
                    </td>
                    <td className="px-5 py-4 text-right">
                      {showActionButton ? (
                        <button
                          type="button"
                          disabled={isSubmitting || !isActionButtonEnabled}
                          onClick={() => void handleAction(workOrder)}
                          className="inline-flex items-center justify-center rounded-full border border-line bg-white px-4 py-2 text-sm font-medium text-steel transition hover:border-accent hover:text-accent disabled:cursor-not-allowed disabled:border-line disabled:text-slate-400"
                        >
                          {isSubmitting ? "Zapisywanie..." : getActionLabel(status)}
                        </button>
                      ) : (
                        <span className="inline-flex rounded-full bg-mist px-3 py-1 text-xs font-semibold text-steel">
                          {getUnavailableLabel(workOrder)}
                        </span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    );
  }

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-7xl flex-col gap-6 px-4 py-8 sm:px-6 lg:px-8">
      <section className="rounded-[2rem] border border-white/70 bg-white/80 p-6 shadow-panel backdrop-blur sm:p-8">
        <div className="space-y-2">
          <p className="text-sm font-semibold uppercase tracking-[0.18em] text-accent">Widok etapu</p>
          <div>
            <h2 className="text-3xl font-semibold text-ink sm:text-4xl">{title}</h2>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-steel sm:text-base">
              {readOnly
                ? "Widok podglądowy dla automatu. Malowanie uruchamia Zawieszanie, a wynik zapisuje Pakowanie."
                : "Lista zaplanowanych zleceń gotowych do rozpoczęcia, kontynuacji albo cofnięcia na wybranym etapie."}
            </p>
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
        </div>
      </section>

      {errorMessage ? (
        <section className="rounded-2xl border border-rose-200 bg-rose-50 px-5 py-4 text-sm text-rose-700">{errorMessage}</section>
      ) : null}

      {warningMessage ? (
        <section className="rounded-2xl border border-amber-200 bg-amber-50 px-5 py-4 text-sm text-amber-800">{warningMessage}</section>
      ) : null}

      <section className="rounded-[2rem] border border-white/70 bg-white/80 p-6 shadow-panel backdrop-blur sm:p-8">
        {isLoading ? (
          <div className="rounded-3xl border border-dashed border-line bg-mist px-6 py-12 text-center text-base text-steel">
            Ładowanie...
          </div>
        ) : workOrders.length === 0 ? (
          <div className="rounded-3xl border border-dashed border-line bg-mist px-6 py-12 text-center text-base text-steel">
            {emptyMessage}
          </div>
        ) : (
          <div className="space-y-6">
            <div className="space-y-4">
              <div>
                <h3 className="text-lg font-semibold text-ink">Do wykonania</h3>
                <p className="mt-1 text-sm text-steel">Zlecenia gotowe do rozpoczęcia lub aktualnie realizowane.</p>
              </div>
              {activeWorkOrders.length === 0 ? (
                <div className="rounded-3xl border border-dashed border-line bg-mist px-6 py-12 text-center text-base text-steel">
                  {emptyMessage}
                </div>
              ) : (
                renderWorkOrdersTable(activeWorkOrders)
              )}
            </div>

            {completedWorkOrders.length > 0 ? (
              <div className="space-y-4 rounded-3xl border border-line/80 bg-mist/50 p-5">
                <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                  <div>
                    <h3 className="text-lg font-semibold text-ink">Zakończone</h3>
                    <p className="mt-1 text-sm text-steel">Zlecenia ukończone na tym etapie, dostępne do cofnięcia.</p>
                  </div>
                  <button
                    type="button"
                    onClick={() => setShowCompleted((current) => !current)}
                    className="inline-flex items-center justify-center rounded-full border border-line bg-white px-4 py-2 text-sm font-medium text-steel transition hover:border-accent hover:text-accent"
                  >
                    {showCompleted ? "Ukryj zakończone" : "Pokaż zakończone"}
                  </button>
                </div>

                {showCompleted ? renderWorkOrdersTable(completedWorkOrders) : null}
              </div>
            ) : null}
          </div>
        )}
      </section>
    </main>
  );
}