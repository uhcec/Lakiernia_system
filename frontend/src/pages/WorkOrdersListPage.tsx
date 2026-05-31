import { FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { fetchWorkOrders } from "../api/workOrdersApi";
import { WorkOrdersTable } from "../components/WorkOrdersTable";
import type { ProcessStatusValue, WorkOrder } from "../types/workOrders";

type OfficeBucket = "INTAKE" | "PRODUCTION" | "READY";

const officeBucketOptions: Array<{ value: OfficeBucket; label: string }> = [
  { value: "INTAKE", label: "Zlecenia" },
  { value: "PRODUCTION", label: "Na produkcji" },
  { value: "READY", label: "Gotowe" },
];

function getOfficeBucket(status: ProcessStatusValue): OfficeBucket {
  if (status === "TO_BE_PLANNED" || status === "INCOMPLETE") {
    return "INTAKE";
  }

  if (status === "READY") {
    return "READY";
  }

  return "PRODUCTION";
}

function getBucketDescription(bucket: OfficeBucket): string {
  switch (bucket) {
    case "INTAKE":
      return "Nowe i niekompletne zlecenia przed produkcją.";
    case "PRODUCTION":
      return "Aktywne zlecenia na hali, według stanu procesu z backendu.";
    case "READY":
      return "Ukończone zlecenia z widocznym statusem wydania klientowi.";
  }
}

export function WorkOrdersListPage() {
  const [workOrders, setWorkOrders] = useState<WorkOrder[]>([]);
  const [activeBucket, setActiveBucket] = useState<OfficeBucket>("INTAKE");
  const [externalOrderNumberFilter, setExternalOrderNumberFilter] = useState("");
  const [appliedExternalOrderNumberFilter, setAppliedExternalOrderNumberFilter] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const hasAppliedExternalOrderNumberFilter = appliedExternalOrderNumberFilter.trim().length > 0;

  const bucketCounts = officeBucketOptions.reduce<Record<OfficeBucket, number>>(
    (counts, bucket) => ({ ...counts, [bucket.value]: 0 }),
    { INTAKE: 0, PRODUCTION: 0, READY: 0 },
  );

  for (const workOrder of workOrders) {
    bucketCounts[getOfficeBucket(workOrder.process_status.value)] += 1;
  }

  const visibleWorkOrders = workOrders.filter((workOrder) => getOfficeBucket(workOrder.process_status.value) === activeBucket);

  useEffect(() => {
    let isActive = true;

    async function loadWorkOrders() {
      setIsLoading(true);
      setErrorMessage(null);

      try {
        const response = await fetchWorkOrders({ externalOrderNumber: appliedExternalOrderNumberFilter });
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
  }, [appliedExternalOrderNumberFilter]);

  function applyExternalOrderNumberFilter(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setAppliedExternalOrderNumberFilter(externalOrderNumberFilter.trim());
  }

  function clearExternalOrderNumberFilter() {
    setExternalOrderNumberFilter("");
    setAppliedExternalOrderNumberFilter("");
  }

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
          <form className="mt-4 flex flex-col gap-3 lg:flex-row lg:items-end" onSubmit={applyExternalOrderNumberFilter}>
            <label className="flex min-w-0 flex-1 flex-col gap-2">
              <span className="text-sm font-medium text-ink">Numer zewnętrzny</span>
              <input
                type="search"
                value={externalOrderNumberFilter}
                onChange={(event) => setExternalOrderNumberFilter(event.target.value)}
                className="rounded-2xl border border-line bg-white px-4 py-3 text-sm text-ink outline-none transition focus:border-accent"
              />
            </label>
            <div className="flex flex-wrap gap-2">
              <button
                type="submit"
                className="inline-flex items-center justify-center rounded-full bg-accent px-5 py-3 text-sm font-medium text-white transition hover:bg-teal-700"
              >
                Szukaj
              </button>
              {hasAppliedExternalOrderNumberFilter ? (
                <button
                  type="button"
                  onClick={clearExternalOrderNumberFilter}
                  className="inline-flex items-center justify-center rounded-full border border-line bg-mist px-5 py-3 text-sm font-medium text-steel transition hover:border-accent hover:text-accent"
                >
                  Wyczyść
                </button>
              ) : null}
            </div>
          </form>
            <div className="mt-4 flex flex-wrap gap-2">
              {officeBucketOptions.map((bucket) => (
                <button
                  key={bucket.value}
                  type="button"
                  onClick={() => setActiveBucket(bucket.value)}
                  className={[
                    "inline-flex items-center gap-2 rounded-full border px-4 py-2 text-sm font-medium transition",
                    activeBucket === bucket.value
                      ? "border-accent bg-white text-ink shadow-sm"
                      : "border-line bg-mist text-steel hover:border-accent hover:text-accent",
                  ].join(" ")}
                >
                  <span>{bucket.label}</span>
                  <span className="inline-flex min-w-6 justify-center rounded-full bg-white px-2 py-0.5 text-xs font-semibold text-ink">
                    {bucketCounts[bucket.value]}
                  </span>
                </button>
              ))}
            </div>
            <p className="mt-3 text-sm text-steel">{getBucketDescription(activeBucket)}</p>
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
            {hasAppliedExternalOrderNumberFilter ? "Brak zleceń dla numeru zewnętrznego" : "Brak zleceń"}
          </div>
        ) : visibleWorkOrders.length === 0 ? (
          <div className="rounded-3xl border border-dashed border-line bg-mist px-6 py-12 text-center text-base text-steel">
            Brak zleceń w wybranej grupie
          </div>
        ) : (
          <WorkOrdersTable workOrders={visibleWorkOrders} />
        )}
      </section>
    </main>
  );
}