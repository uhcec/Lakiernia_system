import { useEffect, useState } from "react";
import { ChevronLeft, ChevronRight, Plus } from "lucide-react";
import {
  createEmployee,
  fetchEmployees,
  fetchOperatorStats,
  fetchPresenceHistory,
  updateEmployee,
} from "../api/employeesApi";
import type { Employee, OperatorStats, PresenceHistory } from "../types/employees";

const MONTHS_PL = [
  "Styczeń", "Luty", "Marzec", "Kwiecień", "Maj", "Czerwiec",
  "Lipiec", "Sierpień", "Wrzesień", "Październik", "Listopad", "Grudzień",
];

const STATION_LABELS_PL: Record<string, string> = {
  SURFACE_PREPARATION: "Przygotowanie",
  HANGING: "Zawieszanie",
  MANUAL_PRODUCTION: "Produkcja ręczna",
  AUTOMATIC_PRODUCTION: "Produkcja automat",
  PACKING: "Pakowanie",
  DECORAL_PRODUCTION: "Produkcja Decoral",
  OFFICE: "Biuro",
  MANAGER: "Kierownik",
};

type MonthAnchor = { year: number; month: number };

function monthRange(anchor: MonthAnchor): { from: string; to: string } {
  const from = new Date(Date.UTC(anchor.year, anchor.month, 1)).toISOString().slice(0, 10);
  const to = new Date(Date.UTC(anchor.year, anchor.month + 1, 0)).toISOString().slice(0, 10);
  return { from, to };
}

function currentMonthAnchor(): MonthAnchor {
  const now = new Date();
  return { year: now.getFullYear(), month: now.getMonth() };
}

function formatHours(hours: number): string {
  return `${hours.toLocaleString("pl-PL", { maximumFractionDigits: 1 })} h`;
}

