import { useEffect, useState } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { fetchCycleTimeStats, fetchThroughputStats, fetchWipAging } from "../api/managerApi";
import type { CycleTimeStats, ThroughputPeriod, ThroughputStats, WipAgingStats } from "../types/manager";
import { BarChart, type BarChartPoint } from "../components/BarChart";

type GroupBy = "day" | "week" | "month";

type LoadedParams = { from: string; to: string; groupBy: GroupBy };

type MonthAnchor = { year: number; month: number }; // month is 0-based

const MONTHS_PL_SHORT = ["Sty", "Lut", "Mar", "Kwi", "Maj", "Cze", "Lip", "Sie", "Wrz", "Paź", "Lis", "Gru"];
const MONTHS_PL = [
  "Styczeń", "Luty", "Marzec", "Kwiecień", "Maj", "Czerwiec",
  "Lipiec", "Sierpień", "Wrzesień", "Październik", "Listopad", "Grudzień",
];
const MAX_DAILY_BARS = 366;

function monthRange(anchor: MonthAnchor): { from: string; to: string } {
  const from = new Date(Date.UTC(anchor.year, anchor.month, 1)).toISOString().slice(0, 10);
  const to = new Date(Date.UTC(anchor.year, anchor.month + 1, 0)).toISOString().slice(0, 10);
  return { from, to };
}

function currentMonthAnchor(): MonthAnchor {
  const now = new Date();
  return { year: now.getFullYear(), month: now.getMonth() };
}

function isoParts(iso: string): { y: number; m: number; d: number } {
  const [y, m, d] = iso.split("-").map(Number);
  return { y, m, d };
}

function formatDayLabel(iso: string): string {
  const { y, m, d } = isoParts(iso);
  return `${String(d).padStart(2, "0")}.${String(m).padStart(2, "0")}.${y}`;
}

function eachDay(from: string, to: string): string[] {
  const days: string[] = [];
  const end = new Date(`${to}T00:00:00Z`).getTime();
  for (let t = new Date(`${from}T00:00:00Z`).getTime(); t <= end; t += 86_400_000) {
    days.push(new Date(t).toISOString().slice(0, 10));
    if (days.length > MAX_DAILY_BARS) break;
  }
  return days;
}

function buildPoints(
  stats: ThroughputStats,
  params: LoadedParams,
  metric: (period: ThroughputPeriod) => number,
): BarChartPoint[] {
  if (params.groupBy === "day") {
    const days = eachDay(params.from, params.to);
    if (days.length <= MAX_DAILY_BARS) {
      const byDate = new Map(stats.periods.map((period) => [period.period_start, period]));
      return days.map((iso) => {
        const period = byDate.get(iso);
        return {
          key: iso,
          tick: String(isoParts(iso).d),
          label: formatDayLabel(iso),
          value: period ? metric(period) : 0,
        };
      });
    }
  }
  return stats.periods.map((period) => ({
    key: period.period_start,
    tick:
      params.groupBy === "month"
        ? MONTHS_PL_SHORT[isoParts(period.period_start).m - 1]
        : formatDayLabel(period.period_start).slice(0, 5),
    label: period.period_label,
    value: metric(period),
  }));
}

type SegmentDef = { key: keyof ThroughputPeriod; label: string; className: string };

const METHOD_SEGMENT_DEFS: readonly SegmentDef[] = [
  { key: "m2_automatic", label: "Automat", className: "bg-accent" },
  { key: "m2_manual", label: "Ręczna", className: "bg-sky-500" },
];

const COATING_SEGMENT_DEFS: readonly SegmentDef[] = [
  { key: "m2_ral_only", label: "Czysty RAL", className: "bg-emerald-500" },
  { key: "m2_decoral", label: "Decoral", className: "bg-fuchsia-500" },
];

