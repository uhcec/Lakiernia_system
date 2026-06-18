import { useEffect, useState } from "react";

import { usePolling, STATION_POLL_INTERVAL_MS } from "../hooks/usePolling";
import { getMutationErrorMessage } from "../utils/mutationError";
import { buildWorkOrderDetailHref, getStationIdForLocation } from "../api/stationContext";
import { StationPresenceWidget } from "./StationPresenceWidget";
import { completePacking, fetchStageWorkOrders, releasePacking, startPacking, transitionStage } from "../api/processApi";
import type { StageWorkOrder, StageStatusValue } from "../types/process";
import { loadCorrectionContexts, type CorrectionContext } from "../utils/correctionContext";
import {
  formatWorkOrderPrimaryInfo,
  getHistoricalStageWorkOrderResultText,
  getStageWorkOrderBadgeStack,
  getStageWorkOrderProgressText,
  type DisplayBadge,
} from "../utils/workOrderDisplay";

type QueueFilter = "ALL" | "NORMAL" | "CORRECTIONS";

interface PackingDraft {
  countedQuantity: string;
  okQuantity: string;
  correctionQuantity: string;
  correctionProfilesQuantity: string;
  correctionAccessoriesQuantity: string;
  correctionReasonCategory: string;
  correctionReasonNote: string;
}

const correctionReasonOptions = [
  { value: "niedomalowanie", label: "Niedomalowanie" },
  { value: "za grubo", label: "Za grubo" },
  { value: "wtrącenia", label: "Wtrącenia" },
  { value: "inne", label: "Inne" },
];

function getActionLabel(status: StageStatusValue): string {
  switch (status) {
    case "NOT_STARTED":
      return "Rozpocznij";
    case "DONE":
      return "Cofnij";
    case "IN_PROGRESS":
      return "Zakończ pakowanie";
  }
}

function parseQuantity(value: string): number {
  if (value.trim() === "") {
    return 0;
  }

  return Number(value);
}

function buildEmptyPackingDraft(): PackingDraft {
  return {
    countedQuantity: "",
    okQuantity: "0",
    correctionQuantity: "0",
    correctionProfilesQuantity: "0",
    correctionAccessoriesQuantity: "0",
    correctionReasonCategory: "",
    correctionReasonNote: "",
  };
}

function formatPaint(workOrder: StageWorkOrder): string {
  return `${workOrder.paint_producer} / ${workOrder.ral_code}`;
}

function formatCountRequirement(quantity: number | null, shouldCount: boolean): string {
  if (typeof quantity === "number") {
    return `${quantity} szt.`;
  }
  return shouldCount ? "Do policzenia" : "-";
}

function getPackingRowSummary(workOrder: StageWorkOrder): string {
  if (workOrder.stage_status.stage === "HANGING") {
    return "W zawieszaniu - oczekuje na pakowanie";
  }

  return workOrder.stage_status.status.value === "DONE" ? "Pakowanie zakończone" : "W pakowaniu";
}

function buildCorrectionReference(workOrder: StageWorkOrder, context: CorrectionContext | undefined): string {
  if (workOrder.is_correction_round) {
    return `Poprawka — runda ${workOrder.order_number}`;
  }
  if (!workOrder.is_correction) {
    return "";
  }
  if (context?.parentOrderNumber) {
    return `Poprawka do ${context.parentOrderNumber}`;
  }
  return "Poprawka do zlecenia nadrzędnego";
}

function buildCorrectionQuantityContext(workOrder: StageWorkOrder, context: CorrectionContext | undefined): string {
  if (workOrder.is_correction_round) {
    return `${workOrder.total_quantity} szt. poprawki`;
  }
  if (!workOrder.is_correction) {
    return "";
  }
  if (typeof context?.parentTotalQuantity === "number") {
    return `${workOrder.total_quantity} szt. poprawki z ${context.parentTotalQuantity}`;
  }
  return `${workOrder.total_quantity} szt. poprawki`;
}

