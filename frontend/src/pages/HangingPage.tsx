import { useEffect, useRef, useState } from "react";

import { buildWorkOrderDetailHref, getStationIdForLocation } from "../api/stationContext";
import { fetchStageWorkOrders, transitionStage } from "../api/processApi";
import { RalColorDot } from "../components/RalColorDot";
import { StationPresenceWidget } from "../components/StationPresenceWidget";
import { usePolling, STATION_POLL_INTERVAL_MS } from "../hooks/usePolling";
import type { StageWorkOrder } from "../types/process";
import { groupHangingQueue } from "../utils/hangingGroups";
import { getLoadErrorMessage } from "../utils/loadError";
import { getMutationErrorMessage } from "../utils/mutationError";
import { badgeClasses, formatDisplayOrderNumber, type DisplayBadge } from "../utils/workOrderDisplay";

// CHANGES #27 (owner 2026-10-15): the hanging station is a compact list grouped by paint (whiteboard
// sketch): header "RAL · producent · kod farby", one row per order "firma · m² · numer · sztuki". Groups
// follow the manager's queue. Drawings, attachments and the correction description live behind
// "Szczegóły"; finished orders sit folded at the bottom with "Cofnij".

const HANGING_BUSY_LABEL = "Zawieszanie zajęte";

function rowKey(workOrder: StageWorkOrder): string {
  return `${workOrder.id}-${workOrder.batch_id ?? workOrder.id}`;
}

function isCorrection(workOrder: StageWorkOrder): boolean {
  // A correction child and a same-order correction round both read as a correction (FRONTEND_TRIAGE C3).
  return workOrder.is_correction || workOrder.is_correction_round;
}

function getRowBadges(workOrder: StageWorkOrder): DisplayBadge[] {
  const badges: DisplayBadge[] = [];
  if (isCorrection(workOrder)) {
    badges.push({ label: "POPRAWKA", tone: "warning" });
  }
  if (workOrder.batch_is_partial) {
    badges.push({ label: "NIEPEŁNE", tone: "warning" });
  }
  if (workOrder.work_order_kind.value === "PRZEMALOWANKA") {
    badges.push({ label: "PRZEMALOWANKA", tone: "danger" });
  }
  if (workOrder.is_ocynk) {
    badges.push({ label: "OCYNK", tone: "info" });
  }
  if (workOrder.coating_type.value === "DECORAL") {
    badges.push({ label: "DECORAL", tone: "accent" });
  }
  return badges;
}

function formatArea(value: number | null): string {
  return typeof value === "number" ? `${value} m²` : "- m²";
}

