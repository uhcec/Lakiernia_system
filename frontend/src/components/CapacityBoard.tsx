import { useCallback, useEffect, useRef, useState } from "react";
import { fetchMultiDayPlan } from "../api/managerApi";
import { STATION_POLL_INTERVAL_MS, usePolling } from "../hooks/usePolling";
import type { MultiDayPlan, OrderPlacement, PlannedDay } from "../types/manager";
import type { ProductionTypeValue } from "../types/workOrders";

// Read-only multi-day capacity board (N49-9): a line's planned work laid across the next working days —
// each day a column filling toward its floor/ceiling, orders in the backend's light→dark sweep order,
// with below-floor / at-risk-deadline / paint flags. The line is selectable (MANUAL / AUTOMATIC, NA55)
// and the board refreshes on the station poll cadence so it tracks work planned on other devices.
// Drag-between-days and pin/urgent (NA49.K) are a deliberate follow-up (they need a backend mutate +
// migration); this surface renders what the planner derives so the manager sees the shape of the week.

const LINE_OPTIONS: { value: ProductionTypeValue; label: string }[] = [
  { value: "AUTOMATIC", label: "Automat" },
  { value: "MANUAL", label: "Ręczna" },
];

function formatDayHeader(scheduledDate: string | null, dayIndex: number): string {
  if (!scheduledDate) return `Dzień ${dayIndex + 1}`;
  const [y, m, d] = scheduledDate.split("-");
  return `${d}.${m}.${y.slice(2)}`;
}

function fillPercent(placedM2: number, ceilingM2: number): number {
  if (ceilingM2 <= 0) return 0;
  return Math.min(100, Math.round((placedM2 / ceilingM2) * 100));
}

function floorPercent(floorM2: number, ceilingM2: number): number {
  if (ceilingM2 <= 0) return 0;
  return Math.min(100, Math.round((floorM2 / ceilingM2) * 100));
}

function PlacementRow({ placement }: { placement: OrderPlacement }) {
  const atRisk = !placement.meets_deadline;
  const paintBlocked = placement.paint_status === "BLOCKED";
  const paintWarn = placement.paint_status === "WARNING";
  return (
    <li
      className={[
        "rounded-xl border px-3 py-2 text-xs",
        atRisk || paintBlocked ? "border-rose-200 bg-rose-50" : "border-line bg-white",
      ].join(" ")}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="font-semibold text-ink">{placement.order_number}</span>
        <span className="text-steel">{placement.total_area_m2 != null ? `${Math.round(placement.total_area_m2)} m²` : "—"}</span>
      </div>
      <div className="mt-0.5 truncate text-steel">{placement.ral_code ?? "—"} · {placement.customer_name}</div>
      <div className="mt-1 flex flex-wrap gap-1">
        {atRisk ? (
          <span className="rounded-full bg-rose-100 px-2 py-0.5 text-[10px] font-semibold text-rose-700">
            {placement.days_late > 0 ? `po terminie +${placement.days_late} dn.` : "po terminie"}
          </span>
        ) : null}
        {paintBlocked ? (
          <span className="rounded-full bg-rose-100 px-2 py-0.5 text-[10px] font-semibold text-rose-700">brak farby</span>
        ) : null}
        {paintWarn ? (
          <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-semibold text-amber-700">farba na wyczerpaniu</span>
        ) : null}
      </div>
    </li>
  );
}

function DayColumn({ day }: { day: PlannedDay }) {
  const fill = fillPercent(day.placed_m2, day.net_ceiling_m2);
  const floorLine = floorPercent(day.floor_m2, day.net_ceiling_m2);
  return (
    <div className="flex w-60 shrink-0 flex-col rounded-2xl border border-line bg-mist/40 p-3">
      <div className="flex items-baseline justify-between">
        <span className="text-sm font-semibold text-ink">{formatDayHeader(day.scheduled_date, day.day_index)}</span>
        <span className="text-[10px] uppercase tracking-wide text-steel">{day.shift_length === "LONG" ? "dług." : "krót."}</span>
      </div>
      <div className="mt-1 text-xs text-steel">
        <span className={day.below_floor ? "font-semibold text-amber-700" : "font-semibold text-emerald-700"}>
          {Math.round(day.placed_m2)} m²
        </span>{" "}
        / próg {Math.round(day.floor_m2)}
      </div>
      {/* Fill bar: placed m² toward the net ceiling, with the floor marked as a dashed line. */}
      <div className="relative mt-2 h-2 w-full rounded-full bg-white">
        <div
          className={["h-2 rounded-full", day.over_ceiling ? "bg-rose-500" : day.below_floor ? "bg-amber-400" : "bg-emerald-500"].join(" ")}
          style={{ width: `${fill}%` }}
        />
        <div className="absolute top-[-2px] h-3 w-px bg-ink/50" style={{ left: `${floorLine}%` }} title="Próg zysku" />
      </div>
      <div className="mt-1 flex flex-wrap gap-1">
        {day.below_floor ? (
          <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-semibold text-amber-700">poniżej progu</span>
        ) : null}
        {day.over_ceiling ? (
          <span className="rounded-full bg-rose-100 px-2 py-0.5 text-[10px] font-semibold text-rose-700">ponad limit</span>
        ) : null}
        {day.changeover_count > 0 ? (
          <span className="rounded-full bg-white px-2 py-0.5 text-[10px] text-steel">{day.changeover_count} zmian koloru</span>
        ) : null}
      </div>
      <ul className="mt-2 flex flex-col gap-1.5">
        {day.placements.map((placement) => (
          <PlacementRow key={placement.work_order_id} placement={placement} />
        ))}
      </ul>
    </div>
  );
}