function buildMergedCorrectionDeltaText(workOrder: StageWorkOrder, context: CorrectionContext | undefined): string {
  if (typeof context?.parentTotalQuantity === "number") {
    return `Poprawiono ${workOrder.total_quantity} z ${context.parentTotalQuantity} szt.`;
  }

  return `Poprawiono ${workOrder.total_quantity} szt.`;
}

function formatPackingBalance(countedQuantity: number, okQuantity: number, correctionQuantity: number): { text: string; tone: "neutral" | "success" | "warning" } {
  if (countedQuantity <= 0) {
    return { text: "Wpisz policzoną ilość", tone: "neutral" };
  }

  const balance = countedQuantity - okQuantity - correctionQuantity;
  if (balance === 0) {
    return { text: "Suma zgodna", tone: "success" };
  }

  if (balance > 0) {
    return { text: `Brakuje ${balance} szt.`, tone: "warning" };
  }

  return { text: `O ${Math.abs(balance)} szt. za dużo`, tone: "warning" };
}

function formatCorrectionSplitBalance(correctionQuantity: number, profilesQuantity: number, accessoriesQuantity: number): { text: string; tone: "neutral" | "success" | "warning" } {
  if (correctionQuantity <= 0) {
    return { text: "Wpisz ilość poprawki", tone: "neutral" };
  }

  const balance = correctionQuantity - profilesQuantity - accessoriesQuantity;
  if (balance === 0) {
    return { text: "Suma zgodna", tone: "success" };
  }

  if (balance > 0) {
    return { text: `Brakuje ${balance} szt.`, tone: "warning" };
  }

  return { text: `O ${Math.abs(balance)} szt. za dużo`, tone: "warning" };
}