export function HangingPage() {
  const detailStationId = getStationIdForLocation(window.location.pathname, window.location.search);
  const [workOrders, setWorkOrders] = useState<StageWorkOrder[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  // CHANGES #16b: only the latest load may apply state, so a slow reload never shows older data.
  const loadRequestSequenceRef = useRef(0);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [activeRowKey, setActiveRowKey] = useState<string | null>(null);
  const [showCompleted, setShowCompleted] = useState(false);

  const activeWorkOrders = workOrders.filter((workOrder) => workOrder.stage_status.status.value !== "DONE");
  const completedWorkOrders = workOrders.filter((workOrder) => workOrder.stage_status.status.value === "DONE");
  const groups = groupHangingQueue(activeWorkOrders);
  // Hanging holds one order at a time (`app/process/resource_locks.py:97-112`); the backend still refuses
  // a second start, the grey button only says so up front.
  const isHangingBusy = activeWorkOrders.some((workOrder) => workOrder.stage_status.status.value === "IN_PROGRESS");

  async function loadWorkOrders(options?: { preserveErrorMessage?: boolean; background?: boolean }): Promise<boolean> {
    const background = options?.background ?? false;
    const requestId = ++loadRequestSequenceRef.current;
    if (!background) {
      setIsLoading(true);
      if (!options?.preserveErrorMessage) {
        setErrorMessage(null);
      }
    }

    try {
      const items = await fetchStageWorkOrders("HANGING");
      if (requestId !== loadRequestSequenceRef.current) {
        return false;
      }
      setWorkOrders(items);
      return true;
    } catch (error) {
      if (!background && requestId === loadRequestSequenceRef.current) {
        setErrorMessage(getLoadErrorMessage(error, "Nie udało się pobrać zleceń"));
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

  // Paused while an action is in flight to avoid clobbering optimistic state.
  usePolling(
    () => {
      void loadWorkOrders({ background: true });
    },
    STATION_POLL_INTERVAL_MS,
    activeRowKey === null,
  );

  async function handleAction(workOrder: StageWorkOrder, action: "start" | "finish" | "reopen") {
    setActiveRowKey(rowKey(workOrder));
    setErrorMessage(null);
    try {
      await transitionStage(workOrder.id, "HANGING", action, workOrder.batch_id ?? undefined);
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
      setActiveRowKey(null);
    }
  }

  function renderRow(workOrder: StageWorkOrder, withDivider: boolean) {
    const status = workOrder.stage_status.status.value;
    const isInProgress = status === "IN_PROGRESS";
    const isDone = status === "DONE";
    const isSubmitting = activeRowKey === rowKey(workOrder);
    const isBlockedByOtherOrder = status === "NOT_STARTED" && isHangingBusy;
    const action = isDone ? "reopen" : isInProgress ? "finish" : "start";
    const actionLabel = isDone ? "Cofnij" : isInProgress ? "Zakończ" : "Rozpocznij";

    return (
      <li
        key={rowKey(workOrder)}
        className={[
          "flex flex-col gap-3 px-4 py-4 sm:flex-row sm:items-center sm:justify-between sm:px-5",
          withDivider ? "border-t border-dashed border-line" : "",
          isInProgress
            ? "bg-emerald-50 ring-2 ring-inset ring-emerald-400"
            : isCorrection(workOrder)
              ? "bg-amber-50/60"
              : "",
        ].join(" ")}
      >
        <div className="min-w-0 space-y-1">
          <p className="flex flex-wrap items-baseline gap-x-2 text-base text-ink sm:text-lg">
            <span className="font-semibold">{workOrder.customer_name || "Brak firmy"}</span>
            <span className="text-steel">·</span>
            <span>{formatArea(workOrder.total_area_m2)}</span>
            <span className="text-steel">·</span>
            <span className="font-semibold">{formatDisplayOrderNumber(workOrder)}</span>
            <span className="text-steel">·</span>
            <span>{workOrder.operational_quantity} szt.</span>
          </p>
          <div className="flex flex-wrap items-center gap-2">
            {isInProgress ? (
              <span className="inline-flex rounded-full bg-emerald-100 px-2 py-1 text-[11px] font-semibold text-emerald-700">
                W TRAKCIE
              </span>
            ) : null}
            {getRowBadges(workOrder).map((badge) => (
              <span
                key={badge.label}
                className={["inline-flex rounded-full px-2 py-1 text-[11px] font-semibold", badgeClasses(badge.tone)].join(" ")}
              >
                {badge.label}
              </span>
            ))}
          </div>
        </div>

        <div className="flex shrink-0 items-center gap-4">
          <a
            href={buildWorkOrderDetailHref(workOrder.id, detailStationId)}
            className="text-sm font-medium text-accent transition hover:text-teal-700"
          >
            Szczegóły
          </a>
          <div className="flex flex-col items-end gap-1">
            <button
              type="button"
              disabled={isSubmitting || isBlockedByOtherOrder}
              onClick={() => void handleAction(workOrder, action)}
              className={[
                "inline-flex min-w-[8.5rem] items-center justify-center rounded-lg border px-4 py-3 text-sm font-semibold transition disabled:cursor-not-allowed",
                isInProgress
                  ? "border-emerald-600 bg-emerald-600 text-white hover:bg-emerald-700 disabled:opacity-60"
                  : "border-line bg-white text-steel hover:border-accent hover:text-accent disabled:border-line disabled:bg-mist disabled:text-slate-400",
              ].join(" ")}
            >
              {isSubmitting ? "Zapisywanie..." : actionLabel}
            </button>
            {isBlockedByOtherOrder ? <span className="text-xs text-steel">{HANGING_BUSY_LABEL}</span> : null}
          </div>
        </div>
      </li>
    );
  }

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-7xl flex-col gap-6 px-4 py-8 sm:px-6 lg:px-8">
      <StationPresenceWidget />
      <section className="rounded-[2rem] border border-white/70 bg-white/80 p-6 shadow-panel backdrop-blur sm:p-8">
        <p className="text-sm font-semibold uppercase tracking-[0.18em] text-accent">Widok etapu</p>
        <h2 className="text-3xl font-semibold text-ink sm:text-4xl">Zawieszanie</h2>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-steel sm:text-base">
          Zlecenia w kolejności kierownika, pogrupowane po farbie.
        </p>
      </section>

      {errorMessage ? (
        <section className="rounded-2xl border border-rose-200 bg-rose-50 px-5 py-4 text-sm text-rose-700">{errorMessage}</section>
      ) : null}

      <section className="space-y-4">
        {isLoading ? (
          <div className="rounded-3xl border border-dashed border-line bg-mist px-6 py-12 text-center text-base text-steel">
            Ładowanie...
          </div>
        ) : groups.length === 0 ? (
          <div className="rounded-3xl border border-dashed border-line bg-mist px-6 py-12 text-center text-base text-steel">
            Brak zleceń do zawieszania
          </div>
        ) : (
          groups.map((group) => (
            <article key={group.key} className="overflow-hidden rounded-2xl border-2 border-ink/70 bg-white shadow-sm">
              <header className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b-2 border-ink/70 bg-mist px-4 py-3 text-lg font-semibold text-ink sm:px-5">
                <RalColorDot ralCode={group.ralCode} />
                <span>{group.ralCode}</span>
                <span className="text-steel">·</span>
                <span>{group.paintProducer}</span>
                <span className="text-steel">·</span>
                <span>{group.paintCode ?? "brak kodu farby"}</span>
              </header>
              <ul>{group.workOrders.map((workOrder, index) => renderRow(workOrder, index > 0))}</ul>
            </article>
          ))
        )}
      </section>

      {completedWorkOrders.length > 0 ? (
        <section className="rounded-2xl border border-line/80 bg-mist/50">
          <button
            type="button"
            onClick={() => setShowCompleted((current) => !current)}
            className="flex w-full items-center justify-between px-5 py-4 text-left"
          >
            <span className="text-lg font-semibold text-ink">
              {showCompleted ? "▾" : "▸"} Zakończone ({completedWorkOrders.length})
            </span>
            <span className="text-sm font-medium text-steel">{showCompleted ? "Ukryj" : "Pokaż"}</span>
          </button>
          {showCompleted ? (
            <ul className="border-t border-line/80 bg-white">
              {completedWorkOrders.map((workOrder, index) => renderRow(workOrder, index > 0))}
            </ul>
          ) : null}
        </section>
      ) : null}
    </main>
  );
}
