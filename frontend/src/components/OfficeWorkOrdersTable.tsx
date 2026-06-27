import { Calendar, Clock } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";

import type { WorkOrder } from "../types/workOrders";
import { formatDisplayOrderNumber } from "../utils/workOrderDisplay";
import { RalColorDot } from "./RalColorDot";

function stageClasses(value: WorkOrder["process_status"]["value"]): string {
  switch (value) {
    case "TO_BE_PLANNED":
      return "bg-sky-50 text-sky-700";
    case "INCOMPLETE":
      return "bg-rose-100 text-rose-700";
    case "SURFACE_PREPARATION":
      return "bg-amber-100 text-amber-800";
    case "HANGING":
      return "bg-indigo-100 text-indigo-700";
    case "PRODUCTION_MANUAL":
      return "bg-orange-100 text-orange-800";
    case "PRODUCTION_AUTOMATIC":
      return "bg-blue-100 text-blue-800";
    case "DECORAL_PRODUCTION":
      return "bg-fuchsia-100 text-fuchsia-800";
    case "PACKING":
      return "bg-violet-100 text-violet-800";
    case "WAITING_FOR_CORRECTIONS":
      return "bg-amber-200 text-amber-900";
    case "READY":
      return "bg-emerald-100 text-emerald-700";
  }
}

function formatDate(dateStr: string): string {
  return new Intl.DateTimeFormat("pl-PL", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  }).format(new Date(dateStr));
}

function getDaysLabel(dateStr: string | null): string {
  if (!dateStr) return "—";
  const dayMs = 24 * 60 * 60 * 1000;
  const days = Math.ceil((new Date(dateStr).getTime() - Date.now()) / dayMs);
  if (days < 0) return "Po terminie";
  if (days === 0) return "Dzisiaj";
  if (days === 1) return "1 dzień";
  return `${days} dni`;
}