// Daily/period points whose bar height is the period total, split into stacked segments along the
// chosen axis (method or coating). Both axes sum to m2_total, so the bar height is identical either way.
function buildStackedPoints(
  stats: ThroughputStats,
  params: LoadedParams,
  segmentDefs: readonly SegmentDef[],
): BarChartPoint[] {
  const toPoint = (
    period: ThroughputPeriod | undefined,
    base: { key: string; tick: string; label: string },
  ): BarChartPoint => ({
    ...base,
    value: period ? period.m2_total : 0,
    segments: segmentDefs.map((def) => ({
      value: period ? (period[def.key] as number) : 0,
      className: def.className,
    })),
  });

  if (params.groupBy === "day") {
    const days = eachDay(params.from, params.to);
    if (days.length <= MAX_DAILY_BARS) {
      const byDate = new Map(stats.periods.map((period) => [period.period_start, period]));
      return days.map((iso) =>
        toPoint(byDate.get(iso), { key: iso, tick: String(isoParts(iso).d), label: formatDayLabel(iso) }),
      );
    }
  }
  return stats.periods.map((period) =>
    toPoint(period, {
      key: period.period_start,
      tick:
        params.groupBy === "month"
          ? MONTHS_PL_SHORT[isoParts(period.period_start).m - 1]
          : formatDayLabel(period.period_start).slice(0, 5),
      label: period.period_label,
    }),
  );
}

function CompositionBar({
  title,
  total,
  segments,
}: {
  title: string;
  total: number;
  segments: { label: string; value: number; className: string }[];
}) {
  const pct = (value: number) => (total > 0 ? (value / total) * 100 : 0);
  return (
    <div>
      <div className="mb-1 flex items-baseline justify-between">
        <p className="text-xs font-semibold uppercase tracking-[0.1em] text-steel">{title}</p>
        <span className="text-xs text-steel">{total.toLocaleString("pl-PL", { maximumFractionDigits: 0 })} m²</span>
      </div>
      <div className="flex h-7 w-full overflow-hidden rounded-lg bg-mist">
        {segments.map((segment) =>
          pct(segment.value) > 0 ? (
            <div key={segment.label} className={segment.className} style={{ width: `${pct(segment.value)}%` }} />
          ) : null,
        )}
      </div>
      <div className="mt-1.5 flex flex-wrap gap-x-4 gap-y-1 text-xs text-steel">
        {segments.map((segment) => (
          <span key={segment.label} className="inline-flex items-center gap-1.5">
            <span className={`inline-block h-2.5 w-2.5 rounded-sm ${segment.className}`} />
            {segment.label}: {segment.value.toLocaleString("pl-PL", { maximumFractionDigits: 0 })} m² ({pct(segment.value).toFixed(0)}%)
          </span>
        ))}
      </div>
    </div>
  );
}

function formatDuration(seconds: number): string {
  const total = Math.round(seconds);
  if (total < 60) return `${total} s`;
  const minutes = Math.round(total / 60);
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  const remainder = minutes % 60;
  return remainder === 0 ? `${hours} godz` : `${hours} godz ${remainder} min`;
}

function buildCycleTimePoints(stats: CycleTimeStats): BarChartPoint[] {
  return stats.stages.map((stage) => ({
    key: stage.stage,
    tick: stage.stage_label,
    label: `${stage.stage_label} (${stage.orders_count} zleceń)`,
    value: Math.round((stage.average_seconds / 60) * 10) / 10,
  }));
}

function productionTypeLabel(value: string | null): string {
  if (value === "MANUAL") return "Ręczna";
  if (value === "AUTOMATIC") return "Automat";
  return "—";
}

function buildWaitTimePoints(stats: CycleTimeStats): BarChartPoint[] {
  return stats.stages
    .filter((stage) => stage.average_wait_before_seconds !== null)
    .map((stage) => ({
      key: stage.stage,
      tick: stage.stage_label,
      label: `Przed: ${stage.stage_label} (${stage.wait_orders_count} zleceń)`,
      value: Math.round(((stage.average_wait_before_seconds as number) / 60) * 10) / 10,
    }));
}

