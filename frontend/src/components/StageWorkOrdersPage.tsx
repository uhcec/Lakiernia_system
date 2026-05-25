import { useEffect, useState } from "react";

import { fetchStageWorkOrders, transitionStage } from "../api/processApi";
import type { ProcessStageValue, StageWorkOrder, StageStatusValue } from "../types/process";
import type { ProductionTypeValue } from "../types/workOrders";

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
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [activeWorkOrderId, setActiveWorkOrderId] = useState<number | null>(null);
  const [showCompleted, setShowCompleted] = useState(false);

  const activeWorkOrders = workOrders.filter((workOrder) => workOrder.stage_status.status.value !== "DONE");
  const completedWorkOrders = workOrders.filter((workOrder) => workOrder.stage_status.status.value === "DONE");

  async function loadWorkOrders() {
    setIsLoading(true);
    setErrorMessage(null);

    try {
      const items = await fetchStageWorkOrders(stage, productionType);
      setWorkOrders(items);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Nie udało się pobrać zleceń");
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    void loadWorkOrders();
  }, [stage, productionType]);

  async function handleAction(workOrder: StageWorkOrder) {
    setActiveWorkOrderId(workOrder.id);
    setErrorMessage(null);

    try {
      await transitionStage(workOrder.id, stage, getStageAction(workOrder.stage_status.status.value), workOrder.batch_id ?? undefined);
      await loadWorkOrders();
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Nie udało się zmienić statusu");
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
                <th className="px-5 py-4 font-semibold">Tytuł</th>
                <th className="px-5 py-4 font-semibold">Firma</th>
                <th className="px-5 py-4 font-semibold">Partia</th>
                <th className="px-5 py-4 font-semibold">Ilość</th>
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
                const rowKey = `${workOrder.id}-${workOrder.batch_id ?? workOrder.id}-${stage}`;

                return (
                  <tr key={rowKey} className="border-t border-line/80 text-ink">
                    <td className="px-5 py-4 font-semibold">{workOrder.queue_position ?? "-"}</td>
                    <td className="px-5 py-4 font-semibold">{workOrder.order_number}</td>
                    <td className="px-5 py-4">{workOrder.title}</td>
                    <td className="px-5 py-4 text-steel">{workOrder.customer_name || "-"}</td>
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
                    <td className="px-5 py-4 font-semibold">{workOrder.batch_quantity ?? workOrder.current_active_quantity}</td>
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
                          disabled={isSubmitting}
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
          </div>
        </div>
      </section>

      {errorMessage ? (
        <section className="rounded-2xl border border-rose-200 bg-rose-50 px-5 py-4 text-sm text-rose-700">{errorMessage}</section>
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