function OfficeWorkOrderRow({ workOrder }: { workOrder: WorkOrder }) {
  const navigate = useNavigate();
  const daysLabel = getDaysLabel(workOrder.planned_pickup_date);
  const isOverdue =
    workOrder.planned_pickup_date != null &&
    new Date(workOrder.planned_pickup_date).getTime() < Date.now();

  return (
    <div
      className="flex min-w-0 cursor-pointer items-center rounded-2xl bg-white ring-1 ring-brand-line/60 transition hover:bg-brand-soft/50"
      onClick={() => navigate(`/zlecenia/${workOrder.id}`)}
    >
      {/* ZLECENIE */}
      <div className="w-52 flex-none px-5 py-3.5">
        <p className={`text-lg font-bold leading-tight ${workOrder.completed_quantity > 0 && workOrder.completed_quantity < workOrder.total_quantity ? "text-amber-700" : "text-brand-ink"}`}>
          {formatDisplayOrderNumber(workOrder)}
        </p>
        <p className="mt-0.5 truncate text-sm leading-snug text-brand-muted">
          {workOrder.customer_name}
        </p>
      </div>

      {/* RAL */}
      <div className="w-32 flex-none px-4 py-3.5">
        <div className="flex items-center gap-2">
          <RalColorDot ralCode={workOrder.ral_code} />
          <span className="text-sm font-semibold text-brand-ink">{workOrder.ral_code}</span>
        </div>
      </div>

      {/* POWIERZCHNIA */}
      <div className="w-32 flex-none px-4 py-3.5">
        <span className="text-sm font-semibold text-brand-ink">
          {workOrder.total_area_m2 != null
            ? `${workOrder.total_area_m2.toLocaleString("pl-PL")} m²`
            : "—"}
        </span>
      </div>

      {/* ETAP */}
      <div className="w-48 flex-none space-y-1.5 px-4 py-3.5">
        <span
          className={[
            "inline-flex rounded-full px-3 py-0.5 text-xs font-semibold",
            stageClasses(workOrder.process_status.value),
          ].join(" ")}
        >
          {workOrder.process_status.label}
        </span>
        <p className="text-xs text-brand-muted">
          {workOrder.production_type?.label ?? "Oczekuje na przypisanie"}
        </p>
      </div>

      {/* STATUS */}
      <div className="w-48 flex-none space-y-1.5 px-4 py-3.5">
        <p className="text-sm font-semibold text-brand-ink">
          {workOrder.completed_quantity} / {workOrder.total_quantity} szt.
        </p>
        <div className="flex flex-wrap gap-1.5">
          {workOrder.process_status.value === "READY" ? (
            <>
              <span className="inline-flex rounded-full bg-emerald-100 px-2.5 py-0.5 text-[11px] font-semibold text-emerald-700">
                Gotowe
              </span>
              <span className={[
                "inline-flex rounded-full px-2.5 py-0.5 text-[11px] font-semibold",
                workOrder.is_released_to_client
                  ? "bg-emerald-100 text-emerald-700"
                  : "bg-brand-surface text-brand-muted",
              ].join(" ")}>
                {workOrder.is_released_to_client ? "Wydane" : "Do wydania"}
              </span>
            </>
          ) : (
            <>
              <span className="inline-flex rounded-full bg-brand-surface px-2.5 py-0.5 text-[11px] font-semibold text-brand-muted">
                Gotowe: {workOrder.completed_quantity}
              </span>
              {workOrder.current_active_quantity > 0 && (
                <span className="inline-flex rounded-full bg-amber-50 px-2.5 py-0.5 text-[11px] font-semibold text-amber-700">
                  Aktywne: {workOrder.current_active_quantity}
                </span>
              )}
            </>
          )}
        </div>
      </div>

      {/* TERMIN */}
      <div className="min-w-[136px] flex-1 space-y-1.5 px-4 py-3.5">
        {workOrder.planned_pickup_date ? (
          <>
            <div className="flex items-center gap-1.5 text-sm font-semibold text-brand-ink">
              <Calendar className="h-4 w-4 flex-none text-brand-muted" />
              {formatDate(workOrder.planned_pickup_date)}
            </div>
            <div
              className={[
                "flex items-center gap-1.5 text-xs",
                isOverdue ? "text-rose-600" : "text-brand-muted",
              ].join(" ")}
            >
              <Clock className="h-3.5 w-3.5 flex-none" />
              {daysLabel}
            </div>
          </>
        ) : (
          <span className="text-sm text-brand-muted">—</span>
        )}
      </div>

      {/* MENU */}
      <div className="flex-none px-4 py-3.5">
        <Link
          to={`/zlecenia/${workOrder.id}`}
          onClick={(e) => e.stopPropagation()}
          className="inline-flex h-8 w-8 items-center justify-center rounded-full bg-brand-surface text-sm font-bold text-brand-muted transition hover:text-brand-ink"
          aria-label={`Szczegóły ${workOrder.order_number}`}
        >
          ⋮
        </Link>
      </div>
    </div>
  );
}

const COLUMNS = [
  { label: "Zlecenie", className: "w-52 flex-none px-5" },
  { label: "RAL", className: "w-32 flex-none px-4" },
  { label: "Powierzchnia", className: "w-32 flex-none pl-0 pr-4" },
  { label: "Etap", className: "w-48 flex-none px-4" },
  { label: "Status", className: "w-48 flex-none px-4" },
  { label: "Termin", className: "min-w-[136px] flex-1 px-4" },
];

export function OfficeWorkOrdersTable({ workOrders }: { workOrders: WorkOrder[] }) {
  return (
    <div className="overflow-x-auto">
      <div className="min-w-[900px] space-y-2">
        {/* Column headers */}
        <div className="flex items-center px-1 pb-1">
          {COLUMNS.map((col) => (
            <div key={col.label} className={col.className}>
              <span className="text-xs font-bold uppercase tracking-[0.14em] text-brand-muted">
                {col.label}
              </span>
            </div>
          ))}
          <div className="w-16 flex-none" />
        </div>

        {/* Rows */}
        <div className="space-y-2">
          {workOrders.map((workOrder) => (
            <OfficeWorkOrderRow key={workOrder.id} workOrder={workOrder} />
          ))}
        </div>
      </div>
    </div>
  );
}