function formatDateTime(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString("pl-PL", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
}

export function EmployeesPage() {
  const [employees, setEmployees] = useState<Employee[]>([]);
  const [anchor, setAnchor] = useState<MonthAnchor>(currentMonthAnchor);
  const [stats, setStats] = useState<OperatorStats | null>(null);
  const [history, setHistory] = useState<PresenceHistory | null>(null);
  const [newName, setNewName] = useState("");
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editingName, setEditingName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const today = currentMonthAnchor();
  const isCurrentMonth = anchor.year === today.year && anchor.month === today.month;

  async function reloadEmployees() {
    setEmployees(await fetchEmployees(true));
  }

  useEffect(() => {
    reloadEmployees().catch((e) => setError(e instanceof Error ? e.message : "Błąd ładowania pracowników"));
  }, []);

  useEffect(() => {
    const { from, to } = monthRange(anchor);
    let cancelled = false;
    Promise.all([fetchOperatorStats(from, to), fetchPresenceHistory(from, to)])
      .then(([s, h]) => {
        if (cancelled) return;
        setStats(s);
        setHistory(h);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : "Błąd ładowania statystyk");
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

  async function withBusy(action: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await action();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Operacja nie powiodła się");
    } finally {
      setBusy(false);
    }
  }

  const addEmployee = () => {
    const name = newName.trim();
    if (!name) return;
    void withBusy(async () => {
      await createEmployee(name);
      setNewName("");
      await reloadEmployees();
    });
  };

  const saveRename = (id: number) => {
    const name = editingName.trim();
    if (!name) return;
    void withBusy(async () => {
      await updateEmployee(id, { full_name: name });
      setEditingId(null);
      await reloadEmployees();
    });
  };

  const toggleActive = (employee: Employee) =>
    void withBusy(async () => {
      await updateEmployee(employee.id, { is_active: !employee.is_active });
      await reloadEmployees();
    });

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-7xl flex-col gap-6 px-4 py-8 sm:px-6 lg:px-8">
      {error ? (
        <div className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</div>
      ) : null}

      {/* Employee administration */}
      <section className="rounded-[2rem] border border-white/70 bg-white/80 p-6 shadow-panel backdrop-blur sm:p-8">
        <div className="mb-4">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-accent">Kadry</p>
          <h2 className="mt-1 text-3xl font-semibold text-ink sm:text-4xl">Pracownicy</h2>
          <p className="mt-2 text-sm text-steel">
            Lista pracowników fabryki (obsada stanowisk, nie konta logowania). Dodawaj, zmieniaj nazwy i
            dezaktywuj — dezaktywacja wymeldowuje pracownika ze wszystkich stanowisk.
          </p>
        </div>

        <div className="mb-5 flex flex-wrap items-center gap-2">
          <input
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && addEmployee()}
            placeholder="Imię i nazwisko"
            className="min-w-[220px] flex-1 rounded-xl border border-line bg-white px-3 py-2 text-sm text-ink focus:border-accent focus:outline-none"
          />
          <button
            type="button"
            onClick={addEmployee}
            disabled={busy || !newName.trim()}
            className="inline-flex items-center gap-2 rounded-full bg-accent px-4 py-2 text-sm font-semibold text-white transition hover:brightness-110 disabled:opacity-50"
          >
            <Plus className="h-4 w-4" /> Dodaj pracownika
          </button>
        </div>

        <div className="overflow-x-auto rounded-3xl border border-line bg-white">
          <table className="w-full min-w-[560px] text-sm">
            <thead>
              <tr className="border-b border-line bg-mist text-xs font-semibold uppercase tracking-[0.1em] text-steel">
                <th className="px-5 py-3 text-left">Pracownik</th>
                <th className="px-4 py-3 text-left">Status</th>
                <th className="px-4 py-3 text-right">Akcje</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {employees.map((employee) => (
                <tr key={employee.id} className={employee.is_active ? "text-ink" : "text-steel"}>
                  <td className="px-5 py-3 font-medium">
                    {editingId === employee.id ? (
                      <input
                        value={editingName}
                        onChange={(e) => setEditingName(e.target.value)}
                        onKeyDown={(e) => e.key === "Enter" && saveRename(employee.id)}
                        autoFocus
                        className="w-full max-w-[280px] rounded-lg border border-accent px-2 py-1 text-sm focus:outline-none"
                      />
                    ) : (
                      employee.full_name
                    )}
                  </td>
                  <td className="px-4 py-3">
                    {employee.is_active ? (
                      <span className="inline-flex rounded-full bg-emerald-100 px-2.5 py-0.5 text-xs font-semibold text-emerald-700">
                        Aktywny
                      </span>
                    ) : (
                      <span className="inline-flex rounded-full bg-line px-2.5 py-0.5 text-xs font-semibold text-steel">
                        Nieaktywny
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <div className="inline-flex gap-2">
                      {editingId === employee.id ? (
                        <>
                          <button
                            type="button"
                            onClick={() => saveRename(employee.id)}
                            disabled={busy}
                            className="rounded-full border border-accent px-3 py-1 text-xs font-medium text-accent hover:bg-accent/10 disabled:opacity-50"
                          >
                            Zapisz
                          </button>
                          <button
                            type="button"
                            onClick={() => setEditingId(null)}
                            className="rounded-full border border-line px-3 py-1 text-xs font-medium text-steel hover:border-steel"
                          >
                            Anuluj
                          </button>
                        </>
                      ) : (
                        <>
                          <button
                            type="button"
                            onClick={() => {
                              setEditingId(employee.id);
                              setEditingName(employee.full_name);
                            }}
                            className="rounded-full border border-line px-3 py-1 text-xs font-medium text-steel hover:border-accent hover:text-accent"
                          >
                            Zmień nazwę
                          </button>
                          <button
                            type="button"
                            onClick={() => toggleActive(employee)}
                            disabled={busy}
                            className="rounded-full border border-line px-3 py-1 text-xs font-medium text-steel hover:border-accent hover:text-accent disabled:opacity-50"
                          >
                            {employee.is_active ? "Dezaktywuj" : "Aktywuj"}
                          </button>
                        </>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
              {employees.length === 0 ? (
                <tr>
                  <td colSpan={3} className="px-5 py-10 text-center text-steel">
                    Brak pracowników. Dodaj pierwszego powyżej.
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>

      {/* Month picker shared by stats + history */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="inline-flex items-center gap-1 rounded-2xl border border-line bg-mist p-1">
          <button type="button" onClick={() => shiftMonth(-1)} aria-label="Poprzedni miesiąc" className="rounded-xl p-2 text-steel transition hover:bg-white hover:text-accent">
            <ChevronLeft className="h-5 w-5" />
          </button>
          <span className="min-w-[160px] text-center text-sm font-semibold text-ink">
            {MONTHS_PL[anchor.month]} {anchor.year}
          </span>
          <button type="button" onClick={() => shiftMonth(1)} disabled={isCurrentMonth} aria-label="Następny miesiąc" className="rounded-xl p-2 text-steel transition hover:bg-white hover:text-accent disabled:cursor-not-allowed disabled:opacity-40">
            <ChevronRight className="h-5 w-5" />
          </button>
        </div>
      </div>

      {/* Per-operator stats */}
      <section className="rounded-[2rem] border border-white/70 bg-white/80 p-6 shadow-panel backdrop-blur sm:p-8">
        <div className="mb-4">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-accent">Wydajność</p>
          <h2 className="mt-1 text-2xl font-semibold text-ink sm:text-3xl">Statystyki operatorów</h2>
          <p className="mt-2 text-sm text-steel">
            Wkład per pracownik w wybranym miesiącu. Każdy obecny przy akcji dostaje pełny kredyt, a zlecenie
            liczone jest raz na operatora — dlatego sumy mogą się nakładać między osobami.
          </p>
        </div>
        <div className="overflow-x-auto rounded-3xl border border-line bg-white">
          <table className="w-full min-w-[640px] text-sm">
            <thead>
              <tr className="border-b border-line bg-mist text-xs font-semibold uppercase tracking-[0.1em] text-steel">
                <th className="px-5 py-3 text-left">Pracownik</th>
                <th className="px-4 py-3 text-right">Godziny</th>
                <th className="px-4 py-3 text-right">Zlecenia</th>
                <th className="px-4 py-3 text-right">Sztuki</th>
                <th className="px-4 py-3 text-right">m²</th>
                <th className="px-4 py-3 text-right" title="Liczba akcji (przejść etapów / pakowań), w których operator był obecny">Akcje</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {(stats?.operators ?? []).map((op) => (
                <tr key={op.employee_id} className="text-ink hover:bg-mist/40">
                  <td className="px-5 py-3 font-medium">
                    {op.full_name}
                    {!op.is_active ? <span className="ml-2 text-xs text-steel">(nieaktywny)</span> : null}
                  </td>
                  <td className="px-4 py-3 text-right text-steel">{formatHours(op.hours_present)}</td>
                  <td className="px-4 py-3 text-right text-steel">{op.orders_count}</td>
                  <td className="px-4 py-3 text-right font-semibold">{op.pieces_credited}</td>
                  <td className="px-4 py-3 text-right text-steel">{op.m2_credited.toFixed(1)}</td>
                  <td className="px-4 py-3 text-right text-steel">{op.actions}</td>
                </tr>
              ))}
              {stats && stats.operators.every((o) => o.actions === 0 && o.hours_present === 0) ? (
                <tr>
                  <td colSpan={6} className="px-5 py-10 text-center text-steel">
                    Brak aktywności w tym miesiącu.
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>

      {/* Presence history */}
      <section className="rounded-[2rem] border border-white/70 bg-white/80 p-6 shadow-panel backdrop-blur sm:p-8">
        <div className="mb-4">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-accent">Obecność</p>
          <h2 className="mt-1 text-2xl font-semibold text-ink sm:text-3xl">Historia obecności</h2>
          <p className="mt-2 text-sm text-steel">Kto był na którym stanowisku i jak długo (w wybranym miesiącu).</p>
        </div>
        <div className="overflow-x-auto rounded-3xl border border-line bg-white">
          <table className="w-full min-w-[640px] text-sm">
            <thead>
              <tr className="border-b border-line bg-mist text-xs font-semibold uppercase tracking-[0.1em] text-steel">
                <th className="px-5 py-3 text-left">Pracownik</th>
                <th className="px-4 py-3 text-left">Stanowisko</th>
                <th className="px-4 py-3 text-left">Od</th>
                <th className="px-4 py-3 text-left">Do</th>
                <th className="px-4 py-3 text-right">Godziny</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {(history?.sessions ?? []).map((s, index) => (
                <tr key={index} className="text-ink hover:bg-mist/40">
                  <td className="px-5 py-3 font-medium">{s.full_name}</td>
                  <td className="px-4 py-3 text-steel">{STATION_LABELS_PL[s.station_id] ?? s.station_id}</td>
                  <td className="px-4 py-3 text-steel">{formatDateTime(s.checked_in_at)}</td>
                  <td className="px-4 py-3 text-steel">
                    {s.is_open ? <span className="text-emerald-600">na stanowisku</span> : formatDateTime(s.checked_out_at)}
                  </td>
                  <td className="px-4 py-3 text-right text-steel">{formatHours(s.hours)}</td>
                </tr>
              ))}
              {history && history.sessions.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-5 py-10 text-center text-steel">
                    Brak obecności w tym miesiącu.
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>
    </main>
  );
}
