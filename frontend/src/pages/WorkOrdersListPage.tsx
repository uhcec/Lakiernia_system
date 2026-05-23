import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { fetchWorkOrders } from "../api/workOrdersApi";
import { WorkOrdersTable } from "../components/WorkOrdersTable";
import type { WorkOrder } from "../types/workOrders";

export function WorkOrdersListPage() {
  const [workOrders, setWorkOrders] = useState<WorkOrder[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    let isActive = true;

    async function loadWorkOrders() {
      setIsLoading(true);
      setErrorMessage(null);

      try {
        const response = await fetchWorkOrders();
        if (!isActive) {
          return;
        }
        setWorkOrders(response.items);
      } catch (error) {
        if (!isActive) {
          return;
        }
        setErrorMessage(error instanceof Error ? error.message : "Nie udało się pobrać zleceń");
      } finally {
        if (isActive) {
          setIsLoading(false);
        }
      }
    }

    loadWorkOrders();

    return () => {
      isActive = false;
    };
  }, []);

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-7xl flex-col gap-6 px-4 py-8 sm:px-6 lg:px-8">
      <section className="rounded-[2rem] border border-white/70 bg-white/80 p-6 shadow-panel backdrop-blur sm:p-8">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div className="space-y-2">
            <p className="text-sm font-semibold uppercase tracking-[0.18em] text-accent">Panel operacyjny</p>
            <div>
              <h1 className="text-3xl font-semibold text-ink sm:text-4xl">Zlecenia</h1>
              <p className="mt-2 max-w-2xl text-sm leading-6 text-steel sm:text-base">
                Lista aktywnych zleceń roboczych z bieżącym statusem procesu. Widok jest przygotowany pod szybkie użycie
                na stanowisku biurowym i na tablecie.
              </p>
            </div>
          </div>
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
            <div className="rounded-2xl border border-line bg-mist px-4 py-3 text-sm text-steel">
              Widocznych rekordów: <span className="font-semibold text-ink">{workOrders.length}</span>
            </div>
            <Link
              to="/zlecenia/nowe"
              className="inline-flex items-center justify-center rounded-full bg-accent px-5 py-3 text-sm font-medium text-white transition hover:bg-teal-700"
            >
              Dodaj zlecenie
            </Link>
          </div>
        </div>
      </section>

      <section className="space-y-4 rounded-[2rem] border border-white/70 bg-white/80 p-6 shadow-panel backdrop-blur sm:p-8">
        <div>
          <h2 className="text-lg font-semibold text-ink">Lista zleceń</h2>
          <p className="mt-1 text-sm text-steel">Status procesu i etapy pozostają jedynym aktywnym źródłem informacji o workflow.</p>
        </div>

        {isLoading ? (
          <div className="rounded-3xl border border-dashed border-line bg-mist px-6 py-12 text-center text-base text-steel">
            Ładowanie...
          </div>
        ) : errorMessage ? (
          <div className="rounded-3xl border border-rose-200 bg-rose-50 px-6 py-12 text-center text-base text-rose-700">
            {errorMessage}
          </div>
        ) : workOrders.length === 0 ? (
          <div className="rounded-3xl border border-dashed border-line bg-mist px-6 py-12 text-center text-base text-steel">
            Brak zleceń
          </div>
        ) : (
          <WorkOrdersTable workOrders={workOrders} />
        )}
      </section>
    </main>
  );
}