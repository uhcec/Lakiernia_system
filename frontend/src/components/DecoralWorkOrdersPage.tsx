import { useEffect, useState } from "react";

import { usePolling, STATION_POLL_INTERVAL_MS } from "../hooks/usePolling";
import { getMutationErrorMessage } from "../utils/mutationError";
import { buildWorkOrderDetailHref, getStationIdForLocation } from "../api/stationContext";
import { CorrectionSplitFields } from "./CorrectionSplitFields";
import { NumberInput } from "./NumberInput";
import { StationPresenceWidget } from "./StationPresenceWidget";
import { TechnicalDrawingLinks } from "./TechnicalDrawingLinks";
import { completeDecoralProduction, fetchStageWorkOrders, transitionStage } from "../api/processApi";
import type { StageWorkOrder, StageStatusValue } from "../types/process";
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
  isReturnedDecoralPass,
  parseQuantity,
} from "../utils/workOrderDisplay";

type QueueFilter = "ALL" | "NORMAL" | "CORRECTIONS";

interface DecoralDraft {
  okQuantity: string;
  correctionQuantity: string;
  correctionProfilesQuantity: string;
  correctionAccessoriesQuantity: string;
  correctionReasonCategory: string;
  correctionReasonNote: string;
}

function getActionLabel(status: StageStatusValue): string {
  switch (status) {
    case "NOT_STARTED":
      return "Rozpocznij";
    case "DONE":
      return "Cofnij";
    case "IN_PROGRESS":
      return "Zatwierdź Decoral";
  }
}

function buildEmptyDecoralDraft(activeQuantity: number): DecoralDraft {
  return {
    okQuantity: String(activeQuantity),
    correctionQuantity: "0",
    correctionProfilesQuantity: "0",
    correctionAccessoriesQuantity: "0",
    correctionReasonCategory: "",
    correctionReasonNote: "",
  };
}

function formatCountRequirement(quantity: number | null, shouldCount: boolean): string {
  if (typeof quantity === "number") return `${quantity} szt.`;
  return shouldCount ? "Do policzenia" : "-";
}

function formatSplitBalance(
  total: number,
  profiles: number,
  accessories: number,
): { text: string; tone: "neutral" | "success" | "warning" } {
  if (total <= 0) return { text: "Wpisz ilość poprawki", tone: "neutral" };
  const balance = total - profiles - accessories;
  if (balance === 0) return { text: "Suma zgodna", tone: "success" };
  if (balance > 0) return { text: `Brakuje ${balance} szt.`, tone: "warning" };
  return { text: `O ${Math.abs(balance)} szt. za dużo`, tone: "warning" };
}