function balanceClasses(tone: ReturnType<typeof formatPackingBalance>["tone"]): string {
  switch (tone) {
    case "success":
      return "border-emerald-200 bg-emerald-50 text-emerald-700";
    case "warning":
      return "border-amber-200 bg-amber-50 text-amber-800";
    case "neutral":
      return "border-line bg-mist text-steel";
  }
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

export function PackingWorkOrdersPage() {
  const detailStationId = getStationIdForLocation(window.location.pathname, window.location.search);
  const [workOrders, setWorkOrders] = useState<StageWorkOrder[]>([]);
  const [queueFilter, setQueueFilter] = useState<QueueFilter>("ALL");
  const [isLoading, setIsLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [warningMessage, setWarningMessage] = useState<string | null>(null);
  const [activeWorkOrderId, setActiveWorkOrderId] = useState<number | null>(null);
  const [showCompleted, setShowCompleted] = useState(false);
  const [drafts, setDrafts] = useState<Record<number, PackingDraft>>({});
  const [correctionContextByOrderId, setCorrectionContextByOrderId] = useState<Record<number, CorrectionContext>>({});

  function getDraftKey(workOrder: StageWorkOrder): number {
    return workOrder.batch_id ?? workOrder.id;
  }

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
      const items = await fetchStageWorkOrders("PACKING");
      setWorkOrders(items);
      const correctionContexts = await loadCorrectionContexts(items);
      setCorrectionContextByOrderId(correctionContexts.contexts);

      if (correctionContexts.failedCount > 0 && !background) {
        setWarningMessage("Nie udało się pobrać pełnego kontekstu dla części poprawek. Lista pozostaje dostępna.");
      }

      // In background mode preserve drafts the operator is editing; only seed orders
      // that just appeared so a poll never wipes an in-progress packing count.
      setDrafts((prev) => {
        const nextDrafts: Record<number, PackingDraft> = background ? { ...prev } : {};
        for (const item of items) {
          const draftKey = getDraftKey(item);
          if (background && draftKey in nextDrafts) {
            continue;
          }
          nextDrafts[draftKey] = {
            countedQuantity: item.counted_quantity?.toString() ?? "",
            okQuantity: String(item.counted_quantity ?? item.current_active_quantity),
            correctionQuantity: "0",
            correctionProfilesQuantity: "0",
            correctionAccessoriesQuantity: "0",
            correctionReasonCategory: "",
            correctionReasonNote: "",
          };
        }
        return nextDrafts;
      });
      return true;
    } catch (error) {
      if (!background) {
        setErrorMessage(error instanceof Error ? error.message : "Nie udało się pobrać zleceń do pakowania");
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

  // Auto-refresh so packing reflects changes made on other devices without a reload.
  usePolling(
    () => {
      void loadWorkOrders({ background: true });
    },
    STATION_POLL_INTERVAL_MS,
    activeWorkOrderId === null,
  );

  function updateDraft(workOrderId: number, fieldName: keyof PackingDraft, value: string) {
    setDrafts((current) => ({
      ...current,
      [workOrderId]: {
        ...(current[workOrderId] ?? buildEmptyPackingDraft()),
        [fieldName]: value,
      },
    }));
  }

  async function handleStageAction(workOrder: StageWorkOrder) {
    const status = workOrder.stage_status.status.value;
    setActiveWorkOrderId(getDraftKey(workOrder));
    setErrorMessage(null);

    try {
      if (status === "NOT_STARTED") {
        await transitionStage(workOrder.id, "PACKING", "start", workOrder.batch_id ?? undefined);
      } else if (status === "DONE") {
        await transitionStage(workOrder.id, "PACKING", "reopen", workOrder.batch_id ?? undefined);
      }
      await loadWorkOrders();
    } catch (error) {
      const message = getMutationErrorMessage(
        error,
        "Nie udało się zmienić statusu pakowania. Widok został odświeżony do aktualnego stanu backendu.",
      );
      const reloaded = await loadWorkOrders({ preserveErrorMessage: true });

      if (reloaded) {
        setErrorMessage(message);
      }
    } finally {
      setActiveWorkOrderId(null);
    }
  }

  async function handleStartPacking(workOrder: StageWorkOrder, override = false) {
    setActiveWorkOrderId(getDraftKey(workOrder));
    setErrorMessage(null);

    try {
      await startPacking(workOrder.id, workOrder.batch_id ?? undefined, override);
      await loadWorkOrders();
    } catch (error) {
      const message = getMutationErrorMessage(
        error,
        "Nie udało się rozpocząć pakowania. Widok został odświeżony do aktualnego stanu backendu.",
      );
      const reloaded = await loadWorkOrders({ preserveErrorMessage: true });

      if (reloaded) {
        setErrorMessage(message);
      }
    } finally {
      setActiveWorkOrderId(null);
    }
  }

  async function handleReleasePacking(workOrder: StageWorkOrder) {
    setActiveWorkOrderId(getDraftKey(workOrder));
    setErrorMessage(null);

    try {
      await releasePacking(workOrder.id, workOrder.batch_id ?? undefined);
      await loadWorkOrders();
    } catch (error) {
      const message = getMutationErrorMessage(
        error,
        "Nie udało się zwolnić stanowiska pakowania. Widok został odświeżony do aktualnego stanu backendu.",
      );
      const reloaded = await loadWorkOrders({ preserveErrorMessage: true });

      if (reloaded) {
        setErrorMessage(message);
      }
    } finally {
      setActiveWorkOrderId(null);
    }
  }

  function handleOverridePacking(workOrder: StageWorkOrder, occupants: StageWorkOrder[]) {
    // The warning is shown only at the moment of opening a second station (not persistently), because
    // an automatic order reserves packing at hanging start — parts may not have reached packing yet.
    const occupantLines = occupants
      .map(
        (occupant) =>
          `• ${occupant.order_number} (${occupant.current_active_quantity} szt.${
            occupant.production_type?.value === "AUTOMATIC" ? ", automat" : ""
          })`,
      )
      .join("\n");
    const message =
      "Uwaga: automat rezerwuje pakowanie już przy rozpoczęciu zawieszania — części mogą jeszcze nie " +
      "dotrzeć z linii, więc stanowisko może wyglądać na wolne.\n\nZajęte przez:\n" +
      `${occupantLines}\n\nOtworzyć drugie stanowisko mimo to?`;
    if (window.confirm(message)) {
      void handleStartPacking(workOrder, true);
    }
  }

  async function handlePackingSubmit(workOrder: StageWorkOrder) {
    const draftKey = getDraftKey(workOrder);
    const draft = drafts[draftKey] ?? buildEmptyPackingDraft();
    const countedQuantity = parseQuantity(draft.countedQuantity);
    const okQuantity = parseQuantity(draft.okQuantity);
    const correctionQuantity = parseQuantity(draft.correctionQuantity);
    const correctionProfilesQuantity = parseQuantity(draft.correctionProfilesQuantity);
    const correctionAccessoriesQuantity = parseQuantity(draft.correctionAccessoriesQuantity);
    const correctionReasonCategory = draft.correctionReasonCategory.trim();
    const correctionReasonNote = draft.correctionReasonNote.trim();

    if (
      !Number.isInteger(countedQuantity) ||
      countedQuantity <= 0 ||
      !Number.isInteger(okQuantity) ||
      !Number.isInteger(correctionQuantity) ||
      okQuantity < 0 ||
      correctionQuantity < 0
    ) {
      setErrorMessage("Policzono musi być dodatnią liczbą całkowitą, a ilości pakowania muszą być nieujemnymi liczbami całkowitymi");
      return;
    }

    if (
      correctionQuantity > 0 &&
      (!Number.isInteger(correctionProfilesQuantity) ||
        !Number.isInteger(correctionAccessoriesQuantity) ||
        correctionProfilesQuantity < 0 ||
        correctionAccessoriesQuantity < 0)
    ) {
      setErrorMessage("Ilości profili i akcesoriów do poprawki muszą być nieujemnymi liczbami całkowitymi");
      return;
    }

    if (okQuantity + correctionQuantity !== countedQuantity) {
      setErrorMessage("Suma ilości OK i do poprawki musi być równa wartości Policzono");
      return;
    }

    if (correctionQuantity > 0 && correctionProfilesQuantity + correctionAccessoriesQuantity !== correctionQuantity) {
      setErrorMessage("Suma profili i akcesoriów do poprawki musi być równa ilości poprawek");
      return;
    }

    if (correctionQuantity > 0 && correctionReasonCategory === "") {
      setErrorMessage("Wybierz powód poprawki przed zatwierdzeniem pakowania");
      return;
    }

    setActiveWorkOrderId(draftKey);
    setErrorMessage(null);

    const payload = {
      counted_quantity: countedQuantity,
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
      await completePacking(
        workOrder.id,
        payload,
        workOrder.batch_id ?? undefined,
      );
      await loadWorkOrders();
    } catch (error) {
      const message = getMutationErrorMessage(
        error,
        "Nie udało się zatwierdzić pakowania. Widok został odświeżony do aktualnego stanu backendu.",
      );
      const reloaded = await loadWorkOrders({ preserveErrorMessage: true });

      if (reloaded) {
        setErrorMessage(message);
      }
    } finally {
      setActiveWorkOrderId(null);
    }
  }

  function renderWorkOrderCards(items: StageWorkOrder[]) {
    // Packing has N slots (NA22). Orders that hold a slot include automatic orders that reserved one
    // at hanging start (they may still show as a HANGING waiting row but occupy a slot).
    const slotOccupants = workOrders.filter((candidate) => candidate.holds_packing_slot);
    const occupiedCount = slotOccupants.length;
    const slotsTotal = workOrders[0]?.packing_slots_total ?? 1;
    return (
      <div className="space-y-3">
        {items.map((workOrder) => {
          const status = workOrder.stage_status.status.value;
          const isPackingStage = workOrder.stage_status.stage === "PACKING";
          const isBeingPacked = isPackingStage && workOrder.is_being_packed;
          // This manual card is at packing but holds no slot: it can start only if the station is
          // free, otherwise it must override to open another slot (up to N), or all slots are full.
          const canStartFree = isPackingStage && status !== "DONE" && !isBeingPacked && occupiedCount === 0;
          const needsOverride = isPackingStage && status !== "DONE" && !isBeingPacked && occupiedCount > 0 && occupiedCount < slotsTotal;
          const allSlotsFull = isPackingStage && status !== "DONE" && !isBeingPacked && occupiedCount >= slotsTotal;
          const otherOccupants = slotOccupants.filter((candidate) => getDraftKey(candidate) !== getDraftKey(workOrder));
          const draftKey = getDraftKey(workOrder);
          const isSubmitting = activeWorkOrderId === draftKey;
          const draft = drafts[draftKey] ?? buildEmptyPackingDraft();
          const countedQuantity = parseQuantity(draft.countedQuantity);
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
            Number.isInteger(countedQuantity) &&
            countedQuantity > 0 &&
            Number.isInteger(okQuantity) &&
            Number.isInteger(correctionQuantity) &&
            okQuantity >= 0 &&
            correctionQuantity >= 0 &&
            okQuantity + correctionQuantity === countedQuantity &&
            hasValidCorrectionSplit &&
            hasRequiredCorrectionReason;
          const packingBalance = formatPackingBalance(countedQuantity, okQuantity, correctionQuantity);
          const correctionSplitBalance = formatCorrectionSplitBalance(correctionQuantity, correctionProfilesQuantity, correctionAccessoriesQuantity);
          const correctionContext = correctionContextByOrderId[workOrder.id];
          const isMergedHistoricalCorrection = workOrder.is_historical_correction;
          const showHistoricalResult = status === "DONE" && !workOrder.is_correction;
          const showBatchProgress = status !== "DONE" || (workOrder.is_correction && !isMergedHistoricalCorrection);

          return (
            <article
              key={`${workOrder.id}-${draftKey}`}
              className={[
                "rounded-lg border bg-white p-5 text-ink shadow-sm",
                (workOrder.is_correction || workOrder.is_correction_round) ? "border-amber-200 bg-amber-50/40" : "border-line/80",
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
                          {workOrder.is_decoral_incomplete ? `N${workOrder.order_number}` : !workOrder.order_number.startsWith("P") && workOrder.completed_quantity > 0 && workOrder.completed_quantity < workOrder.total_quantity ? `P${workOrder.order_number}` : workOrder.order_number}
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
                      <dd className="mt-1 font-semibold text-ink">{formatPaint(workOrder)}</dd>
                    </div>
                    <div>
                      <dt className="font-medium text-steel">Sztuki</dt>
                      <dd className="mt-1 font-semibold text-ink">{workOrder.operational_quantity} szt.</dd>
                    </div>
                  </dl>

                  <div className="space-y-1 text-sm">
                    <p className="font-semibold text-ink">{getPackingRowSummary(workOrder)}</p>
                    {showBatchProgress ? (
                      <p className="text-steel">Postęp partii: {getStageWorkOrderProgressText(workOrder)}</p>
                    ) : null}
                    {showHistoricalResult ? (
                      <p className="font-medium text-emerald-700">{getHistoricalStageWorkOrderResultText(workOrder)}</p>
                    ) : null}
                    {(workOrder.is_correction || workOrder.is_correction_round) ? (
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
                  {!isPackingStage ? (
                    <div className="flex h-full flex-col justify-center gap-3">
                      <span className="inline-flex w-fit rounded-full bg-amber-100 px-3 py-1 text-xs font-semibold text-amber-800">
                        Czeka na koniec zawieszania
                      </span>
                    </div>
                  ) : isBeingPacked ? (
                    <div className="space-y-4">
                      <div className="grid gap-3 sm:grid-cols-3">
                        <label className="space-y-1 text-sm font-medium text-steel">
                          <span>Policzono</span>
                          <input
                            type="number"
                            min="1"
                            step="1"
                            value={draft.countedQuantity}
                            onChange={(event) => updateDraft(draftKey, "countedQuantity", event.target.value)}
                            className="w-full rounded-lg border border-line bg-white px-3 py-2 text-base font-semibold text-ink outline-none transition focus:border-accent"
                          />
                        </label>
                        <label className="space-y-1 text-sm font-medium text-steel">
                          <span>OK</span>
                          <input
                            type="number"
                            min="0"
                            step="1"
                            value={draft.okQuantity}
                            onChange={(event) => updateDraft(draftKey, "okQuantity", event.target.value)}
                            className="w-full rounded-lg border border-line bg-white px-3 py-2 text-base font-semibold text-ink outline-none transition focus:border-accent"
                          />
                        </label>
                        <label className="space-y-1 text-sm font-medium text-steel">
                          <span>Poprawki</span>
                          <input
                            type="number"
                            min="0"
                            step="1"
                            value={draft.correctionQuantity}
                            onChange={(event) => updateDraft(draftKey, "correctionQuantity", event.target.value)}
                            className="w-full rounded-lg border border-line bg-white px-3 py-2 text-base font-semibold text-ink outline-none transition focus:border-accent"
                          />
                        </label>
                      </div>

                      <div className={["rounded-lg border px-3 py-2 text-sm font-semibold", balanceClasses(packingBalance.tone)].join(" ")}>
                        Bilans pakowania: {packingBalance.text}
                      </div>
                      <p className="text-xs font-medium text-steel">OK + Poprawki = Policzono</p>

                      {correctionQuantity > 0 ? (
                        <div className="space-y-3">
                          <div className="grid gap-3 sm:grid-cols-2">
                            <label className="space-y-1 text-sm font-medium text-steel">
                              <span>Profile do poprawki</span>
                              <input
                                type="number"
                                min="0"
                                step="1"
                                value={draft.correctionProfilesQuantity}
                                onChange={(event) => updateDraft(draftKey, "correctionProfilesQuantity", event.target.value)}
                                className="w-full rounded-lg border border-line bg-white px-3 py-2 text-base font-semibold text-ink outline-none transition focus:border-accent"
                              />
                            </label>
                            <label className="space-y-1 text-sm font-medium text-steel">
                              <span>Akcesoria do poprawki</span>
                              <input
                                type="number"
                                min="0"
                                step="1"
                                value={draft.correctionAccessoriesQuantity}
                                onChange={(event) => updateDraft(draftKey, "correctionAccessoriesQuantity", event.target.value)}
                                className="w-full rounded-lg border border-line bg-white px-3 py-2 text-base font-semibold text-ink outline-none transition focus:border-accent"
                              />
                            </label>
                          </div>

                          <div className={["rounded-lg border px-3 py-2 text-sm font-semibold", balanceClasses(correctionSplitBalance.tone)].join(" ")}>
                            Podział poprawki: {correctionSplitBalance.text}
                          </div>

                          <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
                            <label className="space-y-1 text-sm font-medium text-steel">
                              <span>Powód poprawki</span>
                              <select
                                value={draft.correctionReasonCategory}
                                onChange={(event) => updateDraft(draftKey, "correctionReasonCategory", event.target.value)}
                                className="w-full rounded-lg border border-line bg-white px-3 py-2 text-sm text-ink outline-none transition focus:border-accent"
                              >
                                <option value="">Wybierz</option>
                                {correctionReasonOptions.map((option) => (
                                  <option key={option.value} value={option.value}>
                                    {option.label}
                                  </option>
                                ))}
                              </select>
                            </label>
                            {draft.correctionReasonCategory === "inne" ? (
                            <label className="space-y-1 text-sm font-medium text-steel">
                              <span>Notatka</span>
                              <input
                                type="text"
                                maxLength={500}
                                value={draft.correctionReasonNote}
                                onChange={(event) => updateDraft(draftKey, "correctionReasonNote", event.target.value)}
                                placeholder="Notatka"
                                className="w-full rounded-lg border border-line bg-white px-3 py-2 text-sm text-ink outline-none transition focus:border-accent"
                              />
                            </label>
                            ) : null}
                          </div>
                        </div>
                      ) : null}

                      <div className="space-y-2">
                        <button
                          type="button"
                          disabled={isSubmitting || !isDraftValid || !isPackingStage}
                          onClick={() => void handlePackingSubmit(workOrder)}
                          className="inline-flex w-full items-center justify-center rounded-lg bg-accent px-4 py-3 text-sm font-semibold text-white transition hover:bg-teal-700 disabled:cursor-not-allowed disabled:bg-teal-300"
                        >
                          {isSubmitting ? "Zapisywanie..." : getActionLabel(status)}
                        </button>
                        <button
                          type="button"
                          disabled={isSubmitting}
                          onClick={() => void handleReleasePacking(workOrder)}
                          className="inline-flex w-full items-center justify-center rounded-lg border border-line bg-white px-4 py-2 text-sm font-medium text-steel transition hover:border-accent hover:text-accent disabled:cursor-not-allowed disabled:text-slate-400"
                        >
                          Zwolnij stanowisko
                        </button>
                      </div>
                    </div>
                  ) : status === "DONE" ? (
                    <div className="flex h-full flex-col justify-center gap-3">
                      <p className="text-sm font-semibold text-emerald-700">{workOrder.counted_quantity ?? workOrder.planned_quantity} szt. zakończone</p>
                      <button
                        type="button"
                        disabled={isSubmitting}
                        onClick={() => void handleStageAction(workOrder)}
                        className="inline-flex w-full items-center justify-center rounded-lg border border-line bg-white px-4 py-3 text-sm font-semibold text-steel transition hover:border-accent hover:text-accent disabled:cursor-not-allowed disabled:border-line disabled:text-slate-400"
                      >
                        {isSubmitting ? "Zapisywanie..." : getActionLabel(status)}
                      </button>
                    </div>
                  ) : needsOverride ? (
                    <div className="flex h-full flex-col justify-center gap-3">
                      <p className="text-sm text-steel">Stanowisko pakowania jest zajęte.</p>
                      <button
                        type="button"
                        disabled={isSubmitting}
                        onClick={() => handleOverridePacking(workOrder, otherOccupants)}
                        className="inline-flex w-full items-center justify-center rounded-lg bg-accent px-4 py-3 text-sm font-semibold text-white transition hover:bg-teal-700 disabled:cursor-not-allowed disabled:bg-teal-300"
                      >
                        {isSubmitting ? "Zapisywanie..." : "Otwórz drugie stanowisko"}
                      </button>
                    </div>
                  ) : allSlotsFull ? (
                    <div className="flex h-full flex-col justify-center gap-3">
                      <span className="inline-flex w-fit rounded-full bg-amber-100 px-3 py-1 text-xs font-semibold text-amber-800">
                        Wszystkie stanowiska pakowania zajęte
                      </span>
                      <p className="text-sm text-steel">
                        Zajęte przez: {otherOccupants.map((occupant) => occupant.order_number).join(", ") || "—"}.
                        Zakończ jedno z nich, aby rozpocząć to.
                      </p>
                    </div>
                  ) : (
                    <div className="flex h-full flex-col justify-center gap-3">
                      <p className="text-sm text-steel">Policzono: {workOrder.counted_quantity ?? "-"}</p>
                      <button
                        type="button"
                        disabled={isSubmitting || !canStartFree}
                        onClick={() => void handleStartPacking(workOrder)}
                        className="inline-flex w-full items-center justify-center rounded-lg bg-accent px-4 py-3 text-sm font-semibold text-white transition hover:bg-teal-700 disabled:cursor-not-allowed disabled:bg-teal-300"
                      >
                        {isSubmitting ? "Zapisywanie..." : "Rozpocznij pakowanie"}
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
            <h2 className="text-3xl font-semibold text-ink sm:text-4xl">Pakowanie</h2>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-steel sm:text-base">
              Pakowanie, kontrola jakości i podgląd aktywnych automatów oczekujących na koniec zawieszania.
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
            Brak zleceń do pakowania
          </div>
        ) : (
          <div className="space-y-6">
            <div className="space-y-4">
              <div>
                <h3 className="text-lg font-semibold text-ink">Do wykonania</h3>
                <p className="mt-1 text-sm text-steel">Zlecenia do pakowania oraz automaty widoczne wcześniej jako oczekujące na koniec zawieszania.</p>
              </div>
              {activeWorkOrders.length === 0 ? (
                <div className="rounded-3xl border border-dashed border-line bg-mist px-6 py-12 text-center text-base text-steel">
                  Brak zleceń do pakowania
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
                    <p className="mt-1 text-sm text-steel">Zlecenia ukończone na etapie pakowania, dostępne do podglądu i cofnięcia.</p>
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