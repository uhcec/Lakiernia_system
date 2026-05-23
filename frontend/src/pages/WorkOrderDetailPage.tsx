import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { fetchWorkOrder } from "../api/workOrdersApi";
import type { WorkOrder } from "../types/workOrders";

function formatDate(value: string | null): string {
  if (!value) {
    return "-";
  }

  return new Intl.DateTimeFormat("pl-PL").format(new Date(value));
}

export function WorkOrderDetailPage() {
  const { id } = useParams();
  const [workOrder, setWorkOrder] = useState<WorkOrder | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    let isActive = true;

    async function loadWorkOrder() {
      if (!id) {
        setErrorMessage("Nieprawidłowy identyfikator zlecenia");
        setIsLoading(false);
        return;
      }

      setIsLoading(true);
      setErrorMessage(null);

      try {
        const item = await fetchWorkOrder(Number(id));
        if (!isActive) {
          return;
        }
        setWorkOrder(item);
      } catch (error) {
        if (!isActive) {
          return;
        }
        setErrorMessage(error instanceof Error ? error.message : "Nie udało się pobrać zlecenia");
      } finally {
        if (isActive) {
          setIsLoading(false);
        }
      }
    }

    void loadWorkOrder();

    return () => {
      isActive = false;
    };
  }, [id]);

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-7xl flex-col gap-6 px-4 py-8 sm:px-6 lg:px-8">
      <section className="rounded-[2rem] border border-white/70 bg-white/80 p-6 shadow-panel backdrop-blur sm:p-8">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div className="space-y-2">
            <p className="text-sm font-semibold uppercase tracking-[0.18em] text-accent">Szczegóły zlecenia</p>
            <div>
              <h2 className="text-3xl font-semibold text-ink sm:text-4xl">{workOrder?.title ?? "Zlecenie"}</h2>
              <p className="mt-2 max-w-3xl text-sm leading-6 text-steel sm:text-base">
                Podgląd danych biurowych, planowania i aktualnych etapów procesu bez możliwości edycji.
              </p>
            </div>
          </div>
          <Link
            to="/zlecenia"
            className="inline-flex items-center justify-center rounded-full border border-line bg-white px-5 py-3 text-sm font-medium text-steel transition hover:border-accent hover:text-accent"
          >
            Wróć do listy
          </Link>
        </div>
      </section>

      {isLoading ? (
        <section className="rounded-[2rem] border border-white/70 bg-white/80 px-6 py-12 text-center text-base text-steel shadow-panel backdrop-blur">
          Ładowanie...
        </section>
      ) : errorMessage ? (
        <section className="rounded-[2rem] border border-rose-200 bg-rose-50 px-6 py-12 text-center text-base text-rose-700 shadow-panel">
          {errorMessage}
        </section>
      ) : workOrder ? (
        <>
          <section className="grid gap-6 lg:grid-cols-[1.5fr_1fr]">
            <div className="rounded-[2rem] border border-white/70 bg-white/80 p-6 shadow-panel backdrop-blur sm:p-8">
              <h3 className="text-2xl font-semibold text-ink">Dane zlecenia</h3>
              <dl className="mt-6 grid gap-5 md:grid-cols-2">
                <div>
                  <dt className="text-sm font-medium text-steel">Nr zlecenia</dt>
                  <dd className="mt-1 text-base font-semibold text-ink">{workOrder.order_number}</dd>
                </div>
                <div>
                  <dt className="text-sm font-medium text-steel">Tytuł</dt>
                  <dd className="mt-1 text-base font-semibold text-ink">{workOrder.title}</dd>
                </div>
                <div>
                  <dt className="text-sm font-medium text-steel">Firma</dt>
                  <dd className="mt-1 text-base text-ink">{workOrder.customer_name || "-"}</dd>
                </div>
                <div>
                  <dt className="text-sm font-medium text-steel">Technologia</dt>
                  <dd className="mt-1 text-base text-ink">{workOrder.coating_type.label}</dd>
                </div>
                <div>
                  <dt className="text-sm font-medium text-steel">Termin</dt>
                  <dd className="mt-1 text-base text-ink">{formatDate(workOrder.due_date)}</dd>
                </div>
                <div className="md:col-span-2">
                  <dt className="text-sm font-medium text-steel">Uwagi</dt>
                  <dd className="mt-1 whitespace-pre-wrap text-base text-ink">{workOrder.notes || "-"}</dd>
                </div>
              </dl>
            </div>

            <div className="space-y-6">
              <section className="rounded-[2rem] border border-white/70 bg-white/80 p-6 shadow-panel backdrop-blur sm:p-8">
                <h3 className="text-2xl font-semibold text-ink">Planowanie</h3>
                <dl className="mt-6 space-y-5">
                  <div>
                    <dt className="text-sm font-medium text-steel">Typ produkcji</dt>
                    <dd className="mt-1 text-base text-ink">{workOrder.production_type?.label ?? "-"}</dd>
                  </div>
                  <div>
                    <dt className="text-sm font-medium text-steel">Pozycja w kolejce</dt>
                    <dd className="mt-1 text-base text-ink">{workOrder.queue_position ?? "-"}</dd>
                  </div>
                </dl>
              </section>

              <section className="rounded-[2rem] border border-white/70 bg-white/80 p-6 shadow-panel backdrop-blur sm:p-8">
                <h3 className="text-2xl font-semibold text-ink">Status procesu</h3>
                <div className="mt-6 inline-flex rounded-full bg-mist px-4 py-2 text-sm font-semibold text-ink">
                  {workOrder.process_status.label}
                </div>
              </section>
            </div>
          </section>

          <section className="rounded-[2rem] border border-white/70 bg-white/80 p-6 shadow-panel backdrop-blur sm:p-8">
            <h3 className="text-2xl font-semibold text-ink">Etapy</h3>
            <div className="mt-6 space-y-4">
              {workOrder.stage_states.map((stageState) => (
                <div key={stageState.stage.value} className="flex flex-col gap-3 rounded-3xl border border-line/80 bg-white p-5 sm:flex-row sm:items-center sm:justify-between">
                  <div>
                    <p className="text-base font-semibold text-ink">{stageState.stage.label}</p>
                  </div>
                  <span className="inline-flex w-fit rounded-full bg-mist px-3 py-1 text-xs font-semibold text-ink">
                    {stageState.status.label}
                  </span>
                </div>
              ))}
            </div>
          </section>
        </>
      ) : null}
    </main>
  );
}