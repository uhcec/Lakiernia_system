import { useEffect, useState } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { fetchCycleTimeStats, fetchThroughputStats } from "../api/managerApi";
import type { CycleTimeStats, ThroughputPeriod, ThroughputStats } from "../types/manager";
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

export function StatystykiPage() {
  const [anchor, setAnchor] = useState<MonthAnchor>(currentMonthAnchor);
  const [throughputStats, setThroughputStats] = useState<ThroughputStats | null>(null);
  const [cycleTimeStats, setCycleTimeStats] = useState<CycleTimeStats | null>(null);
  const [loadedParams, setLoadedParams] = useState<LoadedParams | null>(null);
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

  function shiftMonth(delta: number) {
    setAnchor((current) => {
      const d = new Date(current.year, current.month + delta, 1);
      return { year: d.getFullYear(), month: d.getMonth() };
    });
  }

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-7xl flex-col gap-6 px-4 py-8 sm:px-6 lg:px-8">
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
              <div className="mb-6 flex flex-col gap-4">
                <BarChart
                  title="Produkcja automat — m² / dzień"
                  unit="m²"
                  decimals={1}
                  barClassName="bg-accent"
                  yMax={1200}
                  yTickStep={100}
                  plotHeight={360}
                  data={buildPoints(throughputStats, loadedParams, (p) => p.m2_automatic)}
                />
                <BarChart
                  title="Produkcja ręczna — m² / dzień"
                  unit="m²"
                  decimals={1}
                  barClassName="bg-sky-500"
                  yMax={70}
                  yTickStep={10}
                  plotHeight={360}
                  data={buildPoints(throughputStats, loadedParams, (p) => p.m2_manual)}
                />
                <BarChart
                  title="Przejazd Decoral — m² / dzień"
                  unit="m²"
                  decimals={1}
                  barClassName="bg-violet-500"
                  yMax={70}
                  yTickStep={10}
                  plotHeight={360}
                  data={buildPoints(throughputStats, loadedParams, (p) => p.m2_decoral)}
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
                    <th className="px-4 py-3 text-right">m² Ręczna</th>
                    <th className="px-4 py-3 text-right">m² Automat</th>
                    <th className="px-4 py-3 text-right" title="Przejazd Decoral (etap DECORAL_PRODUCTION) — osobny licznik, liczony w dniu zakończenia powłoki Decoral; nie wlicza się do m² Razem">
                      m² Decoral (przejazd)
                    </th>
                    <th className="px-4 py-3 text-right font-bold">m² Razem</th>
                    <th className="px-4 py-3 text-right">Zlecenia</th>
                    <th className="px-4 py-3 text-right">Poprawki (szt.)</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line">
                  {throughputStats.periods.length === 0 ? (
                    <tr>
                      <td colSpan={7} className="px-5 py-10 text-center text-steel">
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
                          {period.m2_decoral > 0 ? period.m2_decoral.toFixed(1) : "—"}
                        </td>
                        <td className="px-4 py-3 text-right font-semibold">{period.m2_total.toFixed(1)}</td>
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
                        {throughputStats.totals.m2_decoral > 0 ? throughputStats.totals.m2_decoral.toFixed(1) : "—"}
                      </td>
                      <td className="px-4 py-3 text-right text-accent">
                        {throughputStats.totals.m2_total.toFixed(1)} m²
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
              Średni czas aktywnej pracy na etapie (od rozpoczęcia do zakończenia ostatniego przejścia),
              dla {cycleTimeStats.orders_count}{" "}
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

          <BarChart
            title="Średni czas na etapie — minuty"
            unit="min"
            decimals={1}
            barClassName="bg-teal-500"
            plotHeight={320}
            data={buildCycleTimePoints(cycleTimeStats)}
          />

          <div className="mt-6 overflow-x-auto rounded-3xl border border-line bg-white">
            <table className="w-full min-w-[480px] text-sm">
              <thead>
                <tr className="border-b border-line bg-mist text-xs font-semibold uppercase tracking-[0.1em] text-steel">
                  <th className="px-5 py-3 text-left">Etap</th>
                  <th className="px-4 py-3 text-right">Średni czas</th>
                  <th className="px-4 py-3 text-right">Zleceń</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {cycleTimeStats.stages.map((stage) => (
                  <tr key={stage.stage} className="text-ink hover:bg-mist/40">
                    <td className="px-5 py-3 font-medium">{stage.stage_label}</td>
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
