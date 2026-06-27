import { useEffect, useState } from "react";

import { usePolling, STATION_POLL_INTERVAL_MS } from "../hooks/usePolling";
import { getMutationErrorMessage } from "../utils/mutationError";
import { buildWorkOrderDetailHref, getStationIdForLocation } from "../api/stationContext";
import { NumberInput } from "./NumberInput";
import { StationPresenceWidget } from "./StationPresenceWidget";
import { TechnicalDrawingLinks } from "./TechnicalDrawingLinks";
import { fetchStageWorkOrders, recordAutomaticPaintConsumption, transitionStage } from "../api/processApi";
import type { ProcessStageValue, StageWorkOrder, StageStatusValue } from "../types/process";
import type { ProductionTypeValue } from "../types/workOrders";
import { loadCorrectionContexts, type CorrectionContext } from "../utils/correctionContext";
import {
  badgeClasses,
  buildCorrectionQuantityContext,
  buildCorrectionReference,
  buildMergedCorrectionDeltaText,
  formatDisplayOrderNumber,
  formatWorkOrderPrimaryInfo,
  getHistoricalStageWorkOrderResultText,
  getStageWorkOrderBadgeStack,
  getStageWorkOrderProgressText,
} from "../utils/workOrderDisplay";

type QueueFilter = "ALL" | "NORMAL" | "CORRECTIONS";
type PaintCartonWeightKg = 20 | 25;

interface AutomaticPaintConsumptionDraft {
  cartonWeightKg: PaintCartonWeightKg | null;
  cartonCount: number;
  finalCartonRemainingKg: string;
}

interface AutomaticPaintConsumptionPreview {
  drawnPaintQuantityKg: number | null;
  finalCartonRemainingKg: number | null;
  consumedPaintQuantityKg: number | null;
  errorMessage: string | null;
}

const EMPTY_AUTOMATIC_PAINT_DRAFT: AutomaticPaintConsumptionDraft = {
  cartonWeightKg: null,
  cartonCount: 0,
  finalCartonRemainingKg: "",
};

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

