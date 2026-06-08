import { useState } from "react";
import { fetchThroughputStats } from "../api/managerApi";
import type { ThroughputStats } from "../types/manager";

export function StatystykiPage() {
  const [throughputStats, setThroughputStats] = useState<ThroughputStats | null>(null);
  const [dateFrom, setDateFrom] = useState(() => {
    const d = new Date();
    d.setDate(d.getDate() - 29);
    return d.toISOString().slice(0, 10);
  });
  const [dateTo, setDateTo] = useState(() => new Date().toISOString().slice(0, 10));
  const [groupBy, setGroupBy] = useState<"day" | "week" | "month">("day");
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  async function handleLoad() {
    setIsLoading(true);
    setErrorMessage(null);
    try {
      const stats = await fetchThroughputStats(dateFrom, dateTo, groupBy);
      setThroughputStats(stats);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Nie udało się pobrać statystyk");
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-7xl flex-col gap-6 px-4 py-8 sm:px-6 lg:px-8">
      <section className="rounded-[2rem] border border-white/70 bg-white/80 p-6 shadow-panel backdrop-blur sm:p-8">
        <div className="mb-6">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-accent">Produkcja</p>
          <h2 className="mt-1 text-3xl font-semibold text-ink sm:text-4xl">Przepustowość</h2>
          <p className="mt-2 text-sm text-steel">Zrealizowane m² i sztuki poprawek według daty zakończenia pakowania.</p>
        </div>

        <div className="flex flex-wrap items-end gap-3">
          <div className="flex flex-col gap-1">
            <label className="text-xs font-semibold uppercase tracking-[0.12em] text-steel">Od</label>
            <input
              type="date"
              value={dateFrom}
              onChange={(e) => setDateFrom(e.target.value)}
              className="rounded-2xl border border-line bg-mist/40 px-4 py-2 text-sm text-ink focus:border-accent focus:outline-none"
            />
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-xs font-semibold uppercase tracking-[0.12em] text-steel">Do</label>
            <input
              type="date"
              value={dateTo}
              onChange={(e) => setDateTo(e.target.value)}
              className="rounded-2xl border border-line bg-mist/40 px-4 py-2 text-sm text-ink focus:border-accent focus:outline-none"
            />
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-xs font-semibold uppercase tracking-[0.12em] text-steel">Grupowanie</label>
            <div className="inline-flex rounded-2xl border border-line bg-mist p-1 gap-1">
              {(["day", "week", "month"] as const).map((g) => (
                <button
                  key={g}
                  type="button"
                  onClick={() => setGroupBy(g)}
                  className={[
                    "rounded-xl px-3 py-1.5 text-xs font-medium transition",
                    groupBy === g ? "bg-white text-ink shadow-sm" : "text-steel hover:text-accent",
                  ].join(" ")}
                >
                  {g === "day" ? "Dzień" : g === "week" ? "Tydzień" : "Miesiąc"}
                </button>
              ))}
            </div>
          </div>
          <button
            type="button"
            onClick={() => void handleLoad()}
            disabled={isLoading}
            className="inline-flex items-center justify-center rounded-full bg-accent px-5 py-2.5 text-sm font-medium text-white transition hover:bg-teal-700 disabled:opacity-60"
          >
            {isLoading ? "Ładowanie…" : "Pokaż"}
          </button>
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

            <div className="overflow-x-auto rounded-3xl border border-line bg-white">
              <table className="w-full min-w-[640px] text-sm">
                <thead>
                  <tr className="border-b border-line bg-mist text-xs font-semibold uppercase tracking-[0.1em] text-steel">
                    <th className="px-5 py-3 text-left">Okres</th>
                    <th className="px-4 py-3 text-right">m² Ręczna</th>
                    <th className="px-4 py-3 text-right">m² Automat</th>
                    <th className="px-4 py-3 text-right">m² Decoral</th>
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
            Wybierz zakres dat i kliknij „Pokaż" aby załadować dane.
          </div>
        ) : null}
      </section>
    </main>
  );
}
