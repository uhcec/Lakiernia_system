import { FormEvent, useEffect, useMemo, useState } from "react";

import { fetchAuditEvents, getAuditEventsExportUrl, type AuditEventSearchParams } from "../api/auditApi";
import { downloadAuthedFile } from "../utils/download";
import type { AuditEvent, AuditStationId } from "../types/audit";

const stationOptions: Array<{ value: AuditStationId; label: string }> = [
  { value: "OFFICE", label: "Biuro" },
  { value: "MANAGER", label: "Kierownik" },
  { value: "SURFACE_PREPARATION", label: "Przygotowanie" },
  { value: "HANGING", label: "Zawieszanie" },
  { value: "AUTOMATIC_PRODUCTION", label: "Produkcja automat" },
  { value: "MANUAL_PRODUCTION", label: "Produkcja ręczna" },
  { value: "PACKING", label: "Pakowanie" },
  { value: "DECORAL_PRODUCTION", label: "Produkcja Decoral" },
  { value: "SYSTEM", label: "System" },
  { value: "UNKNOWN", label: "Nieznana stacja" },
];

const stationLabels = stationOptions.reduce<Record<AuditStationId, string>>((labels, option) => {
  labels[option.value] = option.label;
  return labels;
}, {} as Record<AuditStationId, string>);

interface AuditFilterState {
  workOrderId: string;
  eventType: string;
  stationId: AuditStationId | "";
  requestId: string;
  targetType: string;
  targetId: string;
  createdFrom: string;
  createdTo: string;
}

const initialFilters: AuditFilterState = {
  workOrderId: "",
  eventType: "",
  stationId: "",
  requestId: "",
  targetType: "",
  targetId: "",
  createdFrom: "",
  createdTo: "",
};

function formatDateTime(value: string): string {
  return new Intl.DateTimeFormat("pl-PL", {
    dateStyle: "short",
    timeStyle: "short",
  }).format(new Date(value));
}

function formatDetails(details: AuditEvent["details"]): string {
  if (details === null) {
    return "-";
  }

  return JSON.stringify(details, null, 2);
}

function buildSearchParams(filters: AuditFilterState): AuditEventSearchParams {
  return {
    workOrderId: filters.workOrderId,
    eventType: filters.eventType,
    stationId: filters.stationId,
    requestId: filters.requestId,
    targetType: filters.targetType,
    targetId: filters.targetId,
    createdFrom: filters.createdFrom,
    createdTo: filters.createdTo,
    limit: 100,
  };
}

