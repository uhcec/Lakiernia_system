import { useEffect, useState } from "react";

import { completePacking, fetchStageWorkOrders, transitionStage } from "../api/processApi";
import type { StageWorkOrder, StageStatusValue } from "../types/process";
import { formatWorkOrderPrimaryInfo } from "../utils/workOrderDisplay";

interface PackingDraft {
  countedQuantity: string;
  okQuantity: string;
  correctionQuantity: string;
}

function getActionLabel(status: StageStatusValue): string {
  switch (status) {
    case "NOT_STARTED":
      return "Rozpocznij";
    case "DONE":
      return "Cofnij";
    case "IN_PROGRESS":
      return "Zatwierdź pakowanie";
  }
}

function parseQuantity(value: string): number {
  if (value.trim() === "") {
    return 0;
  }

  return Number(value);
}

function formatDifference(difference: number): string {
  return difference > 0 ? `+${difference}` : String(difference);
}

export function PackingWorkOrdersPage() {
  const [workOrders, setWorkOrders] = useState<StageWorkOrder[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [activeWorkOrderId, setActiveWorkOrderId] = useState<number | null>(null);
  const [showCompleted, setShowCompleted] = useState(false);
  const [drafts, setDrafts] = useState<Record<number, PackingDraft>>({});

  function getDraftKey(workOrder: StageWorkOrder): number {
    return workOrder.batch_id ?? workOrder.id;
  }

  const activeWorkOrders = workOrders.filter((workOrder) => workOrder.stage_status.status.value !== "DONE");
  const completedWorkOrders = workOrders.filter((workOrder) => workOrder.stage_status.status.value === "DONE");

  async function loadWorkOrders() {
    setIsLoading(true);
    setErrorMessage(null);

    try {
      const items = await fetchStageWorkOrders("PACKING");
      setWorkOrders(items);
      setDrafts((current) => {
        const nextDrafts = { ...current };
        for (const item of items) {
          const draftKey = getDraftKey(item);
          const existingDraft = nextDrafts[draftKey];
          if (!existingDraft) {
            nextDrafts[draftKey] = {
              countedQuantity: item.counted_quantity?.toString() ?? "",
              okQuantity: String(item.counted_quantity ?? item.current_active_quantity),
              correctionQuantity: "0",
            };
          }
        }
        return nextDrafts;
      });
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Nie udało się pobrać zleceń do pakowania");
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    void loadWorkOrders();
  }, []);

  function updateDraft(workOrderId: number, fieldName: keyof PackingDraft, value: string) {
    setDrafts((current) => ({
      ...current,
      [workOrderId]: {
        ...(current[workOrderId] ?? { countedQuantity: "", okQuantity: "0", correctionQuantity: "0" }),
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
      setErrorMessage(error instanceof Error ? error.message : "Nie udało się zmienić statusu pakowania");
    } finally {
      setActiveWorkOrderId(null);
    }
  }

  async function handlePackingSubmit(workOrder: StageWorkOrder) {
    const draftKey = getDraftKey(workOrder);
    const draft = drafts[draftKey] ?? { countedQuantity: "", okQuantity: "0", correctionQuantity: "0" };
    const countedQuantity = parseQuantity(draft.countedQuantity);
    const okQuantity = parseQuantity(draft.okQuantity);
    const correctionQuantity = parseQuantity(draft.correctionQuantity);

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

    if (okQuantity + correctionQuantity !== countedQuantity) {
      setErrorMessage("Suma ilości OK i do poprawki musi być równa wartości Policzono");
      return;
    }

    setActiveWorkOrderId(draftKey);
    setErrorMessage(null);

    try {
      await completePacking(
        workOrder.id,
        {
          counted_quantity: countedQuantity,
          ok_quantity: okQuantity,
          correction_quantity: correctionQuantity,
        },
        workOrder.batch_id ?? undefined,
      );
      await loadWorkOrders();
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Nie udało się zatwierdzić pakowania");
    } finally {
      setActiveWorkOrderId(null);
    }
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
                <th className="px-5 py-4 font-semibold">Plan</th>
                <th className="px-5 py-4 font-semibold">Policzono</th>
                <th className="px-5 py-4 font-semibold">Różnica</th>
                <th className="px-5 py-4 font-semibold">OK</th>
                <th className="px-5 py-4 font-semibold">Poprawki</th>
                <th className="px-5 py-4 font-semibold">Status etapu</th>
                <th className="px-5 py-4 font-semibold text-right">Akcje</th>
              </tr>
            </thead>
            <tbody>
              {items.map((workOrder) => {
                const status = workOrder.stage_status.status.value;
                const draftKey = getDraftKey(workOrder);
                const isSubmitting = activeWorkOrderId === draftKey;
                const draft = drafts[draftKey] ?? { countedQuantity: "", okQuantity: "0", correctionQuantity: "0" };
                const countedQuantity = parseQuantity(draft.countedQuantity);
                const okQuantity = parseQuantity(draft.okQuantity);
                const correctionQuantity = parseQuantity(draft.correctionQuantity);
                const difference =
                  Number.isInteger(countedQuantity) && countedQuantity > 0
                    ? countedQuantity - workOrder.planned_quantity
                    : null;
                const isDraftValid =
                  Number.isInteger(countedQuantity) &&
                  countedQuantity > 0 &&
                  Number.isInteger(okQuantity) &&
                  Number.isInteger(correctionQuantity) &&
                  okQuantity >= 0 &&
                  correctionQuantity >= 0 &&
                  okQuantity + correctionQuantity === countedQuantity;

                return (
                  <tr key={`${workOrder.id}-${draftKey}`} className="border-t border-line/80 text-ink align-top">
                    <td className="px-5 py-4 font-semibold">{workOrder.queue_position ?? "-"}</td>
                    <td className="px-5 py-4 font-semibold">{workOrder.order_number}</td>
                    <td className="px-5 py-4 text-steel">{formatWorkOrderPrimaryInfo(workOrder)}</td>
                    <td className="px-5 py-4 font-semibold">{workOrder.planned_quantity}</td>
                    <td className="px-5 py-4">
                      {status === "IN_PROGRESS" ? (
                        <input
                          type="number"
                          min="1"
                          step="1"
                          value={draft.countedQuantity}
                          onChange={(event) => updateDraft(draftKey, "countedQuantity", event.target.value)}
                          className="w-24 rounded-2xl border border-line bg-white px-3 py-2 text-sm text-ink outline-none transition focus:border-accent"
                        />
                      ) : (
                        <span className="font-semibold text-ink">{workOrder.counted_quantity ?? "-"}</span>
                      )}
                    </td>
                    <td className="px-5 py-4">
                      {difference === null ? (
                        <span className="text-steel">-</span>
                      ) : difference === 0 ? (
                        <span className="font-medium text-emerald-700">Brak różnicy</span>
                      ) : (
                        <span className="font-medium text-amber-700">Różnica: {formatDifference(difference)} szt.</span>
                      )}
                    </td>
                    <td className="px-5 py-4">
                      {status === "IN_PROGRESS" ? (
                        <input
                          type="number"
                          min="0"
                          step="1"
                          value={draft.okQuantity}
                          onChange={(event) => updateDraft(draftKey, "okQuantity", event.target.value)}
                          className="w-24 rounded-2xl border border-line bg-white px-3 py-2 text-sm text-ink outline-none transition focus:border-accent"
                        />
                      ) : (
                        <span className="text-steel">-</span>
                      )}
                    </td>
                    <td className="px-5 py-4">
                      {status === "IN_PROGRESS" ? (
                        <input
                          type="number"
                          min="0"
                          step="1"
                          value={draft.correctionQuantity}
                          onChange={(event) => updateDraft(draftKey, "correctionQuantity", event.target.value)}
                          className="w-24 rounded-2xl border border-line bg-white px-3 py-2 text-sm text-ink outline-none transition focus:border-accent"
                        />
                      ) : (
                        <span className="text-steel">-</span>
                      )}
                    </td>
                    <td className="px-5 py-4">
                      <span className="inline-flex rounded-full bg-mist px-3 py-1 text-xs font-semibold text-ink">
                        {workOrder.stage_status.status.label}
                      </span>
                    </td>
                    <td className="px-5 py-4">
                      {status === "IN_PROGRESS" ? (
                        <div className="flex min-w-[20rem] flex-col items-end gap-3">
                          <p className="text-xs text-steel">
                            Plan: {workOrder.planned_quantity}. Zatwierdzenie jest dostępne dopiero, gdy OK + poprawki = Policzono.
                          </p>
                          <button
                            type="button"
                            disabled={isSubmitting || !isDraftValid}
                            onClick={() => void handlePackingSubmit(workOrder)}
                            className="inline-flex items-center justify-center rounded-full bg-accent px-4 py-2 text-sm font-medium text-white transition hover:bg-teal-700 disabled:cursor-not-allowed disabled:bg-teal-300"
                          >
                            {isSubmitting ? "Zapisywanie..." : getActionLabel(status)}
                          </button>
                        </div>
                      ) : (
                        <div className="flex justify-end">
                          <button
                            type="button"
                            disabled={isSubmitting}
                            onClick={() => void handleStageAction(workOrder)}
                            className="inline-flex items-center justify-center rounded-full border border-line bg-white px-4 py-2 text-sm font-medium text-steel transition hover:border-accent hover:text-accent disabled:cursor-not-allowed disabled:border-line disabled:text-slate-400"
                          >
                            {isSubmitting ? "Zapisywanie..." : getActionLabel(status)}
                          </button>
                        </div>
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
            <h2 className="text-3xl font-semibold text-ink sm:text-4xl">Pakowanie</h2>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-steel sm:text-base">
              Najpierw potwierdź policzoną ilość, potem rozdziel ją na OK i poprawki. Korekta wraca do produkcji jako nowa aktywna partia.
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
            Brak zleceń do pakowania
          </div>
        ) : (
          <div className="space-y-6">
            <div className="space-y-4">
              <div>
                <h3 className="text-lg font-semibold text-ink">Do wykonania</h3>
                <p className="mt-1 text-sm text-steel">Uruchom pakowanie, wpisz ilość policzoną i dopiero wtedy rozdziel partię na OK i poprawki.</p>
              </div>
              {activeWorkOrders.length === 0 ? (
                <div className="rounded-3xl border border-dashed border-line bg-mist px-6 py-12 text-center text-base text-steel">
                  Brak zleceń do pakowania
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

                {showCompleted ? renderWorkOrdersTable(completedWorkOrders) : null}
              </div>
            ) : null}
          </div>
        )}
      </section>
    </main>
  );
}