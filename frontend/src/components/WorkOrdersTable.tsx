import { Link, useNavigate } from "react-router-dom";

import type { WorkOrder } from "../types/workOrders";
import {
  formatWorkOrderPrimaryInfo,
  getWorkOrderActiveCorrectionsText,
  getWorkOrderAttentionBadges,
  getWorkOrderBadgeStack,
  getWorkOrderCorrectionContextText,
  getWorkOrderDiscrepancyText,
  getHistoricalWorkOrderResultText,
  getWorkOrderProgressText,
  getWorkOrderStatusSummary,
  type DisplayBadge,
} from "../utils/workOrderDisplay";

interface WorkOrdersTableProps {
  workOrders: WorkOrder[];
}

function statusClasses(statusValue: WorkOrder["process_status"]["value"]): string {
  switch (statusValue) {
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

function badgeClasses(tone: DisplayBadge["tone"]): string {
  switch (tone) {
    case "info":
      return "bg-sky-50 text-sky-700";
    case "warning":
      return "bg-amber-100 text-amber-800";
    case "success":
      return "bg-emerald-100 text-emerald-700";
    case "accent":
      return "bg-violet-100 text-violet-700";
    case "danger":
      return "bg-rose-100 text-rose-700";
    case "neutral":
      return "bg-brand-surface text-brand-muted";
  }
}

function formatDateLabel(dateValue: string | null): string {
  if (!dateValue) {
    return "-";
  }

  const parsedDate = new Date(dateValue);
  if (Number.isNaN(parsedDate.getTime())) {
    return dateValue;
  }

  return new Intl.DateTimeFormat("pl-PL", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  }).format(parsedDate);
}

function getTechnologyLine(workOrder: WorkOrder): string {
  const parts = [workOrder.ral_code, workOrder.coating_type.label];

  if (workOrder.is_ocynk) {
    parts.push("Ocynk");
  }

  return parts.filter(Boolean).join(" · ");
}

function getTermMeta(workOrder: WorkOrder): string {
  if (!workOrder.planned_pickup_date) {
    return "-";
  }

  if (workOrder.process_status.value === "READY") {
    return workOrder.is_released_to_client ? "Wydane" : "Gotowe do wydania";
  }

  const dayMs = 24 * 60 * 60 * 1000;
  const diffDays = Math.ceil((new Date(workOrder.planned_pickup_date).getTime() - Date.now()) / dayMs);

  if (diffDays < 0) {
    return "Po terminie";
  }

  if (diffDays === 0) {
    return "Dzisiaj";
  }

  if (diffDays === 1) {
    return "1 dzień";
  }

  return `${diffDays} dni`;
}

function getTermMetaClass(workOrder: WorkOrder): string {
  const meta = getTermMeta(workOrder);

  if (meta === "Po terminie" || meta === "Dzisiaj") {
    return "text-rose-600";
  }

  return "text-brand-muted";
}

export function WorkOrdersTable({ workOrders }: WorkOrdersTableProps) {
  const navigate = useNavigate();

  function renderQuantitySummary(workOrder: WorkOrder) {
    const totalQuantity = workOrder.total_quantity ?? null;
    const completedQuantity = workOrder.completed_quantity ?? null;
    const activeQuantity = workOrder.current_active_quantity ?? null;

    if (totalQuantity === null || completedQuantity === null || activeQuantity === null) {
      return <span className="text-steel">—</span>;
    }

    if (workOrder.process_status.value === "READY") {
      return (
        <div className="space-y-2">
          <p className="text-sm font-semibold text-ink">{getHistoricalWorkOrderResultText(workOrder)}</p>
          <span className="inline-flex rounded-full bg-emerald-100 px-3 py-1 text-xs font-semibold text-emerald-700">
            Gotowe
          </span>
        </div>
      );
    }

    return (
      <div className="space-y-2">
        <p className="text-sm font-semibold text-ink">{getWorkOrderProgressText(workOrder)}</p>
        <p className="text-xs text-steel">Gotowe: {completedQuantity} szt. · Aktywne: {activeQuantity} szt.</p>
        {getWorkOrderActiveCorrectionsText(workOrder) ? (
          <span className="inline-flex rounded-full bg-rose-100 px-3 py-1 text-xs font-semibold text-rose-700">
            {getWorkOrderActiveCorrectionsText(workOrder)}
          </span>
        ) : null}
        {getWorkOrderDiscrepancyText(workOrder) ? (
          <p className="text-xs font-medium text-amber-700">{getWorkOrderDiscrepancyText(workOrder)}</p>
        ) : null}
        {activeQuantity > 0 ? (
          <span className="inline-flex rounded-full bg-amber-100 px-3 py-1 text-xs font-semibold text-amber-800">
            Aktywne: {activeQuantity}
          </span>
        ) : (
          <span className="inline-flex rounded-full bg-emerald-100 px-3 py-1 text-xs font-semibold text-emerald-700">
            Gotowe
          </span>
        )}
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-[1.8rem] border border-brand-line/70 bg-white shadow-panel">
      <div className="overflow-x-auto">
        <table className="min-w-[1080px] border-collapse text-left text-sm">
          <thead className="bg-brand-soft text-brand-muted">
            <tr>
              <th className="px-5 py-4 text-xs font-bold uppercase tracking-[0.14em]">Nr zlecenia</th>
              <th className="px-5 py-4 text-xs font-bold uppercase tracking-[0.14em]">Klient</th>
              <th className="px-5 py-4 text-xs font-bold uppercase tracking-[0.14em]">RAL</th>
              <th className="px-5 py-4 text-xs font-bold uppercase tracking-[0.14em]">Powierzchnia</th>
              <th className="px-5 py-4 text-xs font-bold uppercase tracking-[0.14em]">Etap</th>
              <th className="px-5 py-4 text-xs font-bold uppercase tracking-[0.14em]">Status</th>
              <th className="px-5 py-4 text-xs font-bold uppercase tracking-[0.14em]">Termin</th>
              <th className="px-5 py-4 text-right text-xs font-bold uppercase tracking-[0.14em]">Więcej</th>
            </tr>
          </thead>
          <tbody>
            {workOrders.map((workOrder) => (
              <tr
                key={workOrder.id}
                className={[
                  "cursor-pointer border-t border-brand-line/70 text-brand-ink transition hover:bg-brand-soft/80",
                  workOrder.is_correction ? "bg-amber-50/40" : "",
                  getWorkOrderAttentionBadges(workOrder).length > 0 ? "ring-1 ring-inset ring-amber-200" : "",
                ].join(" ")}
                onClick={() => navigate(`/zlecenia/${workOrder.id}`)}
              >
                <td className="px-5 py-4 font-semibold align-top">
                  <div className="space-y-2">
                    <div className="text-base font-bold text-brand-ink">{workOrder.order_number}</div>
                    {workOrder.external_order_number ? (
                      <div className="text-xs font-medium text-brand-muted">Zewn.: {workOrder.external_order_number}</div>
                    ) : null}
                    <div className="flex flex-wrap gap-2">
                      {[...getWorkOrderBadgeStack(workOrder), ...getWorkOrderAttentionBadges(workOrder)].map((badge) => (
                        <span
                          key={`${workOrder.id}-${badge.label}`}
                          className={["inline-flex rounded-full px-3 py-1 text-[11px] font-semibold", badgeClasses(badge.tone)].join(" ")}
                        >
                          {badge.label}
                        </span>
                      ))}
                    </div>
                  </div>
                </td>
                <td className="px-5 py-4 align-top text-brand-muted">
                  <div className="space-y-1">
                    <p className="font-semibold text-brand-ink">{workOrder.customer_name}</p>
                    <p>{workOrder.order_number}</p>
                    {getWorkOrderCorrectionContextText(workOrder) ? (
                      <p className="text-amber-700">{getWorkOrderCorrectionContextText(workOrder)}</p>
                    ) : null}
                  </div>
                </td>
                <td className="px-5 py-4 align-top text-brand-muted">
                  <div className="space-y-2">
                    <div className="flex items-center gap-2">
                      <span className="inline-flex h-3.5 w-3.5 rounded-full border border-brand-line bg-brand-900/85" />
                      <p className="font-semibold text-brand-ink">{workOrder.ral_code || workOrder.paint_code || "Bez koloru"}</p>
                    </div>
                    <p>{getTechnologyLine(workOrder)}</p>
                  </div>
                </td>
                <td className="px-5 py-4 align-top text-brand-muted">
                  <div className="space-y-2">
                    <p className="font-semibold text-brand-ink">{workOrder.total_area_m2?.toLocaleString("pl-PL") ?? "-"} m²</p>
                    <p>{formatWorkOrderPrimaryInfo(workOrder).split(" · ").slice(2, 3).join("")}</p>
                  </div>
                </td>
                <td className="px-5 py-4 align-top text-brand-muted">
                  <div className="space-y-2">
                    <p className="font-semibold text-brand-ink">{getWorkOrderStatusSummary(workOrder)}</p>
                    <p>{workOrder.production_type?.label ?? "Oczekuje na przypisanie"}</p>
                    {workOrder.queue_position !== null ? <p>Pozycja: {workOrder.queue_position}</p> : <p>Pozycja: -</p>}
                  </div>
                </td>
                <td className="px-5 py-4 align-top text-brand-muted">{renderQuantitySummary(workOrder)}</td>
                <td className="px-5 py-4 align-top">
                  <div className="space-y-2">
                    <span className={["inline-flex rounded-full px-3 py-1 text-xs font-semibold", statusClasses(workOrder.process_status.value)].join(" ")}>
                      {workOrder.process_status.label}
                    </span>
                    {getWorkOrderDiscrepancyText(workOrder) ? (
                      <p className="text-xs font-semibold text-amber-700">{getWorkOrderDiscrepancyText(workOrder)}</p>
                    ) : null}
                  </div>
                </td>
                <td className="px-5 py-4 align-top text-brand-muted">
                  <div className="space-y-2">
                    <p className="font-semibold text-brand-ink">{formatDateLabel(workOrder.planned_pickup_date)}</p>
                    <p className={getTermMetaClass(workOrder)}>{getTermMeta(workOrder)}</p>
                  </div>
                </td>
                <td className="px-5 py-4 align-top text-right">
                  <Link
                    to={`/zlecenia/${workOrder.id}`}
                    onClick={(event) => event.stopPropagation()}
                    className="inline-flex h-10 w-10 items-center justify-center rounded-full bg-brand-surface text-base font-semibold text-brand-ink transition hover:bg-brand-100"
                    aria-label={`Szczegóły ${workOrder.order_number}`}
                  >
                    ⋮
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}