export function StatystykiPage() {
  const [anchor, setAnchor] = useState<MonthAnchor>(currentMonthAnchor);
  const [throughputStats, setThroughputStats] = useState<ThroughputStats | null>(null);
  const [cycleTimeStats, setCycleTimeStats] = useState<CycleTimeStats | null>(null);
  const [wipAging, setWipAging] = useState<WipAgingStats | null>(null);
  const [loadedParams, setLoadedParams] = useState<LoadedParams | null>(null);
  const [breakdownAxis, setBreakdownAxis] = useState<"method" | "coating">("method");
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const today = currentMonthAnchor();
  const isCurrentMonth = anchor.year === today.year && anchor.month === today.month;

  useEffect(() => {
    const { from, to } = monthRange(anchor);
    let cancelled = false;
    setIsLoading(true);
    setErrorMessage(null);
    Promise.all([fetchThroughputStats(from, to, "day"), fetchCycleTimeStats(from, to)])
      .then(([throughput, cycleTime]) => {
        if (cancelled) return;
        setThroughputStats(throughput);
        setCycleTimeStats(cycleTime);
        setLoadedParams({ from, to, groupBy: "day" });
      })
      .catch((error) => {
        if (cancelled) return;
        setErrorMessage(error instanceof Error ? error.message : "Nie udało się pobrać statystyk");
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [anchor]);

  // WIP-aging is a live "what's stuck right now" view, independent of the selected month.
  useEffect(() => {
    let cancelled = false;
    fetchWipAging()
      .then((stats) => {
        if (!cancelled) setWipAging(stats);
      })
      .catch(() => {
        // Non-blocking: the rest of the page stays usable if this live view fails.
        if (!cancelled) setWipAging(null);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  function shiftMonth(delta: number) {
    setAnchor((current) => {
      const d = new Date(current.year, current.month + delta, 1);
      return { year: d.getFullYear(), month: d.getMonth() };
    });
  }

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-7xl flex-col gap-6 px-4 py-8 sm:px-6 lg:px-8">
      {wipAging && wipAging.items.length > 0 ? (
        <section className="rounded-[2rem] border border-white/70 bg-white/80 p-6 shadow-panel backdrop-blur sm:p-8">
          <div className="mb-4">
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-accent">Na żywo</p>
            <h2 className="mt-1 text-3xl font-semibold text-ink sm:text-4xl">Zlecenia w toku</h2>
            <p className="mt-2 text-sm text-steel">
              Zlecenia aktualnie w realizacji, według czasu spędzonego na bieżącym etapie (najdłużej u góry).
            </p>
          </div>
          <div className="overflow-x-auto rounded-3xl border border-line bg-white">
            <table className="w-full min-w-[640px] text-sm">
              <thead>
                <tr className="border-b border-line bg-mist text-xs font-semibold uppercase tracking-[0.1em] text-steel">
                  <th className="px-5 py-3 text-left">Zlecenie</th>
                  <th className="px-4 py-3 text-left">Klient</th>
                  <th className="px-4 py-3 text-left">Etap</th>
                  <th className="px-4 py-3 text-left">Produkcja</th>
                  <th className="px-4 py-3 text-right">Czas na etapie</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {wipAging.items.map((item) => {
                  const isLong = item.age_seconds >= 24 * 3600;
                  return (
                    <tr key={item.work_order_id} className={isLong ? "bg-rose-50/60 text-ink" : "text-ink hover:bg-mist/40"}>
                      <td className="px-5 py-3 font-medium">{item.order_number}</td>
                      <td className="px-4 py-3 text-steel">{item.customer_name ?? "—"}</td>
                      <td className="px-4 py-3 text-steel">{item.stage_label}</td>
                      <td className="px-4 py-3 text-steel">{productionTypeLabel(item.production_type)}</td>
                      <td className={`px-4 py-3 text-right font-semibold ${isLong ? "text-rose-700" : ""}`}>
                        {formatDuration(item.age_seconds)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}

      <section className="rounded-[2rem] border border-white/70 bg-white/80 p-6 shadow-panel backdrop-blur sm:p-8">
        <div className="mb-6">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-accent">Produkcja</p>
          <h2 className="mt-1 text-3xl font-semibold text-ink sm:text-4xl">Przepustowość</h2>
          <p className="mt-2 text-sm text-steel">
            Zrealizowane m² (wg typu produkcji — ręczna/automat obejmują też bazę zleceń Decoral, liczone w dniu
            zakończenia pakowania), osobny przejazd Decoral (liczony w dniu zakończenia powłoki Decoral) oraz sztuki
            poprawek, w skali dnia.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <div className="inline-flex items-center gap-1 rounded-2xl border border-line bg-mist p-1">
            <button
              type="button"
              onClick={() => shiftMonth(-1)}
              aria-label="Poprzedni miesiąc"
              className="rounded-xl p-2 text-steel transition hover:bg-white hover:text-accent"
            >
              <ChevronLeft className="h-5 w-5" />
            </button>
            <span className="min-w-[160px] text-center text-sm font-semibold text-ink">
              {MONTHS_PL[anchor.month]} {anchor.year}
            </span>
            <button
              type="button"
              onClick={() => shiftMonth(1)}
              disabled={isCurrentMonth}
              aria-label="Następny miesiąc"
              className="rounded-xl p-2 text-steel transition hover:bg-white hover:text-accent disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:bg-transparent disabled:hover:text-steel"
            >
              <ChevronRight className="h-5 w-5" />
            </button>
          </div>
          {!isCurrentMonth ? (
            <button
              type="button"
              onClick={() => setAnchor(currentMonthAnchor())}
              className="rounded-full border border-line px-4 py-2 text-xs font-medium text-steel transition hover:border-accent hover:text-accent"
            >
              Bieżący miesiąc
            </button>
          ) : null}
          {isLoading ? <span className="text-sm text-steel">Ładowanie…</span> : null}
        </div>

        {errorMessage ? (
          <div className="mt-4 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{errorMessage}</div>
        ) : null}

        {throughputStats ? (
          <div className="mt-6">
            {throughputStats.orders_without_m2_count > 0 ? (
              <div className="mb-4 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-2 text-sm text-amber-800">
                {throughputStats.orders_without_m2_count}{" "}
                {throughputStats.orders_without_m2_count === 1 ? "zlecenie nie ma" : "zleceń nie ma"} wypełnionego metrażu
                — dane m² mogą być niepełne.
              </div>
            ) : null}

            {loadedParams && throughputStats.periods.length > 0 ? (
              <div className="mb-6 flex flex-col gap-5">
                {/* 1. Headline — how much product passed through the factory */}
                <div className="flex flex-wrap items-baseline gap-x-6 gap-y-1 rounded-3xl border border-line bg-mist px-5 py-4">
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-[0.18em] text-accent">Przez fabrykę</p>
                    <p className="mt-1 text-3xl font-semibold text-ink">
                      {throughputStats.totals.m2_total.toLocaleString("pl-PL", { maximumFractionDigits: 0 })}{" "}
                      <span className="text-base font-normal text-steel">m²</span>
                    </p>
                  </div>
                  <p className="text-sm text-steel">
                    {throughputStats.totals.orders_count} {throughputStats.totals.orders_count === 1 ? "zlecenie" : "zleceń"}
                  </p>
                </div>

                {/* 2. Composition — the same total, cut two ways (both sum to it) */}
                <div className="flex flex-col gap-4 rounded-3xl border border-line bg-white p-5">
                  <p className="text-sm font-semibold uppercase tracking-[0.1em] text-steel">
                    Skład produkcji — ten sam total, dwa przekroje
                  </p>
                  <CompositionBar
                    title="Wg metody"
                    total={throughputStats.totals.m2_total}
                    segments={[
                      { label: "Ręczna", value: throughputStats.totals.m2_manual, className: "bg-sky-500" },
                      { label: "Automat", value: throughputStats.totals.m2_automatic, className: "bg-accent" },
                    ]}
                  />
                  <CompositionBar
                    title="Wg powłoki"
                    total={throughputStats.totals.m2_total}
                    segments={[
                      { label: "Czysty RAL", value: throughputStats.totals.m2_ral_only, className: "bg-emerald-500" },
                      { label: "Decoral", value: throughputStats.totals.m2_decoral, className: "bg-fuchsia-500" },
                    ]}
                  />
                </div>

                {/* 3. Daily stacked chart with method/coating toggle (total height unchanged) */}
                <div className="flex flex-col gap-3">
                  <div className="flex items-center justify-end gap-2">
                    <span className="text-xs font-medium text-steel">Przekrój:</span>
                    <div className="inline-flex items-center gap-1 rounded-2xl border border-line bg-mist p-1">
                      <button
                        type="button"
                        onClick={() => setBreakdownAxis("method")}
                        className={`rounded-xl px-3 py-1 text-xs font-medium transition ${breakdownAxis === "method" ? "bg-white text-accent shadow-sm" : "text-steel hover:text-accent"}`}
                      >
                        Metoda
                      </button>
                      <button
                        type="button"
                        onClick={() => setBreakdownAxis("coating")}
                        className={`rounded-xl px-3 py-1 text-xs font-medium transition ${breakdownAxis === "coating" ? "bg-white text-accent shadow-sm" : "text-steel hover:text-accent"}`}
                      >
                        Powłoka
                      </button>
                    </div>
                  </div>
                  <BarChart
                    title="Produkcja — m² / dzień"
                    unit="m²"
                    decimals={1}
                    plotHeight={360}
                    legend={(breakdownAxis === "method" ? METHOD_SEGMENT_DEFS : COATING_SEGMENT_DEFS).map((def) => ({
                      label: def.label,
                      className: def.className,
                    }))}
                    data={buildStackedPoints(
                      throughputStats,
                      loadedParams,
                      breakdownAxis === "method" ? METHOD_SEGMENT_DEFS : COATING_SEGMENT_DEFS,
                    )}
                  />
                </div>

                {/* 4. Decoral pass — separate line workload, NOT part of the total */}
                <BarChart
                  title="Przejazd Decoral — m² / dzień (osobny licznik, nie wlicza się do total)"
                  unit="m²"
                  decimals={1}
                  barClassName="bg-violet-500"
                  yMax={70}
                  yTickStep={10}
                  plotHeight={360}
                  data={buildPoints(throughputStats, loadedParams, (p) => p.m2_decoral_pass)}
                />

                <BarChart
                  title="Poprawki — sztuki / dzień"
                  unit="szt."
                  barClassName="bg-amber-500"
                  data={buildPoints(throughputStats, loadedParams, (p) => p.correction_pieces)}
                />
              </div>
            ) : null}

            <div className="overflow-x-auto rounded-3xl border border-line bg-white">
              <table className="w-full min-w-[640px] text-sm">
                <thead>
                  <tr className="border-b border-line bg-mist text-xs font-semibold uppercase tracking-[0.1em] text-steel">
                    <th className="px-5 py-3 text-left">Okres</th>
                    <th className="px-4 py-3 text-right" title="Wg metody — sumuje się do m² Razem">Ręczna</th>
                    <th className="px-4 py-3 text-right" title="Wg metody — sumuje się do m² Razem">Automat</th>
                    <th className="px-4 py-3 text-right" title="Wg powłoki — sumuje się do m² Razem">Czysty RAL</th>
                    <th className="px-4 py-3 text-right" title="Wg powłoki — sumuje się do m² Razem">Decoral</th>
                    <th className="px-4 py-3 text-right font-bold">m² Razem</th>
                    <th className="px-4 py-3 text-right" title="Przejazd Decoral (etap DECORAL_PRODUCTION) — osobny licznik obciążenia linii; nie wlicza się do m² Razem">
                      Przejazd Decoral*
                    </th>
                    <th className="px-4 py-3 text-right">Zlecenia</th>
                    <th className="px-4 py-3 text-right">Poprawki (szt.)</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line">
                  {throughputStats.periods.length === 0 ? (
                    <tr>
                      <td colSpan={9} className="px-5 py-10 text-center text-steel">
                        Brak danych dla wybranego okresu.
                      </td>
                    </tr>
                  ) : (
                    throughputStats.periods.map((period) => (
                      <tr key={period.period_start} className="text-ink hover:bg-mist/40">
                        <td className="px-5 py-3 font-medium">{period.period_label}</td>
                        <td className="px-4 py-3 text-right text-steel">
                          {period.m2_manual > 0 ? period.m2_manual.toFixed(1) : "—"}
                        </td>
                        <td className="px-4 py-3 text-right text-steel">
                          {period.m2_automatic > 0 ? period.m2_automatic.toFixed(1) : "—"}
                        </td>
                        <td className="px-4 py-3 text-right text-steel">
                          {period.m2_ral_only > 0 ? period.m2_ral_only.toFixed(1) : "—"}
                        </td>
                        <td className="px-4 py-3 text-right text-steel">
                          {period.m2_decoral > 0 ? period.m2_decoral.toFixed(1) : "—"}
                        </td>
                        <td className="px-4 py-3 text-right font-semibold">{period.m2_total.toFixed(1)}</td>
                        <td className="px-4 py-3 text-right text-steel">
                          {period.m2_decoral_pass > 0 ? period.m2_decoral_pass.toFixed(1) : "—"}
                        </td>
                        <td className="px-4 py-3 text-right text-steel">{period.orders_count}</td>
                        <td className="px-4 py-3 text-right">
                          {period.correction_pieces > 0 ? (
                            <span className="inline-flex rounded-full bg-amber-100 px-2.5 py-0.5 text-xs font-semibold text-amber-800">
                              {period.correction_pieces} szt.
                            </span>
                          ) : (
                            <span className="text-steel">—</span>
                          )}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
                {throughputStats.periods.length > 0 ? (
                  <tfoot>
                    <tr className="border-t-2 border-line bg-mist font-semibold text-ink">
                      <td className="px-5 py-3">Razem</td>
                      <td className="px-4 py-3 text-right">
                        {throughputStats.totals.m2_manual > 0 ? throughputStats.totals.m2_manual.toFixed(1) : "—"}
                      </td>
                      <td className="px-4 py-3 text-right">
                        {throughputStats.totals.m2_automatic > 0 ? throughputStats.totals.m2_automatic.toFixed(1) : "—"}
                      </td>
                      <td className="px-4 py-3 text-right">
                        {throughputStats.totals.m2_ral_only > 0 ? throughputStats.totals.m2_ral_only.toFixed(1) : "—"}
                      </td>
                      <td className="px-4 py-3 text-right">
                        {throughputStats.totals.m2_decoral > 0 ? throughputStats.totals.m2_decoral.toFixed(1) : "—"}
                      </td>
                      <td className="px-4 py-3 text-right text-accent">
                        {throughputStats.totals.m2_total.toFixed(1)} m²
                      </td>
                      <td className="px-4 py-3 text-right">
                        {throughputStats.totals.m2_decoral_pass > 0 ? throughputStats.totals.m2_decoral_pass.toFixed(1) : "—"}
                      </td>
                      <td className="px-4 py-3 text-right">{throughputStats.totals.orders_count}</td>
                      <td className="px-4 py-3 text-right">
                        {throughputStats.totals.correction_pieces > 0 ? (
                          <span className="inline-flex rounded-full bg-amber-100 px-2.5 py-0.5 text-xs font-semibold text-amber-800">
                            {throughputStats.totals.correction_pieces} szt.
                          </span>
                        ) : (
                          "—"
                        )}
                      </td>
                    </tr>
                  </tfoot>
                ) : null}
              </table>
            </div>
            <p className="mt-2 text-xs text-steel">
              * Przejazd Decoral — osobny licznik obciążenia linii Decoral; nie wlicza się do „m² Razem”.
            </p>
          </div>
        ) : !isLoading ? (
          <div className="mt-6 rounded-3xl border border-dashed border-line bg-mist px-6 py-10 text-center text-sm text-steel">
            Brak danych dla miesiąca {MONTHS_PL[anchor.month]} {anchor.year}.
          </div>
        ) : null}
      </section>

      {cycleTimeStats && cycleTimeStats.orders_count > 0 ? (
        <section className="rounded-[2rem] border border-white/70 bg-white/80 p-6 shadow-panel backdrop-blur sm:p-8">
          <div className="mb-6">
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-accent">Wąskie gardła</p>
            <h2 className="mt-1 text-3xl font-semibold text-ink sm:text-4xl">Czasy etapów</h2>
            <p className="mt-2 text-sm text-steel">
              Średni czas aktywnej pracy na etapie (od rozpoczęcia do zakończenia ostatniego przejścia) oraz
              średnie oczekiwanie w kolejce przed rozpoczęciem etapu, dla {cycleTimeStats.orders_count}{" "}
              {cycleTimeStats.orders_count === 1 ? "zlecenia spakowanego" : "zleceń spakowanych"} w tym miesiącu.
            </p>
          </div>

          {cycleTimeStats.overall_average_seconds !== null ? (
            <div className="mb-6 inline-flex flex-col rounded-2xl border border-line bg-mist px-5 py-3">
              <span className="text-xs font-semibold uppercase tracking-[0.1em] text-steel">
                Średni czas realizacji (od 1. etapu do pakowania)
              </span>
              <span className="mt-1 text-2xl font-semibold text-ink">
                {formatDuration(cycleTimeStats.overall_average_seconds)}
              </span>
            </div>
          ) : null}

          <div className="flex flex-col gap-4">
            <BarChart
              title="Średni czas pracy na etapie — minuty"
              unit="min"
              decimals={1}
              barClassName="bg-teal-500"
              plotHeight={320}
              data={buildCycleTimePoints(cycleTimeStats)}
            />
            {buildWaitTimePoints(cycleTimeStats).length > 0 ? (
              <BarChart
                title="Średnie oczekiwanie przed etapem — minuty"
                unit="min"
                decimals={1}
                barClassName="bg-amber-500"
                plotHeight={320}
                data={buildWaitTimePoints(cycleTimeStats)}
              />
            ) : null}
          </div>

          <div className="mt-6 overflow-x-auto rounded-3xl border border-line bg-white">
            <table className="w-full min-w-[560px] text-sm">
              <thead>
                <tr className="border-b border-line bg-mist text-xs font-semibold uppercase tracking-[0.1em] text-steel">
                  <th className="px-5 py-3 text-left">Etap</th>
                  <th className="px-4 py-3 text-right" title="Średni czas oczekiwania w kolejce przed rozpoczęciem etapu">
                    Oczekiwanie przed
                  </th>
                  <th className="px-4 py-3 text-right">Średni czas pracy</th>
                  <th className="px-4 py-3 text-right">Zleceń</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {cycleTimeStats.stages.map((stage) => (
                  <tr key={stage.stage} className="text-ink hover:bg-mist/40">
                    <td className="px-5 py-3 font-medium">{stage.stage_label}</td>
                    <td className="px-4 py-3 text-right text-steel">
                      {stage.average_wait_before_seconds !== null ? formatDuration(stage.average_wait_before_seconds) : "—"}
                    </td>
                    <td className="px-4 py-3 text-right font-semibold">{formatDuration(stage.average_seconds)}</td>
                    <td className="px-4 py-3 text-right text-steel">{stage.orders_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}
    </main>
  );
}