export function AuditEventsPage() {
  const [filters, setFilters] = useState<AuditFilterState>(initialFilters);
  const [appliedFilters, setAppliedFilters] = useState<AuditFilterState>(initialFilters);
  const [auditEvents, setAuditEvents] = useState<AuditEvent[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const exportUrl = useMemo(() => getAuditEventsExportUrl(buildSearchParams(appliedFilters)), [appliedFilters]);

  useEffect(() => {
    let isActive = true;

    async function loadAuditEvents() {
      setIsLoading(true);
      setErrorMessage(null);

      try {
        const response = await fetchAuditEvents(buildSearchParams(appliedFilters));
        if (!isActive) {
          return;
        }
        setAuditEvents(response.items);
      } catch (error) {
        if (!isActive) {
          return;
        }
        setErrorMessage(error instanceof Error ? error.message : "Nie udało się pobrać historii audytu");
      } finally {
        if (isActive) {
          setIsLoading(false);
        }
      }
    }

    loadAuditEvents();

    return () => {
      isActive = false;
    };
  }, [appliedFilters]);

  function updateFilter<K extends keyof AuditFilterState>(key: K, value: AuditFilterState[K]) {
    setFilters((currentFilters) => ({ ...currentFilters, [key]: value }));
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setAppliedFilters(filters);
  }

  function clearFilters() {
    setFilters(initialFilters);
    setAppliedFilters(initialFilters);
  }

  async function handleExport() {
    setErrorMessage(null);
    try {
      await downloadAuthedFile(exportUrl, "audit-events.csv");
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Nie udało się wyeksportować CSV");
    }
  }

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-7xl flex-col gap-6 px-4 py-8 sm:px-6 lg:px-8">
      <section className="rounded-[2rem] border border-white/70 bg-white/80 p-6 shadow-panel backdrop-blur sm:p-8">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div className="space-y-2">
            <p className="text-sm font-semibold uppercase tracking-[0.18em] text-accent">Audyt</p>
            <div>
              <h1 className="text-3xl font-semibold text-ink sm:text-4xl">Historia systemu</h1>
              <p className="mt-2 max-w-2xl text-sm leading-6 text-steel sm:text-base">
                Wyszukiwanie zdarzeń po stacji, typie zdarzenia, zleceniu i identyfikatorze żądania.
              </p>
            </div>
          </div>
          <div className="rounded-2xl border border-line bg-mist px-4 py-3 text-sm text-steel">
            Widocznych zdarzeń: <span className="font-semibold text-ink">{auditEvents.length}</span>
          </div>
        </div>
      </section>

      <section className="rounded-[2rem] border border-white/70 bg-white/80 p-6 shadow-panel backdrop-blur sm:p-8">
        <form className="grid gap-4 md:grid-cols-2 xl:grid-cols-4" onSubmit={handleSubmit}>
          <label className="space-y-2 text-sm font-medium text-ink">
            ID zlecenia
            <input
              className="w-full rounded-2xl border border-line bg-white px-4 py-3 text-sm text-ink outline-none transition focus:border-accent"
              inputMode="numeric"
              value={filters.workOrderId}
              onChange={(event) => updateFilter("workOrderId", event.target.value)}
            />
          </label>
          <label className="space-y-2 text-sm font-medium text-ink">
            Typ zdarzenia
            <input
              className="w-full rounded-2xl border border-line bg-white px-4 py-3 text-sm text-ink outline-none transition focus:border-accent"
              value={filters.eventType}
              onChange={(event) => updateFilter("eventType", event.target.value)}
            />
          </label>
          <label className="space-y-2 text-sm font-medium text-ink">
            Stacja
            <select
              className="w-full rounded-2xl border border-line bg-white px-4 py-3 text-sm text-ink outline-none transition focus:border-accent"
              value={filters.stationId}
              onChange={(event) => updateFilter("stationId", event.target.value as AuditStationId | "")}
            >
              <option value="">Wszystkie</option>
              {stationOptions.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
          <label className="space-y-2 text-sm font-medium text-ink">
            Request ID
            <input
              className="w-full rounded-2xl border border-line bg-white px-4 py-3 text-sm text-ink outline-none transition focus:border-accent"
              value={filters.requestId}
              onChange={(event) => updateFilter("requestId", event.target.value)}
            />
          </label>
          <label className="space-y-2 text-sm font-medium text-ink">
            Typ obiektu
            <input
              className="w-full rounded-2xl border border-line bg-white px-4 py-3 text-sm text-ink outline-none transition focus:border-accent"
              value={filters.targetType}
              onChange={(event) => updateFilter("targetType", event.target.value)}
            />
          </label>
          <label className="space-y-2 text-sm font-medium text-ink">
            ID obiektu
            <input
              className="w-full rounded-2xl border border-line bg-white px-4 py-3 text-sm text-ink outline-none transition focus:border-accent"
              inputMode="numeric"
              value={filters.targetId}
              onChange={(event) => updateFilter("targetId", event.target.value)}
            />
          </label>
          <label className="space-y-2 text-sm font-medium text-ink">
            Od
            <input
              className="w-full rounded-2xl border border-line bg-white px-4 py-3 text-sm text-ink outline-none transition focus:border-accent"
              type="datetime-local"
              value={filters.createdFrom}
              onChange={(event) => updateFilter("createdFrom", event.target.value)}
            />
          </label>
          <label className="space-y-2 text-sm font-medium text-ink">
            Do
            <input
              className="w-full rounded-2xl border border-line bg-white px-4 py-3 text-sm text-ink outline-none transition focus:border-accent"
              type="datetime-local"
              value={filters.createdTo}
              onChange={(event) => updateFilter("createdTo", event.target.value)}
            />
          </label>
          <div className="flex flex-col gap-3 md:col-span-2 xl:col-span-4 sm:flex-row sm:items-center sm:justify-end">
            <button
              type="button"
              className="inline-flex items-center justify-center rounded-full border border-line bg-white px-5 py-3 text-sm font-medium text-steel transition hover:text-accent"
              onClick={clearFilters}
            >
              Wyczyść
            </button>
            <button
              type="button"
              className="inline-flex items-center justify-center rounded-full border border-line bg-white px-5 py-3 text-sm font-medium text-ink transition hover:text-accent"
              onClick={handleExport}
            >
              Eksport CSV
            </button>
            <button
              type="submit"
              className="inline-flex items-center justify-center rounded-full bg-accent px-5 py-3 text-sm font-medium text-white transition hover:bg-teal-700"
            >
              Szukaj
            </button>
          </div>
        </form>
      </section>

      <section className="rounded-[2rem] border border-white/70 bg-white/80 p-6 shadow-panel backdrop-blur sm:p-8">
        <h2 className="text-lg font-semibold text-ink">Zdarzenia audytu</h2>

        {isLoading ? (
          <div className="mt-6 rounded-3xl border border-dashed border-line bg-mist px-6 py-12 text-center text-base text-steel">
            Ładowanie...
          </div>
        ) : errorMessage ? (
          <div className="mt-6 rounded-3xl border border-rose-200 bg-rose-50 px-6 py-12 text-center text-base text-rose-700">
            {errorMessage}
          </div>
        ) : auditEvents.length === 0 ? (
          <div className="mt-6 rounded-3xl border border-dashed border-line bg-mist px-6 py-12 text-center text-base text-steel">
            Brak zdarzeń dla wybranych filtrów.
          </div>
        ) : (
          <div className="mt-6 overflow-hidden rounded-3xl border border-line bg-white">
            <div className="hidden grid-cols-[minmax(220px,1.4fr)_minmax(160px,0.9fr)_minmax(180px,1fr)_minmax(220px,1.3fr)] gap-4 border-b border-line bg-mist px-5 py-3 text-xs font-semibold uppercase text-steel md:grid">
              <span>Zdarzenie</span>
              <span>Stacja</span>
              <span>Czas</span>
              <span>Trace</span>
            </div>
            <div className="divide-y divide-line">
              {auditEvents.map((event) => (
                <article
                  key={event.id}
                  className="grid gap-4 px-5 py-4 text-sm md:grid-cols-[minmax(220px,1.4fr)_minmax(160px,0.9fr)_minmax(180px,1fr)_minmax(220px,1.3fr)]"
                >
                  <div className="space-y-1">
                    <p className="font-semibold text-ink">{event.summary}</p>
                    <p className="text-xs text-steel">{event.event_type}</p>
                    {event.actors.length > 0 ? (
                      <p className="text-xs text-steel">Operatorzy: {event.actors.map((actor) => actor.employee_name).join(", ")}</p>
                    ) : null}
                  </div>
                  <div className="text-steel">{stationLabels[event.station_id]}</div>
                  <div className="text-steel">{formatDateTime(event.created_at)}</div>
                  <div className="space-y-2 text-steel">
                    <p className="break-all font-mono text-xs">{event.request_id ?? "-"}</p>
                    <p className="text-xs">Zlecenie: {event.work_order_id ?? "-"}</p>
                    <details className="rounded-2xl border border-line/80 bg-mist/50 px-3 py-2">
                      <summary className="cursor-pointer font-medium text-ink">Szczegóły</summary>
                      <pre className="mt-2 overflow-x-auto whitespace-pre-wrap text-xs leading-5 text-steel">{formatDetails(event.details)}</pre>
                    </details>
                  </div>
                </article>
              ))}
            </div>
          </div>
        )}
      </section>
    </main>
  );
}
