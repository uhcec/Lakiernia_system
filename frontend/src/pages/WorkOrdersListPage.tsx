import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";

import { usePolling, STATION_POLL_INTERVAL_MS } from "../hooks/usePolling";
import { fetchWorkOrders } from "../api/workOrdersApi";
import { OfficeWorkOrdersTable } from "../components/OfficeWorkOrdersTable";
import type { ProcessStatusValue, WorkOrder } from "../types/workOrders";

type OfficeBucket = "INTAKE" | "PRODUCTION" | "READY";

const officeBucketOptions: Array<{ value: OfficeBucket; label: string }> = [
  { value: "INTAKE", label: "Zlecenia" },
  { value: "PRODUCTION", label: "Na produkcji" },
  { value: "READY", label: "Gotowe" },
];

const bucketColorClasses: Record<OfficeBucket, string> = {
  INTAKE: "bg-sky-50 text-sky-700",
  PRODUCTION: "bg-amber-50 text-amber-700",
  READY: "bg-emerald-50 text-emerald-700",
};

function MetricIcon({ label, className }: { label: string; className: string }) {
  return (
    <div className={["flex h-14 w-14 items-center justify-center rounded-[1.1rem] text-sm font-black uppercase tracking-[0.14em]", className].join(" ")}>
      {label}
    </div>
  );
}

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

  const delayedCount = workOrders.filter((workOrder) => {
    if (!workOrder.planned_pickup_date) {
      return false;
    }

    return new Date(workOrder.planned_pickup_date).getTime() < Date.now() && workOrder.process_status.value !== "READY";
  }).length;

  const visibleWorkOrders = workOrders.filter((workOrder) => getOfficeBucket(workOrder.process_status.value) === activeBucket);

  const latestFilterRef = useRef(appliedExternalOrderNumberFilter);
  latestFilterRef.current = appliedExternalOrderNumberFilter;

  const loadWorkOrders = useCallback(
    async (options?: { background?: boolean }) => {
      const background = options?.background ?? false;
      const requestedFilter = appliedExternalOrderNumberFilter;
      if (!background) {
        setIsLoading(true);
        setErrorMessage(null);
      }

      try {
        const response = await fetchWorkOrders({ externalOrderNumber: requestedFilter });
        // Ignore a stale response if the filter changed while this request was in flight.
        if (requestedFilter !== latestFilterRef.current) {
          return;
        }
        setWorkOrders(response.items);
      } catch (error) {
        if (!background && requestedFilter === latestFilterRef.current) {
          setErrorMessage(error instanceof Error ? error.message : "Nie udało się pobrać zleceń");
        }
      } finally {
        if (!background && requestedFilter === latestFilterRef.current) {
          setIsLoading(false);
        }
      }
    },
    [appliedExternalOrderNumberFilter],
  );

  useEffect(() => {
    void loadWorkOrders();
  }, [loadWorkOrders]);

  // Auto-refresh so the office list reflects production changes without a manual reload.
  usePolling(() => {
    void loadWorkOrders({ background: true });
  }, STATION_POLL_INTERVAL_MS);

  function applyExternalOrderNumberFilter(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setAppliedExternalOrderNumberFilter(externalOrderNumberFilter.trim());
  }

  function clearExternalOrderNumberFilter() {
    setExternalOrderNumberFilter("");
    setAppliedExternalOrderNumberFilter("");
  }

  return (
    <main className="flex min-h-full w-full flex-col gap-5 px-1 pb-5">
      <section className="rounded-[1.95rem] bg-white px-6 py-6 shadow-panel ring-1 ring-brand-line/70 sm:px-8 sm:py-7">
        <div className="flex flex-col gap-5 xl:flex-row xl:items-center xl:justify-between">
          <div className="flex items-start gap-5">
            <div className="flex h-20 w-20 flex-none items-center justify-center rounded-[1.7rem] bg-brand-soft shadow-inner ring-1 ring-brand-line/60">
              <div className="flex h-12 w-12 items-center justify-center rounded-[1rem] border border-brand-line/80 text-[1.35rem] font-black text-brand-900">
                ✓
              </div>
            </div>
            <div className="space-y-2">
              <h1 className="text-3xl font-bold text-brand-ink sm:text-4xl">Zlecenia produkcyjne</h1>
              <p className="max-w-3xl text-sm leading-7 text-brand-muted sm:text-base">
                Lista aktywnych zleceń roboczych z bieżącym statusem procesu.
                Widok jest przygotowany pod szybkie użycie na stanowisku biurowym.
              </p>
            </div>
          </div>

          <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
            <div className="rounded-full border border-brand-line/70 bg-brand-soft px-5 py-3 text-sm font-semibold text-brand-muted">
              Widocznych rekordów: <span className="text-xl text-brand-ink">{visibleWorkOrders.length}</span>
            </div>
            <Link
              to="/zlecenia/nowe"
              className="inline-flex items-center justify-center rounded-full bg-brand-warm px-6 py-3 text-sm font-semibold text-brand-ink transition hover:bg-brand-warm-strong"
            >
              + Dodaj zlecenie
            </Link>
          </div>
        </div>
      </section>

      <section className="grid gap-4 xl:grid-cols-4">
        <article className="rounded-[1.8rem] bg-white px-6 py-5 shadow-panel ring-1 ring-brand-line/70">
          <div className="flex items-center gap-4">
            <MetricIcon label="ALL" className="bg-brand-soft text-brand-900" />
            <div>
              <p className="text-sm font-semibold text-brand-muted">Wszystkie zlecenia</p>
              <p className="text-4xl font-bold text-brand-ink">{workOrders.length}</p>
              <p className="text-sm text-brand-muted">Aktywne w systemie</p>
            </div>
          </div>
        </article>
        <article className="rounded-[1.8rem] bg-white px-6 py-5 shadow-panel ring-1 ring-brand-line/70">
          <div className="flex items-center gap-4">
            <MetricIcon label="RUN" className="bg-amber-50 text-amber-700" />
            <div>
              <p className="text-sm font-semibold text-brand-muted">Na produkcji</p>
              <p className="text-4xl font-bold text-brand-ink">{bucketCounts.PRODUCTION}</p>
              <p className="text-sm text-brand-muted">W realizacji</p>
            </div>
          </div>
        </article>
        <article className="rounded-[1.8rem] bg-white px-6 py-5 shadow-panel ring-1 ring-brand-line/70">
          <div className="flex items-center gap-4">
            <MetricIcon label="OK" className="bg-emerald-50 text-emerald-700" />
            <div>
              <p className="text-sm font-semibold text-brand-muted">Gotowe</p>
              <p className="text-4xl font-bold text-brand-ink">{bucketCounts.READY}</p>
              <p className="text-sm text-brand-muted">Zakończone</p>
            </div>
          </div>
        </article>
        <article className="rounded-[1.8rem] bg-white px-6 py-5 shadow-panel ring-1 ring-brand-line/70">
          <div className="flex items-center gap-4">
            <MetricIcon label="ETA" className="bg-rose-50 text-rose-700" />
            <div>
              <p className="text-sm font-semibold text-brand-muted">Po terminie</p>
              <p className="text-4xl font-bold text-brand-ink">{delayedCount}</p>
              <p className="text-sm text-brand-muted">Po terminie</p>
            </div>
          </div>
        </article>
      </section>

      <section className="space-y-5 rounded-[1.95rem] bg-white px-6 py-6 shadow-panel ring-1 ring-brand-line/70 sm:px-8 sm:py-7">
        <div>
          <h2 className="text-[2rem] font-bold text-brand-ink">Lista zleceń</h2>
          <form className="mt-5 flex flex-col gap-3 xl:flex-row xl:items-end" onSubmit={applyExternalOrderNumberFilter}>
            <label className="flex min-w-0 flex-1 flex-col gap-2">
              <span className="text-sm font-semibold text-brand-ink">Numer zewnętrzny</span>
              <input
                type="search"
                value={externalOrderNumberFilter}
                onChange={(event) => setExternalOrderNumberFilter(event.target.value)}
                placeholder="Wpisz numer zewnętrzny i naciśnij Enter..."
                className="rounded-[1.2rem] border border-brand-line bg-brand-soft px-4 py-3 text-sm text-brand-ink outline-none transition placeholder:text-brand-muted/70 focus:border-brand-900"
              />
            </label>
            <div className="flex flex-wrap gap-2">
              <button
                type="submit"
                className="inline-flex items-center justify-center rounded-full bg-brand-900 px-6 py-3 text-sm font-semibold text-white transition hover:bg-brand-800"
              >
                Szukaj
              </button>
              {hasAppliedExternalOrderNumberFilter ? (
                <button
                  type="button"
                  onClick={clearExternalOrderNumberFilter}
                  className="inline-flex items-center justify-center rounded-full bg-brand-surface px-6 py-3 text-sm font-semibold text-brand-muted transition hover:text-brand-ink"
                >
                  Wyczysc
                </button>
              ) : null}
              <button
                type="button"
                className="inline-flex h-[3.1rem] w-[3.1rem] items-center justify-center rounded-full border border-brand-line bg-white text-brand-muted transition hover:text-brand-ink"
                aria-label="Filtry"
              >
                ≡
              </button>
            </div>
          </form>
          <div className="mt-5 flex flex-wrap gap-3">
            {officeBucketOptions.map((bucket) => (
              <button
                key={bucket.value}
                type="button"
                onClick={() => setActiveBucket(bucket.value)}
                className={[
                  "inline-flex items-center gap-3 rounded-full px-4 py-2 text-sm font-semibold transition",
                  activeBucket === bucket.value
                    ? "bg-brand-900 text-white shadow-brand"
                    : `${bucketColorClasses[bucket.value]} hover:opacity-90`,
                ].join(" ")}
              >
                <span className="h-2.5 w-2.5 rounded-full bg-current" />
                <span>{bucket.label}</span>
                <span className="inline-flex min-w-7 justify-center rounded-full bg-white/80 px-2 py-0.5 text-xs font-bold text-brand-ink">
                  {bucketCounts[bucket.value]}
                </span>
              </button>
            ))}
          </div>
          <p className="mt-4 text-sm text-brand-muted">{getBucketDescription(activeBucket)}</p>
        </div>

        {isLoading ? (
          <div className="rounded-[1.8rem] border border-dashed border-brand-line bg-brand-soft px-6 py-12 text-center text-base text-brand-muted">
            Ładowanie...
          </div>
        ) : errorMessage ? (
          <div className="rounded-[1.8rem] border border-rose-200 bg-rose-50 px-6 py-12 text-center text-base text-rose-700">
            {errorMessage}
          </div>
        ) : workOrders.length === 0 ? (
          <div className="rounded-[1.8rem] border border-dashed border-brand-line bg-brand-soft px-6 py-12 text-center text-base text-brand-muted">
            {hasAppliedExternalOrderNumberFilter ? "Brak zleceń dla numeru zewnętrznego" : "Brak zleceń"}
          </div>
        ) : visibleWorkOrders.length === 0 ? (
          <div className="rounded-[1.8rem] border border-dashed border-brand-line bg-brand-soft px-6 py-12 text-center text-base text-brand-muted">
            Brak zleceń w wybranej grupie
          </div>
        ) : (
          <OfficeWorkOrdersTable workOrders={visibleWorkOrders} />
        )}
      </section>
    </main>
  );
}