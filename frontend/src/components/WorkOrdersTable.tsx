import { Link, useNavigate } from "react-router-dom";

import type { WorkOrder } from "../types/workOrders";
import {
  formatWorkOrderPrimaryInfo,
  getWorkOrderActiveCorrectionsText,
  getWorkOrderAttentionBadges,
  getWorkOrderBadgeStack,
  getWorkOrderCorrectionContextText,
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
      return "bg-slate-100 text-slate-700";
    case "INCOMPLETE":
      return "bg-rose-100 text-rose-700";
    case "SURFACE_PREPARATION":
      return "bg-amber-100 text-amber-800";
    case "HANGING":
      return "bg-sky-100 text-sky-700";
    case "PRODUCTION_MANUAL":
      return "bg-orange-100 text-orange-800";
    case "PRODUCTION_AUTOMATIC":
      return "bg-cyan-100 text-cyan-800";
    case "DECORAL_PRODUCTION":
      return "bg-violet-100 text-violet-800";
    case "PACKING":
      return "bg-lime-100 text-lime-800";
    case "WAITING_FOR_CORRECTIONS":
      return "bg-amber-200 text-amber-900";
    case "READY":
      return "bg-emerald-100 text-emerald-700";
  }
}

function badgeClasses(tone: DisplayBadge["tone"]): string {
  switch (tone) {
    case "info":
      return "bg-sky-100 text-sky-800";
    case "warning":
      return "bg-amber-100 text-amber-800";
    case "success":
      return "bg-emerald-100 text-emerald-700";
    case "accent":
      return "bg-violet-100 text-violet-800";
    case "danger":
      return "bg-rose-100 text-rose-700";
    case "neutral":
      return "bg-slate-100 text-slate-700";
  }
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
    <div className="overflow-hidden rounded-3xl border border-line bg-white shadow-panel">
      <div className="overflow-x-auto">
        <table className="min-w-full border-collapse text-left text-sm">
          <thead className="bg-mist text-steel">
            <tr>
              <th className="px-5 py-4 font-semibold">Nr zlecenia</th>
              <th className="px-5 py-4 font-semibold">Dane główne</th>
              <th className="px-5 py-4 font-semibold">Technologia</th>
              <th className="px-5 py-4 font-semibold">Typ produkcji</th>
              <th className="px-5 py-4 font-semibold">Pozycja</th>
              <th className="px-5 py-4 font-semibold">Ilość</th>
              <th className="px-5 py-4 font-semibold">Status procesu</th>
              <th className="px-5 py-4 font-semibold text-right">Szczegóły</th>
            </tr>
          </thead>
          <tbody>
            {workOrders.map((workOrder) => (
              <tr
                key={workOrder.id}
                className={[
                  "cursor-pointer border-t border-line/80 text-ink transition hover:bg-mist/60",
                  workOrder.is_correction ? "bg-amber-50/40" : "",
                  getWorkOrderAttentionBadges(workOrder).length > 0 ? "ring-1 ring-inset ring-amber-200" : "",
                ].join(" ")}
                onClick={() => navigate(`/zlecenia/${workOrder.id}`)}
              >
                <td className="px-5 py-4 font-semibold">
                  <div className="space-y-2">
                    <div>{workOrder.order_number}</div>
                    {workOrder.external_order_number ? (
                      <div className="text-xs font-medium text-steel">Zewn.: {workOrder.external_order_number}</div>
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
                <td className="px-5 py-4 text-steel">
                  <div className="space-y-1">
                    <p>{formatWorkOrderPrimaryInfo(workOrder)}</p>
                    {getWorkOrderCorrectionContextText(workOrder) ? (
                      <p className="text-amber-700">{getWorkOrderCorrectionContextText(workOrder)}</p>
                    ) : null}
                  </div>
                </td>
                <td className="px-5 py-4 text-steel">{workOrder.coating_type.label}</td>
                <td className="px-5 py-4 text-steel">{workOrder.production_type?.label ?? "—"}</td>
                <td className="px-5 py-4 text-steel">{workOrder.queue_position ?? "—"}</td>
                <td className="px-5 py-4 text-steel">{renderQuantitySummary(workOrder)}</td>
                <td className="px-5 py-4">
                  <div className="space-y-2">
                    <span className={["inline-flex rounded-full px-3 py-1 text-xs font-semibold", statusClasses(workOrder.process_status.value)].join(" ")}>
                      {workOrder.process_status.label}
                    </span>
                    <p className="text-sm font-semibold text-ink">{getWorkOrderStatusSummary(workOrder)}</p>
                  </div>
                </td>
                <td className="px-5 py-4 text-right">
                  <Link
                    to={`/zlecenia/${workOrder.id}`}
                    onClick={(event) => event.stopPropagation()}
                    className="inline-flex items-center justify-center rounded-full border border-line bg-white px-4 py-2 text-sm font-medium text-steel transition hover:border-accent hover:text-accent"
                  >
                    Szczegóły
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