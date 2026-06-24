import { useEffect, useState } from "react";
import { fetchMultiDayPlan } from "../api/managerApi";
import type { MultiDayPlan, OrderPlacement, PlannedDay } from "../types/manager";

// Read-only multi-day capacity board (N49-9, first cut): the AUTOMATIC line's planned work laid across
// the next working days — each day a column filling toward its floor/ceiling, orders in the backend's
// light→dark sweep order, with below-floor / at-risk-deadline / paint flags. Drag-between-days and
// pin/urgent (NA49.K) are a deliberate follow-up (they need a backend mutate + migration); this surface
// renders what the planner derives so the manager can see the shape of the week at a glance.

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
  const [plan, setPlan] = useState<MultiDayPlan | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchMultiDayPlan("AUTOMATIC", 3)
      .then((result) => {
        if (!cancelled) setPlan(result);
      })
      .catch((caught) => {
        if (!cancelled) setError(caught instanceof Error ? caught.message : "Nie udało się pobrać planu");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (error) {
    return (
      <section className="rounded-2xl border border-rose-200 bg-rose-50 px-5 py-4 text-sm text-rose-700">{error}</section>
    );
  }
  if (!plan) return null;

  const hasWork = plan.days.some((day) => day.placements.length > 0);

  return (
    <section className="rounded-[2rem] border border-white/70 bg-white/80 p-6 shadow-panel backdrop-blur sm:p-8">
      <div className="mb-4">
        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-accent">Automat</p>
        <h3 className="mt-1 text-2xl font-semibold text-ink">Plan wielodniowy</h3>
        <p className="mt-2 text-sm text-steel">
          Zaplanowana praca automatu rozłożona na kolejne dni robocze — każda kolumna wypełnia się do
          progu zysku i limitu kabiny, w kolejności od jasnych do ciemnych kolorów. Terminy są twarde:
          zlecenia po terminie i z brakiem farby są oznaczone na czerwono.
        </p>
        {plan.infeasible_order_ids.length > 0 ? (
          <p className="mt-2 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-2 text-sm font-semibold text-rose-700">
            {plan.infeasible_order_ids.length} zleceń nie zdąży na termin w tym oknie planowania.
          </p>
        ) : null}
      </div>
      {hasWork ? (
        <div className="flex gap-3 overflow-x-auto pb-2">
          {plan.days.map((day) => (
            <DayColumn key={day.day_index} day={day} />
          ))}
        </div>
      ) : (
        <div className="rounded-3xl border border-dashed border-line bg-mist px-6 py-10 text-center text-sm text-steel">
          Brak zaplanowanej pracy na automacie.
        </div>
      )}
    </section>
  );
}