export function CapacityBoard() {
  const [line, setLine] = useState<ProductionTypeValue>("AUTOMATIC");
  const [plan, setPlan] = useState<MultiDayPlan | null>(null);
  const [error, setError] = useState<string | null>(null);
  // The line currently requested, so a response that arrives after the manager switched lines is ignored.
  const lineRef = useRef(line);
  lineRef.current = line;

  const load = useCallback(() => {
    const requested = lineRef.current;
    fetchMultiDayPlan(requested, 3)
      .then((result) => {
        if (lineRef.current !== requested) return;
        setPlan(result);
        setError(null);
      })
      .catch((caught) => {
        if (lineRef.current !== requested) return;
        setError(caught instanceof Error ? caught.message : "Nie udało się pobrać planu");
      });
  }, []);

  // Fetch immediately when the selected line changes (drop the old plan so stale data never shows).
  useEffect(() => {
    setPlan(null);
    setError(null);
    load();
  }, [line, load]);

  // Keep the board current with work planned on other devices (same cadence as the station boards).
  usePolling(load, STATION_POLL_INTERVAL_MS);

  const hasWork = plan?.days.some((day) => day.placements.length > 0) ?? false;
  const lineLabel = LINE_OPTIONS.find((option) => option.value === line)?.label ?? "";

  return (
    <section className="rounded-[2rem] border border-white/70 bg-white/80 p-6 shadow-panel backdrop-blur sm:p-8">
      <div className="mb-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-accent">{lineLabel}</p>
            <h3 className="mt-1 text-2xl font-semibold text-ink">Plan wielodniowy</h3>
          </div>
          <div className="inline-flex rounded-full border border-line bg-mist p-1" role="group" aria-label="Linia">
            {LINE_OPTIONS.map((option) => (
              <button
                key={option.value}
                type="button"
                onClick={() => setLine(option.value)}
                aria-pressed={line === option.value}
                className={[
                  "rounded-full px-4 py-1 text-sm font-semibold transition",
                  line === option.value ? "bg-white text-ink shadow-sm" : "text-steel hover:text-ink",
                ].join(" ")}
              >
                {option.label}
              </button>
            ))}
          </div>
        </div>
        <p className="mt-2 text-sm text-steel">
          Zaplanowana praca linii rozłożona na kolejne dni robocze — każda kolumna wypełnia się do progu
          zysku i limitu kabiny, w kolejności od jasnych do ciemnych kolorów. Terminy są twarde: zlecenia
          po terminie i z brakiem farby są oznaczone na czerwono.
        </p>
        {plan && plan.infeasible_order_ids.length > 0 ? (
          <p className="mt-2 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-2 text-sm font-semibold text-rose-700">
            {plan.infeasible_order_ids.length} zleceń nie zdąży na termin w tym oknie planowania.
          </p>
        ) : null}
      </div>
      {error ? (
        <div className="rounded-2xl border border-rose-200 bg-rose-50 px-5 py-4 text-sm text-rose-700">{error}</div>
      ) : !plan ? null : hasWork ? (
        <div className="flex gap-3 overflow-x-auto pb-2">
          {plan.days.map((day) => (
            <DayColumn key={day.day_index} day={day} />
          ))}
        </div>
      ) : (
        <div className="rounded-3xl border border-dashed border-line bg-mist px-6 py-10 text-center text-sm text-steel">
          Brak zaplanowanej pracy na tej linii.
        </div>
      )}
    </section>
  );
}