export function StageWorkOrdersPage({
  stage,
  title,
  emptyMessage,
  productionType,
  allowManualStart = true,
  readOnly = false,
  readOnlyLabel = "Podgląd",
}: StageWorkOrdersPageProps) {
  const detailStationId = getStationIdForLocation(window.location.pathname, window.location.search);
  const [workOrders, setWorkOrders] = useState<StageWorkOrder[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [queueFilter, setQueueFilter] = useState<QueueFilter>("ALL");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [warningMessage, setWarningMessage] = useState<string | null>(null);
  const [activeWorkOrderId, setActiveWorkOrderId] = useState<number | null>(null);
  const [showCompleted, setShowCompleted] = useState(false);
  const [countedQuantities, setCountedQuantities] = useState<Record<number, string>>({});
  const [paintConsumptionDrafts, setPaintConsumptionDrafts] = useState<Record<number, AutomaticPaintConsumptionDraft>>({});
  const [correctionContextByOrderId, setCorrectionContextByOrderId] = useState<Record<number, CorrectionContext>>({});

  const isSurfacePreparationStage = stage === "SURFACE_PREPARATION";
  const isAutomaticProductionView = stage === "PRODUCTION" && productionType === "AUTOMATIC";

  const filteredWorkOrders = workOrders.filter((workOrder) => {
    if (queueFilter === "NORMAL") {
      return !workOrder.is_correction && !workOrder.is_correction_round;
    }
    if (queueFilter === "CORRECTIONS") {
      return workOrder.is_correction || workOrder.is_correction_round;
    }
    return true;
  });
  const activeWorkOrders = filteredWorkOrders.filter((workOrder) => workOrder.stage_status.status.value !== "DONE");
  const completedWorkOrders = filteredWorkOrders.filter((workOrder) => workOrder.stage_status.status.value === "DONE");

  async function loadWorkOrders(options?: { preserveErrorMessage?: boolean; background?: boolean }): Promise<boolean> {
    const background = options?.background ?? false;
    if (!background) {
      setIsLoading(true);
      if (!options?.preserveErrorMessage) {
        setErrorMessage(null);
      }
      setWarningMessage(null);
    }

    try {
      const items = await fetchStageWorkOrders(stage, productionType);
      setWorkOrders(items);
      const correctionContexts = await loadCorrectionContexts(items);
      setCorrectionContextByOrderId(correctionContexts.contexts);

      if (correctionContexts.failedCount > 0 && !background) {
        setWarningMessage("Nie udało się pobrać pełnego kontekstu dla części poprawek. Lista pozostaje dostępna.");
      }

      if (stage === "SURFACE_PREPARATION") {
        // In background mode preserve what the operator is typing; only seed orders
        // that just appeared so a poll never wipes an in-progress count.
        setCountedQuantities((prev) => {
          const next: Record<number, string> = background ? { ...prev } : {};
          for (const item of items) {
            if (!background || !(item.id in next)) {
              next[item.id] = item.counted_quantity?.toString() ?? "";
            }
          }
          return next;
        });
      }
      if (isAutomaticProductionView) {
        setPaintConsumptionDrafts((prev) => {
          const next: Record<number, AutomaticPaintConsumptionDraft> = background ? { ...prev } : {};
          for (const item of items) {
            if (!background || !(item.id in next)) {
              next[item.id] = { ...EMPTY_AUTOMATIC_PAINT_DRAFT };
            }
          }
          return next;
        });
      }
      return true;
    } catch (error) {
      if (!background) {
        setErrorMessage(error instanceof Error ? error.message : "Nie udało się pobrać zleceń");
      }
      return false;
    } finally {
      if (!background) {
        setIsLoading(false);
      }
    }
  }

  useEffect(() => {
    void loadWorkOrders();
  }, [stage, productionType]);

  // Auto-refresh so changes made on other devices appear without a manual reload.
  // Paused while an action is in flight to avoid clobbering optimistic state.
  usePolling(
    () => {
      void loadWorkOrders({ background: true });
    },
    STATION_POLL_INTERVAL_MS,
    activeWorkOrderId === null,
  );

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

  function parsePositiveDecimal(value: string): number | null {
    if (!value.trim()) {
      return null;
    }

    const parsed = Number(value);
    if (!Number.isFinite(parsed) || parsed <= 0) {
      return null;
    }

    return parsed;
  }

  function parseNonNegativeDecimal(value: string): number | null {
    if (!value.trim()) {
      return 0;
    }

    const parsed = Number(value);
    if (!Number.isFinite(parsed) || parsed < 0) {
      return null;
    }

    return parsed;
  }

  function formatArea(value: number | null): string {
    return typeof value === "number" ? `${value} m2` : "-";
  }

  function formatPaint(workOrder: StageWorkOrder): string {
    return `${workOrder.paint_producer} / ${workOrder.ral_code}`;
  }

  function formatPaintKg(value: number | null): string {
    return typeof value === "number" ? `${value} kg` : "-";
  }

  function buildAutomaticPaintConsumptionPreview(
    workOrder: StageWorkOrder,
    draft: AutomaticPaintConsumptionDraft,
  ): AutomaticPaintConsumptionPreview {
    if (draft.cartonWeightKg === null || draft.cartonCount < 1) {
      return {
        drawnPaintQuantityKg: null,
        finalCartonRemainingKg: null,
        consumedPaintQuantityKg: null,
        errorMessage: null,
      };
    }

    const finalCartonRemainingKg = parseNonNegativeDecimal(draft.finalCartonRemainingKg);
    if (finalCartonRemainingKg === null) {
      return {
        drawnPaintQuantityKg: draft.cartonWeightKg * draft.cartonCount,
        finalCartonRemainingKg: null,
        consumedPaintQuantityKg: null,
        errorMessage: "Pozostałość w ostatnim kartonie musi być liczbą nieujemną.",
      };
    }

    if (finalCartonRemainingKg > draft.cartonWeightKg) {
      return {
        drawnPaintQuantityKg: draft.cartonWeightKg * draft.cartonCount,
        finalCartonRemainingKg,
        consumedPaintQuantityKg: null,
        errorMessage: "Pozostałość w ostatnim kartonie nie może przekraczać wagi kartonu.",
      };
    }

    const drawnPaintQuantityKg = draft.cartonWeightKg * draft.cartonCount;
    const consumedPaintQuantityKg = drawnPaintQuantityKg - finalCartonRemainingKg;
    if (consumedPaintQuantityKg <= 0) {
      return {
        drawnPaintQuantityKg,
        finalCartonRemainingKg,
        consumedPaintQuantityKg: null,
        errorMessage: "Zużycie farby musi być dodatnią liczbą.",
      };
    }

    return {
      drawnPaintQuantityKg,
      finalCartonRemainingKg,
      consumedPaintQuantityKg,
      errorMessage: null,
    };
  }

  function formatCountRequirement(quantity: number | null, shouldCount: boolean): string {
    if (typeof quantity === "number") {
      return `${quantity} szt.`;
    }
    return shouldCount ? "Do policzenia" : "-";
  }

  function usesVerificationColumns(): boolean {
    return stage === "SURFACE_PREPARATION" || stage === "DECORAL_PRODUCTION";
  }

  async function handleAction(workOrder: StageWorkOrder) {
    setActiveWorkOrderId(workOrder.id);
    setErrorMessage(null);

    const countedQuantity = isSurfacePreparationStage && workOrder.stage_status.status.value === "IN_PROGRESS"
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

  async function handleAutomaticPaintConsumption(workOrder: StageWorkOrder) {
    const draft = paintConsumptionDrafts[workOrder.id] ?? EMPTY_AUTOMATIC_PAINT_DRAFT;
    const preview = buildAutomaticPaintConsumptionPreview(workOrder, draft);
    if (preview.errorMessage) {
      setErrorMessage(preview.errorMessage);
      return;
    }

    if (preview.consumedPaintQuantityKg === null) {
      setErrorMessage("Wybierz wagę kartonu i dodaj pobrane kartony.");
      return;
    }

    setActiveWorkOrderId(workOrder.id);
    setErrorMessage(null);

    try {
      await recordAutomaticPaintConsumption(workOrder.id, { consumed_paint_quantity_kg: preview.consumedPaintQuantityKg });
      await loadWorkOrders();
    } catch (error) {
      const message = getMutationErrorMessage(
        error,
        "Nie udało się zapisać zużycia farby. Widok został odświeżony do aktualnego stanu backendu.",
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

    if (isSurfacePreparationStage && workOrder.stage_status.status.value === "IN_PROGRESS") {
      return parseCountedQuantity(countedQuantities[workOrder.id] ?? "") !== null;
    }

    return true;
  }

  function getUnavailableLabel(workOrder: StageWorkOrder): string {
    if (readOnly) {
      return readOnlyLabel;
    }

    return "Start po zawieszaniu";
  }

  function renderWorkOrderCards(items: StageWorkOrder[]) {
    const showVerificationFields = usesVerificationColumns();

    return (
      <div className="space-y-3">
        {items.map((workOrder) => {
          const status = workOrder.stage_status.status.value;
          const isSubmitting = activeWorkOrderId === workOrder.id;
          const showActionButton = canTriggerAction(workOrder);
          const isActionButtonEnabled = isActionEnabled(workOrder);
          const showAutomaticPaintConsumption =
            isAutomaticProductionView &&
            ((workOrder.stage_status.stage === "HANGING" && status === "IN_PROGRESS")
              || (workOrder.stage_status.stage === "PRODUCTION" && status !== "DONE"));
          const automaticPaintDraft = paintConsumptionDrafts[workOrder.id] ?? EMPTY_AUTOMATIC_PAINT_DRAFT;
          const automaticPaintPreview = buildAutomaticPaintConsumptionPreview(workOrder, automaticPaintDraft);
          const hasAutomaticPaintConfiguration = workOrder.paint_code !== null;
          const rowKey = `${workOrder.id}-${workOrder.batch_id ?? workOrder.id}-${stage}`;
          const countedDraft = countedQuantities[workOrder.id] ?? "";
          const correctionContext = correctionContextByOrderId[workOrder.id];
          const isMergedHistoricalCorrection = workOrder.is_historical_correction;
          // A correction child OR a same-order correction round both read as "a correction" for the card's
          // amber styling + "runda/poprawka" label, matching the packing & Decoral pages (FRONTEND_TRIAGE C3).
          const isCorrection = workOrder.is_correction || workOrder.is_correction_round;
          const showHistoricalResult = status === "DONE" && !workOrder.is_correction;
          const showBatchProgress = status !== "DONE" || (workOrder.is_correction && !isMergedHistoricalCorrection);

          return (
            <article
              key={rowKey}
              className={[
                "rounded-lg border bg-white p-5 text-ink shadow-sm",
                isCorrection ? "border-amber-200 bg-amber-50/40" : "border-line/80",
              ].join(" ")}
            >
              <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(14rem,18rem)]">
                <div className="space-y-4">
                  <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                    <div className="min-w-0 space-y-2">
                      <div className="flex flex-wrap items-center gap-2">
                        {workOrder.shared_stage_line_label ? (
                          <>
                            <span className="inline-flex rounded-full bg-mist px-3 py-1 text-xs font-semibold text-steel">
                              {workOrder.shared_stage_line_label}
                            </span>
                            {workOrder.is_next_at_shared_stage ? (
                              <span className="inline-flex rounded-full bg-emerald-100 px-3 py-1 text-xs font-semibold text-emerald-700">
                                NASTĘPNE
                              </span>
                            ) : null}
                          </>
                        ) : (
                          <span className="inline-flex rounded-full bg-mist px-3 py-1 text-xs font-semibold text-steel">
                            Poz. {workOrder.queue_position ?? "-"}
                          </span>
                        )}
                        <span className={`text-lg font-semibold ${workOrder.completed_quantity > 0 && workOrder.completed_quantity < workOrder.total_quantity ? "text-amber-700" : "text-ink"}`}>
                          {formatDisplayOrderNumber(workOrder)}
                        </span>
                        {workOrder.completed_quantity > 0 && workOrder.completed_quantity < workOrder.total_quantity && (
                          <span className="inline-flex rounded-full bg-amber-100 px-2 py-1 text-xs font-semibold text-amber-700">
                            {workOrder.completed_quantity}/{workOrder.total_quantity} szt.
                          </span>
                        )}
                        <span className="inline-flex rounded-full bg-mist px-3 py-1 text-xs font-semibold text-ink">
                          {workOrder.stage_status.status.label}
                        </span>
                      </div>
                      <p className="text-sm text-steel">{formatWorkOrderPrimaryInfo(workOrder)}</p>
                    </div>
                    <a
                      href={buildWorkOrderDetailHref(workOrder.id, detailStationId)}
                      className="inline-flex shrink-0 text-sm font-medium text-accent transition hover:text-teal-700"
                    >
                      Szczegóły / załączniki
                    </a>
                  </div>

                  <div className="flex flex-wrap gap-2">
                    {workOrder.batch_is_partial ? (
                      <span className="inline-flex rounded-full bg-amber-100 px-2 py-1 text-[11px] font-semibold text-amber-800">
                        Niepełne
                      </span>
                    ) : null}
                    {getStageWorkOrderBadgeStack(workOrder).map((badge) => (
                      <span
                        key={`${workOrder.id}-${badge.label}`}
                        className={["inline-flex rounded-full px-2 py-1 text-[11px] font-semibold", badgeClasses(badge.tone)].join(" ")}
                      >
                        {badge.label}
                      </span>
                    ))}
                  </div>

                  <dl className="grid gap-x-6 gap-y-3 text-sm sm:grid-cols-2 xl:grid-cols-4">
                    {showVerificationFields ? (
                      <>
                        <div>
                          <dt className="font-medium text-steel">Profile</dt>
                          <dd className="mt-1 font-semibold text-ink">{formatCountRequirement(workOrder.profiles_quantity, workOrder.profiles_to_count)}</dd>
                        </div>
                        <div>
                          <dt className="font-medium text-steel">Akcesoria</dt>
                          <dd className="mt-1 font-semibold text-ink">{formatCountRequirement(workOrder.accessories_quantity, workOrder.accessories_to_count)}</dd>
                        </div>
                      </>
                    ) : (
                      <div>
                        <dt className="font-medium text-steel">Metraż</dt>
                        <dd className="mt-1 font-semibold text-ink">{formatArea(workOrder.total_area_m2)}</dd>
                      </div>
                    )}
                    <div>
                      <dt className="font-medium text-steel">Farba</dt>
                      <dd className="mt-1 font-semibold text-ink">{formatPaint(workOrder)}</dd>
                    </div>
                    <div>
                      <dt className="font-medium text-steel">Sztuki</dt>
                      <dd className="mt-1 font-semibold text-ink">{workOrder.operational_quantity} szt.</dd>
                    </div>
                  </dl>

                  <TechnicalDrawingLinks workOrderId={workOrder.id} drawings={workOrder.technical_drawings} />

                  <div className="space-y-1 text-sm">
                    <p className="font-semibold text-ink">{status === "DONE" ? `Zakończono: ${title}` : title}</p>
                    {showBatchProgress ? (
                      <p className="text-steel">Postęp partii: {getStageWorkOrderProgressText(workOrder)}</p>
                    ) : null}
                    {showHistoricalResult ? (
                      <p className="font-medium text-emerald-700">{getHistoricalStageWorkOrderResultText(workOrder)}</p>
                    ) : null}
                    {isCorrection ? (
                      <>
                        <p className="font-medium text-amber-800">{buildCorrectionReference(workOrder, correctionContext)}</p>
                        <p className="text-amber-700">
                          {isMergedHistoricalCorrection
                            ? buildMergedCorrectionDeltaText(workOrder, correctionContext)
                            : buildCorrectionQuantityContext(workOrder, correctionContext)}
                        </p>
                      </>
                    ) : null}
                  </div>
                </div>

                <div className="border-t border-line/80 pt-4 lg:border-l lg:border-t-0 lg:pl-5 lg:pt-0">
                  <div className="flex h-full flex-col justify-center gap-3">
                    {isAutomaticProductionView ? (
                      <>
                        <div className="space-y-1 text-sm">
                          <p className="text-steel">Kod farby: {workOrder.paint_code ?? "-"}</p>
                          <p className="text-steel">Aktualny stan farby: {formatPaintKg(workOrder.current_paint_stock_quantity_kg ?? null)}</p>
                          <p className="text-steel">Zużyto: {formatPaintKg(workOrder.consumed_paint_quantity_kg)}</p>
                        </div>

                        {showAutomaticPaintConsumption ? (
                          <>
                            <div className="space-y-3 rounded-lg border border-line/70 bg-mist/60 p-3">
                              <div className="space-y-2">
                                <p className="text-sm font-medium text-steel">Waga kartonu</p>
                                <div className="flex gap-2">
                                  {[20, 25].map((weight) => {
                                    const isSelected = automaticPaintDraft.cartonWeightKg === weight;
                                    return (
                                      <button
                                        key={`${workOrder.id}-${weight}`}
                                        type="button"
                                        onClick={() => {
                                          setPaintConsumptionDrafts((current) => ({
                                            ...current,
                                            [workOrder.id]: {
                                              ...(current[workOrder.id] ?? EMPTY_AUTOMATIC_PAINT_DRAFT),
                                              cartonWeightKg: weight as PaintCartonWeightKg,
                                            },
                                          }));
                                        }}
                                        className={[
                                          "inline-flex items-center justify-center rounded-lg border px-3 py-2 text-sm font-semibold transition",
                                          isSelected
                                            ? "border-accent bg-white text-accent"
                                            : "border-line bg-white text-steel hover:border-accent hover:text-accent",
                                        ].join(" ")}
                                      >
                                        {weight} kg
                                      </button>
                                    );
                                  })}
                                </div>
                              </div>

                              <div className="space-y-2">
                                <p className="text-sm font-medium text-steel">Pobrane kartony</p>
                                <div className="inline-flex items-center rounded-lg border border-line bg-white">
                                  <button
                                    type="button"
                                    aria-label="Usuń karton"
                                    onClick={() => {
                                      setPaintConsumptionDrafts((current) => {
                                        const existingDraft = current[workOrder.id] ?? EMPTY_AUTOMATIC_PAINT_DRAFT;
                                        const nextCartonCount = Math.max(existingDraft.cartonCount - 1, 0);
                                        return {
                                          ...current,
                                          [workOrder.id]: {
                                            ...existingDraft,
                                            cartonCount: nextCartonCount,
                                            finalCartonRemainingKg: nextCartonCount === 0 ? "" : existingDraft.finalCartonRemainingKg,
                                          },
                                        };
                                      });
                                    }}
                                    className="inline-flex h-11 w-11 items-center justify-center text-lg font-semibold text-steel transition hover:text-accent"
                                  >
                                    -
                                  </button>
                                  <span className="min-w-12 border-x border-line px-4 text-center text-base font-semibold text-ink">
                                    {automaticPaintDraft.cartonCount}
                                  </span>
                                  <button
                                    type="button"
                                    aria-label="Dodaj karton"
                                    onClick={() => {
                                      setPaintConsumptionDrafts((current) => {
                                        const existingDraft = current[workOrder.id] ?? EMPTY_AUTOMATIC_PAINT_DRAFT;
                                        return {
                                          ...current,
                                          [workOrder.id]: {
                                            ...existingDraft,
                                            cartonCount: existingDraft.cartonCount + 1,
                                          },
                                        };
                                      });
                                    }}
                                    className="inline-flex h-11 w-11 items-center justify-center text-lg font-semibold text-steel transition hover:text-accent"
                                  >
                                    +
                                  </button>
                                </div>
                              </div>

                              <label className="space-y-1 text-sm font-medium text-steel">
                                <span>Pozostało w ostatnim kartonie [kg]</span>
                                <NumberInput
                                  min={0}
                                  step="0.01"
                                  value={automaticPaintDraft.finalCartonRemainingKg}
                                  onValueChange={(value) => {
                                    setPaintConsumptionDrafts((current) => ({
                                      ...current,
                                      [workOrder.id]: {
                                        ...(current[workOrder.id] ?? EMPTY_AUTOMATIC_PAINT_DRAFT),
                                        finalCartonRemainingKg: value,
                                      },
                                    }));
                                  }}
                                  className="w-full rounded-lg border border-line bg-white px-3 py-2 text-base font-semibold text-ink outline-none transition focus:border-accent focus:ring-2 focus:ring-accent/20"
                                  placeholder="0"
                                />
                              </label>

                              <div className="space-y-1 text-sm">
                                <p className="text-steel">Pobrano z kartonów: {formatPaintKg(automaticPaintPreview.drawnPaintQuantityKg)}</p>
                                <p className="text-steel">Pozostało w ostatnim kartonie: {formatPaintKg(automaticPaintPreview.finalCartonRemainingKg)}</p>
                                <p className="text-steel">Zużycie do zapisu: {formatPaintKg(automaticPaintPreview.consumedPaintQuantityKg)}</p>
                              </div>
                            </div>

                            {!hasAutomaticPaintConfiguration ? (
                              <p className="text-sm text-amber-800">Brak kodu farby w zleceniu.</p>
                            ) : automaticPaintPreview.errorMessage ? (
                              <p className="text-sm text-amber-800">{automaticPaintPreview.errorMessage}</p>
                            ) : null}
                            <button
                              type="button"
                              disabled={
                                isSubmitting
                                || automaticPaintPreview.consumedPaintQuantityKg === null
                                || automaticPaintPreview.errorMessage !== null
                                || !hasAutomaticPaintConfiguration
                              }
                              onClick={() => void handleAutomaticPaintConsumption(workOrder)}
                              className="inline-flex w-full items-center justify-center rounded-lg border border-line bg-white px-4 py-3 text-sm font-semibold text-steel transition hover:border-accent hover:text-accent disabled:cursor-not-allowed disabled:border-line disabled:text-slate-400"
                            >
                              {isSubmitting ? "Zapisywanie..." : "Zapisz zużycie farby"}
                            </button>
                          </>
                        ) : (
                          <p className="text-sm text-steel">Zużycie farby wpiszesz po rozpoczęciu zawieszania.</p>
                        )}
                      </>
                    ) : null}

                    {isSurfacePreparationStage ? (
                      status === "IN_PROGRESS" ? (
                        <label className="space-y-1 text-sm font-medium text-steel">
                          <span>Policzono</span>
                          <NumberInput
                            min={1}
                            step={1}
                            value={countedDraft}
                            onValueChange={(value) => {
                              setCountedQuantities((current) => ({
                                ...current,
                                [workOrder.id]: value,
                              }));
                            }}
                            className="w-full rounded-lg border border-line bg-white px-3 py-2 text-base font-semibold text-ink outline-none transition focus:border-accent focus:ring-2 focus:ring-accent/20"
                            placeholder="Podaj ilość"
                          />
                        </label>
                      ) : (
                        <p className="text-sm text-steel">Policzono: {workOrder.counted_quantity ?? "-"}</p>
                      )
                    ) : null}

                    {showActionButton ? (
                      <button
                        type="button"
                        disabled={isSubmitting || !isActionButtonEnabled}
                        onClick={() => void handleAction(workOrder)}
                        className="inline-flex w-full items-center justify-center rounded-lg border border-line bg-white px-4 py-3 text-sm font-semibold text-steel transition hover:border-accent hover:text-accent disabled:cursor-not-allowed disabled:border-line disabled:text-slate-400"
                      >
                        {isSubmitting ? "Zapisywanie..." : getActionLabel(status)}
                      </button>
                    ) : (
                      <span className="inline-flex w-fit rounded-full bg-mist px-3 py-1 text-xs font-semibold text-steel">
                        {getUnavailableLabel(workOrder)}
                      </span>
                    )}
                  </div>
                </div>
              </div>
            </article>
          );
        })}
      </div>
    );
  }

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-7xl flex-col gap-6 px-4 py-8 sm:px-6 lg:px-8">
      <StationPresenceWidget />
      <section className="rounded-[2rem] border border-white/70 bg-white/80 p-6 shadow-panel backdrop-blur sm:p-8">
        <div className="space-y-2">
          <p className="text-sm font-semibold uppercase tracking-[0.18em] text-accent">Widok etapu</p>
          <div>
            <h2 className="text-3xl font-semibold text-ink sm:text-4xl">{title}</h2>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-steel sm:text-base">
              {readOnly
                ? "Kolejka automatu obejmuje zlecenia do zawieszania, w zawieszaniu i na linii automatycznej."
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
                renderWorkOrderCards(activeWorkOrders)
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

                {showCompleted ? renderWorkOrderCards(completedWorkOrders) : null}
              </div>
            ) : null}
          </div>
        )}
      </section>
    </main>
  );
}
