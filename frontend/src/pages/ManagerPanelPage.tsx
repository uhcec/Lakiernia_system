import { FormEvent, useEffect, useState } from "react";

import {
  assignWorkOrderPlan,
  fetchPlannedWorkOrders,
  fetchUnplannedWorkOrders,
  updateWorkOrderQueuePosition,
} from "../api/managerApi";
import type { ProductionTypeValue, WorkOrder } from "../types/workOrders";

interface PlanDraft {
  productionType: ProductionTypeValue;
  queuePosition: string;
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

function createQueueDrafts(workOrders: WorkOrder[]): Record<number, string> {
  return workOrders.reduce<Record<number, string>>((drafts, workOrder) => {
    drafts[workOrder.id] = workOrder.queue_position ? String(workOrder.queue_position) : "";
    return drafts;
  }, {});
}

export function ManagerPanelPage() {
  const [unplannedWorkOrders, setUnplannedWorkOrders] = useState<WorkOrder[]>([]);
  const [plannedWorkOrders, setPlannedWorkOrders] = useState<WorkOrder[]>([]);
  const [planDrafts, setPlanDrafts] = useState<Record<number, PlanDraft>>({});
  const [queueDrafts, setQueueDrafts] = useState<Record<number, string>>({});
  const [isLoading, setIsLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [planningWorkOrderId, setPlanningWorkOrderId] = useState<number | null>(null);
  const [updatingWorkOrderId, setUpdatingWorkOrderId] = useState<number | null>(null);

  async function loadManagerData() {
    setIsLoading(true);
    setErrorMessage(null);

    try {
      const [unplanned, planned] = await Promise.all([fetchUnplannedWorkOrders(), fetchPlannedWorkOrders()]);
      setUnplannedWorkOrders(unplanned);
      setPlannedWorkOrders(planned);
      setPlanDrafts(createPlanDrafts(unplanned));
      setQueueDrafts(createQueueDrafts(planned));
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Nie udało się pobrać panelu kierownika");
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    void loadManagerData();
  }, []);

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

  function updateQueueDraft(workOrderId: number, value: string) {
    setQueueDrafts((current) => ({
      ...current,
      [workOrderId]: value,
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
      setErrorMessage(error instanceof Error ? error.message : "Nie udało się zaplanować zlecenia");
    } finally {
      setPlanningWorkOrderId(null);
    }
  }

  async function handleQueueUpdate(workOrderId: number) {
    const parsedQueuePosition = Number(queueDrafts[workOrderId]);

    if (!Number.isInteger(parsedQueuePosition) || parsedQueuePosition < 1) {
      setSuccessMessage(null);
      setErrorMessage("Pozycja w kolejce musi być liczbą większą lub równą 1");
      return;
    }

    setUpdatingWorkOrderId(workOrderId);
    setErrorMessage(null);
    setSuccessMessage(null);

    try {
      await updateWorkOrderQueuePosition(workOrderId, { queue_position: parsedQueuePosition });
      await loadManagerData();
      setSuccessMessage("Kolejność została zaktualizowana");
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Nie udało się zmienić kolejności");
    } finally {
      setUpdatingWorkOrderId(null);
    }
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
          </div>
          <div className="rounded-2xl border border-line bg-mist px-4 py-3 text-sm text-steel">
            Do zaplanowania: <span className="font-semibold text-ink">{unplannedWorkOrders.length}</span>
            <span className="mx-2 text-line">|</span>
            Zaplanowane: <span className="font-semibold text-ink">{plannedWorkOrders.length}</span>
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
          ) : unplannedWorkOrders.length === 0 ? (
            <div className="rounded-3xl border border-dashed border-line bg-mist px-6 py-12 text-center text-base text-steel">
              Wszystkie zlecenia są już zaplanowane
            </div>
          ) : (
            <div className="space-y-4">
              {unplannedWorkOrders.map((workOrder) => {
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
                        <h4 className="mt-2 text-lg font-semibold text-ink">{workOrder.title}</h4>
                        <p className="mt-1 text-sm text-steel">{workOrder.customer_name || "Brak firmy"}</p>
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
          ) : plannedWorkOrders.length === 0 ? (
            <div className="rounded-3xl border border-dashed border-line bg-mist px-6 py-12 text-center text-base text-steel">
              Brak zaplanowanych zleceń
            </div>
          ) : (
            <div className="overflow-hidden rounded-3xl border border-line bg-white shadow-panel">
              <div className="overflow-x-auto">
                <table className="min-w-full border-collapse text-left text-sm">
                  <thead className="bg-mist text-steel">
                    <tr>
                      <th className="px-5 py-4 font-semibold">Pozycja</th>
                      <th className="px-5 py-4 font-semibold">Numer</th>
                      <th className="px-5 py-4 font-semibold">Tytuł</th>
                      <th className="px-5 py-4 font-semibold">Firma</th>
                      <th className="px-5 py-4 font-semibold">Typ produkcji</th>
                      <th className="px-5 py-4 font-semibold text-right">Akcja</th>
                    </tr>
                  </thead>
                  <tbody>
                    {plannedWorkOrders.map((workOrder) => {
                      const isSubmitting = updatingWorkOrderId === workOrder.id;

                      return (
                        <tr key={workOrder.id} className="border-t border-line/80 text-ink">
                          <td className="px-5 py-4">
                            <input
                              type="number"
                              min={1}
                              value={queueDrafts[workOrder.id] ?? ""}
                              onChange={(event) => updateQueueDraft(workOrder.id, event.target.value)}
                              className="w-24 rounded-2xl border border-line bg-white px-3 py-2 text-sm text-ink outline-none transition focus:border-accent"
                            />
                          </td>
                          <td className="px-5 py-4 font-semibold">{workOrder.order_number}</td>
                          <td className="px-5 py-4">{workOrder.title}</td>
                          <td className="px-5 py-4 text-steel">{workOrder.customer_name || "-"}</td>
                          <td className="px-5 py-4 text-steel">{getProductionTypeLabel(workOrder.production_type?.value)}</td>
                          <td className="px-5 py-4 text-right">
                            <button
                              type="button"
                              disabled={isSubmitting}
                              onClick={() => void handleQueueUpdate(workOrder.id)}
                              className="inline-flex items-center justify-center rounded-full border border-line bg-white px-4 py-2 text-sm font-medium text-steel transition hover:border-accent hover:text-accent disabled:cursor-not-allowed disabled:border-line disabled:text-slate-400"
                            >
                              {isSubmitting ? "Zapisywanie..." : "Zmień kolejność"}
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      </section>
    </main>
  );
}