export function DecoralWorkOrdersPage() {
  const detailStationId = getStationIdForLocation(window.location.pathname, window.location.search);
  const [workOrders, setWorkOrders] = useState<StageWorkOrder[]>([]);
  const [queueFilter, setQueueFilter] = useState<QueueFilter>("ALL");
  const [isLoading, setIsLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [warningMessage, setWarningMessage] = useState<string | null>(null);
  const [activeWorkOrderId, setActiveWorkOrderId] = useState<string | null>(null);
  const [showCompleted, setShowCompleted] = useState(false);
  const [drafts, setDrafts] = useState<Record<string, DecoralDraft>>({});
  const [correctionContextByOrderId, setCorrectionContextByOrderId] = useState<Record<number, CorrectionContext>>({});

  // Namespace the draft key by ID space: batch IDs and work-order IDs come from different sequences,
  // so a bare `batch_id ?? id` could collide a batch with a batchless order sharing the same integer.
  function getDraftKey(workOrder: StageWorkOrder): string {
    return workOrder.batch_id != null ? `b${workOrder.batch_id}` : `w${workOrder.id}`;
  }

  const filteredWorkOrders = workOrders.filter((workOrder) => {
    if (queueFilter === "NORMAL") return !workOrder.is_correction && !workOrder.is_correction_round;
    if (queueFilter === "CORRECTIONS") return workOrder.is_correction || workOrder.is_correction_round;
    return true;
  });
  const activeWorkOrders = filteredWorkOrders.filter((w) => w.stage_status.status.value !== "DONE");
  const completedWorkOrders = filteredWorkOrders.filter((w) => w.stage_status.status.value === "DONE");

  async function loadWorkOrders(options?: { preserveErrorMessage?: boolean; background?: boolean }): Promise<boolean> {
    const background = options?.background ?? false;
    if (!background) {
      setIsLoading(true);
      if (!options?.preserveErrorMessage) setErrorMessage(null);
      setWarningMessage(null);
    }
    try {
      const items = await fetchStageWorkOrders("DECORAL_PRODUCTION");
      setWorkOrders(items);
      const correctionContexts = await loadCorrectionContexts(items);
      setCorrectionContextByOrderId(correctionContexts.contexts);
      if (correctionContexts.failedCount > 0 && !background) {
        setWarningMessage("Nie udało się pobrać pełnego kontekstu dla części poprawek. Lista pozostaje dostępna.");
      }
      // In background mode preserve drafts being edited; only seed newly appeared orders.
      setDrafts((prev) => {
        const nextDrafts: Record<string, DecoralDraft> = background ? { ...prev } : {};
        for (const item of items) {
          const draftKey = getDraftKey(item);
          if (background && draftKey in nextDrafts) {
            continue;
          }
          nextDrafts[draftKey] = buildEmptyDecoralDraft(item.current_active_quantity);
        }
        return nextDrafts;
      });
      return true;
    } catch (error) {
      if (!background) {
        setErrorMessage(error instanceof Error ? error.message : "Nie udało się pobrać zleceń Decoral");
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
  }, []);

  // Auto-refresh so Decoral reflects changes made on other devices without a reload.
  usePolling(
    () => {
      void loadWorkOrders({ background: true });
    },
    STATION_POLL_INTERVAL_MS,
    activeWorkOrderId === null,
  );

  function updateDraft(draftKey: string, fieldName: keyof DecoralDraft, value: string) {
    setDrafts((current) => ({
      ...current,
      [draftKey]: {
        ...(current[draftKey] ?? buildEmptyDecoralDraft(0)),
        [fieldName]: value,
      },
    }));
  }

  async function handleStageAction(workOrder: StageWorkOrder) {
    const status = workOrder.stage_status.status.value;
    const draftKey = getDraftKey(workOrder);
    setActiveWorkOrderId(draftKey);
    setErrorMessage(null);
    try {
      if (status === "NOT_STARTED") {
        await transitionStage(workOrder.id, "DECORAL_PRODUCTION", "start", workOrder.batch_id ?? undefined);
      } else if (status === "DONE") {
        await transitionStage(workOrder.id, "DECORAL_PRODUCTION", "reopen", workOrder.batch_id ?? undefined);
      }
      await loadWorkOrders();
    } catch (error) {
      const message = getMutationErrorMessage(
        error,
        "Nie udało się zmienić statusu Decoral. Widok został odświeżony do aktualnego stanu backendu.",
      );
      const reloaded = await loadWorkOrders({ preserveErrorMessage: true });
      if (reloaded) setErrorMessage(message);
    } finally {
      setActiveWorkOrderId(null);
    }
  }

  async function handleDecoralSubmit(workOrder: StageWorkOrder) {
    const draftKey = getDraftKey(workOrder);
    const draft = drafts[draftKey] ?? buildEmptyDecoralDraft(workOrder.current_active_quantity);
    const okQuantity = parseQuantity(draft.okQuantity);
    const correctionQuantity = parseQuantity(draft.correctionQuantity);
    const correctionProfilesQuantity = parseQuantity(draft.correctionProfilesQuantity);
    const correctionAccessoriesQuantity = parseQuantity(draft.correctionAccessoriesQuantity);
    const correctionReasonCategory = draft.correctionReasonCategory.trim();
    const correctionReasonNote = draft.correctionReasonNote.trim();

    if (!Number.isInteger(okQuantity) || !Number.isInteger(correctionQuantity) || okQuantity < 0 || correctionQuantity < 0) {
      setErrorMessage("Ilości muszą być nieujemnymi liczbami całkowitymi");
      return;
    }
    if (okQuantity + correctionQuantity <= 0) {
      setErrorMessage("Suma ilości OK i do poprawki musi być większa od zera");
      return;
    }
    if (correctionQuantity > 0 && correctionReasonCategory === "") {
      setErrorMessage("Wybierz powód poprawki przed zatwierdzeniem");
      return;
    }
    if (
      correctionQuantity > 0 &&
      correctionProfilesQuantity + correctionAccessoriesQuantity !== correctionQuantity
    ) {
      setErrorMessage("Suma profili i akcesoriów do poprawki musi być równa ilości poprawek");
      return;
    }

    setActiveWorkOrderId(draftKey);
    setErrorMessage(null);

    const payload = {
      ok_quantity: okQuantity,
      correction_quantity: correctionQuantity,
      ...(correctionQuantity > 0
        ? {
            correction_profiles_quantity: correctionProfilesQuantity,
            correction_accessories_quantity: correctionAccessoriesQuantity,
            correction_reason_category: correctionReasonCategory,
            ...(correctionReasonNote ? { correction_reason_note: correctionReasonNote } : {}),
          }
        : {}),
    };

    try {
      await completeDecoralProduction(workOrder.id, payload, workOrder.batch_id ?? undefined);
      await loadWorkOrders();
    } catch (error) {
      const message = getMutationErrorMessage(
        error,
        "Nie udało się zatwierdzić Decoral. Widok został odświeżony do aktualnego stanu backendu.",
      );
      const reloaded = await loadWorkOrders({ preserveErrorMessage: true });
      if (reloaded) setErrorMessage(message);
    } finally {
      setActiveWorkOrderId(null);
    }
  }

  function renderWorkOrderCards(items: StageWorkOrder[]) {
    return (
      <div className="space-y-3">
        {items.map((workOrder) => {
          const status = workOrder.stage_status.status.value;
          const isDecoralInProgress = status === "IN_PROGRESS";
          const draftKey = getDraftKey(workOrder);
          const isSubmitting = activeWorkOrderId === draftKey;
          const draft = drafts[draftKey] ?? buildEmptyDecoralDraft(workOrder.current_active_quantity);
          const okQuantity = parseQuantity(draft.okQuantity);
          const correctionQuantity = parseQuantity(draft.correctionQuantity);
          const correctionProfilesQuantity = parseQuantity(draft.correctionProfilesQuantity);
          const correctionAccessoriesQuantity = parseQuantity(draft.correctionAccessoriesQuantity);
          const hasRequiredCorrectionReason = correctionQuantity === 0 || draft.correctionReasonCategory.trim() !== "";
          const hasValidCorrectionSplit =
            correctionQuantity === 0 ||
            (Number.isInteger(correctionProfilesQuantity) &&
              Number.isInteger(correctionAccessoriesQuantity) &&
              correctionProfilesQuantity >= 0 &&
              correctionAccessoriesQuantity >= 0 &&
              correctionProfilesQuantity + correctionAccessoriesQuantity === correctionQuantity);
          const isDraftValid =
            Number.isInteger(okQuantity) &&
            Number.isInteger(correctionQuantity) &&
            okQuantity >= 0 &&
            correctionQuantity >= 0 &&
            okQuantity + correctionQuantity > 0 &&
            hasValidCorrectionSplit &&
            hasRequiredCorrectionReason;
          const splitBalance = formatSplitBalance(correctionQuantity, correctionProfilesQuantity, correctionAccessoriesQuantity);
          const correctionContext = correctionContextByOrderId[workOrder.id];
          const isMergedHistoricalCorrection = workOrder.is_historical_correction;
          const showHistoricalResult = status === "DONE" && !workOrder.is_correction;
          const showBatchProgress = status !== "DONE" || (workOrder.is_correction && !isMergedHistoricalCorrection);
          const isCorrection = workOrder.is_correction || workOrder.is_correction_round;

          return (
            <article
              key={`${workOrder.id}-${draftKey}`}
              className={[
                "rounded-lg border bg-white p-5 text-ink shadow-sm",
                isCorrection ? "border-amber-200 bg-amber-50/40" : "border-line/80",
              ].join(" ")}
            >
              <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(20rem,28rem)]">
                <div className="space-y-4">
                  <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                    <div className="min-w-0 space-y-2">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="inline-flex rounded-full bg-mist px-3 py-1 text-xs font-semibold text-steel">
                          Poz. {workOrder.queue_position ?? "-"}
                        </span>
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
                    {getStageWorkOrderBadgeStack(workOrder).map((badge) => (
                      <span
                        key={`${workOrder.id}-${badge.label}`}
                        className={["inline-flex rounded-full px-2 py-1 text-[11px] font-semibold", badgeClasses(badge.tone)].join(" ")}
                      >
                        {badge.label}
                      </span>
                    ))}
                    {/* CHANGES #2: the returned corrected pieces are a separate, second Decoral pass — make it
                        explicit so the operator doesn't mistake them for the original run. */}
                    {isReturnedDecoralPass(workOrder) ? (
                      <span className="inline-flex rounded-full bg-violet-100 px-2 py-1 text-[11px] font-semibold text-violet-800">
                        DRUGI PRZEBIEG · poprawione sztuki
                      </span>
                    ) : null}
                  </div>

                  <dl className="grid gap-x-6 gap-y-3 text-sm sm:grid-cols-2 xl:grid-cols-4">
                    <div>
                      <dt className="font-medium text-steel">Profile</dt>
                      <dd className="mt-1 font-semibold text-ink">{formatCountRequirement(workOrder.profiles_quantity, workOrder.profiles_to_count)}</dd>
                    </div>
                    <div>
                      <dt className="font-medium text-steel">Akcesoria</dt>
                      <dd className="mt-1 font-semibold text-ink">{formatCountRequirement(workOrder.accessories_quantity, workOrder.accessories_to_count)}</dd>
                    </div>
                    <div>
                      <dt className="font-medium text-steel">Farba</dt>
                      <dd className="mt-1 font-semibold text-ink">{`${workOrder.paint_producer} / ${workOrder.ral_code}`}</dd>
                    </div>
                    <div>
                      <dt className="font-medium text-steel">Folia</dt>
                      <dd className="mt-1 font-semibold text-ink">
                        {workOrder.decoral_foil ? `${workOrder.decoral_foil.name} (${workOrder.decoral_foil.code})` : "—"}
                      </dd>
                    </div>
                    <div>
                      <dt className="font-medium text-steel">Sztuki</dt>
                      <dd className="mt-1 font-semibold text-ink">{workOrder.operational_quantity} szt.</dd>
                    </div>
                  </dl>

                  <TechnicalDrawingLinks workOrderId={workOrder.id} drawings={workOrder.technical_drawings} />

                  <div className="space-y-1 text-sm">
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
                  {isDecoralInProgress ? (
                    <div className="space-y-4">
                      <div className="grid gap-3 sm:grid-cols-2">
                        <label className="space-y-1 text-sm font-medium text-steel">
                          <span>OK</span>
                          <NumberInput
                            min="0"
                            step="1"
                            value={draft.okQuantity}
                            onValueChange={(value) => updateDraft(draftKey, "okQuantity", value)}
                            className="w-full rounded-lg border border-line bg-white px-3 py-2 text-base font-semibold text-ink outline-none transition focus:border-accent"
                          />
                        </label>
                        <label className="space-y-1 text-sm font-medium text-steel">
                          <span>Poprawki</span>
                          <NumberInput
                            min="0"
                            step="1"
                            value={draft.correctionQuantity}
                            onValueChange={(value) => updateDraft(draftKey, "correctionQuantity", value)}
                            className="w-full rounded-lg border border-line bg-white px-3 py-2 text-base font-semibold text-ink outline-none transition focus:border-accent"
                          />
                        </label>
                      </div>

                      {correctionQuantity > 0 ? (
                        <div className="space-y-3">
                          <CorrectionSplitFields
                            correctionProfilesQuantity={draft.correctionProfilesQuantity}
                            correctionAccessoriesQuantity={draft.correctionAccessoriesQuantity}
                            correctionReasonCategory={draft.correctionReasonCategory}
                            correctionReasonNote={draft.correctionReasonNote}
                            splitBalance={splitBalance}
                            onFieldChange={(field, value) => updateDraft(draftKey, field, value)}
                          />
                        </div>
                      ) : null}

                      <button
                        type="button"
                        disabled={isSubmitting || !isDraftValid}
                        onClick={() => void handleDecoralSubmit(workOrder)}
                        className="inline-flex w-full items-center justify-center rounded-lg bg-accent px-4 py-3 text-sm font-semibold text-white transition hover:bg-teal-700 disabled:cursor-not-allowed disabled:bg-teal-300"
                      >
                        {isSubmitting ? "Zapisywanie..." : getActionLabel(status)}
                      </button>
                    </div>
                  ) : (
                    <div className="flex h-full flex-col justify-center gap-3">
                      {status === "DONE" ? (
                        <p className="text-sm font-semibold text-emerald-700">{workOrder.planned_quantity} szt. zakończone</p>
                      ) : null}
                      <button
                        type="button"
                        disabled={isSubmitting}
                        onClick={() => void handleStageAction(workOrder)}
                        className="inline-flex w-full items-center justify-center rounded-lg border border-line bg-white px-4 py-3 text-sm font-semibold text-steel transition hover:border-accent hover:text-accent disabled:cursor-not-allowed disabled:border-line disabled:text-slate-400"
                      >
                        {isSubmitting ? "Zapisywanie..." : getActionLabel(status)}
                      </button>
                    </div>
                  )}
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
            <h2 className="text-3xl font-semibold text-ink sm:text-4xl">Produkcja Decoral</h2>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-steel sm:text-base">
              Produkcja Decoral — kontrola jakości i zatwierdzanie zleceń.
            </p>
            <div className="mt-3 inline-flex rounded-full border border-line bg-mist p-1">
              {(["ALL", "NORMAL", "CORRECTIONS"] as QueueFilter[]).map((filter) => (
                <button
                  key={filter}
                  type="button"
                  onClick={() => setQueueFilter(filter)}
                  className={[
                    "rounded-full px-4 py-2 text-sm font-medium transition",
                    queueFilter === filter ? "bg-white text-ink shadow-sm" : "text-steel hover:text-accent",
                  ].join(" ")}
                >
                  {filter === "ALL" ? "Wszystkie" : filter === "NORMAL" ? "Zwykłe" : "Poprawki"}
                </button>
              ))}
            </div>
          </div>
        </div>
      </section>

      {errorMessage ? (
        <section className="rounded-2xl border border-rose-200 bg-rose-50 px-5 py-4 text-sm text-rose-700">{errorMessage}</section>
      ) : null}
      {warningMessage ? (
        <section className="rounded-2xl border border-amber-200 bg-amber-50 px-5 py-4 text-sm text-amber-700">{warningMessage}</section>
      ) : null}

      {isLoading ? (
        <section className="rounded-2xl border border-line bg-white/80 px-5 py-8 text-center text-sm text-steel">Ładowanie...</section>
      ) : (
        <>
          {activeWorkOrders.length === 0 && !showCompleted ? (
            <section className="rounded-2xl border border-line bg-white/80 px-5 py-8 text-center text-sm text-steel">
              Brak aktywnych zleceń Decoral
            </section>
          ) : null}

          {activeWorkOrders.length > 0 ? renderWorkOrderCards(activeWorkOrders) : null}

          <div className="mt-2">
            <button
              type="button"
              onClick={() => setShowCompleted((v) => !v)}
              className="text-sm font-medium text-steel hover:text-accent"
            >
              {showCompleted ? "Ukryj zakończone" : `Pokaż zakończone (${completedWorkOrders.length})`}
            </button>
          </div>

          {showCompleted && completedWorkOrders.length > 0 ? (
            <div className="opacity-70">{renderWorkOrderCards(completedWorkOrders)}</div>
          ) : null}
        </>
      )}
    </main>
  );
}
