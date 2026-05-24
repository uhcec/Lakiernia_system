import { Link, useNavigate } from "react-router-dom";

import type { WorkOrder } from "../types/workOrders";

interface WorkOrdersTableProps {
  workOrders: WorkOrder[];
}

function statusClasses(statusValue: WorkOrder["process_status"]["value"]): string {
  switch (statusValue) {
    case "TO_BE_PLANNED":
      return "bg-slate-100 text-slate-700";
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
    case "READY":
      return "bg-emerald-100 text-emerald-700";
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

    return (
      <div className="space-y-2">
        <p className="text-sm text-ink">{`${totalQuantity} szt. / gotowe ${completedQuantity} / aktywne ${activeQuantity}`}</p>
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
              <th className="px-5 py-4 font-semibold">Tytuł</th>
              <th className="px-5 py-4 font-semibold">Firma</th>
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
                className="cursor-pointer border-t border-line/80 text-ink transition hover:bg-mist/60"
                onClick={() => navigate(`/zlecenia/${workOrder.id}`)}
              >
                <td className="px-5 py-4 font-semibold">{workOrder.order_number}</td>
                <td className="px-5 py-4">{workOrder.title}</td>
                <td className="px-5 py-4 text-steel">{workOrder.customer_name || "—"}</td>
                <td className="px-5 py-4 text-steel">{workOrder.coating_type.label}</td>
                <td className="px-5 py-4 text-steel">{workOrder.production_type?.label ?? "—"}</td>
                <td className="px-5 py-4 text-steel">{workOrder.queue_position ?? "—"}</td>
                <td className="px-5 py-4 text-steel">{renderQuantitySummary(workOrder)}</td>
                <td className="px-5 py-4">
                  <span className={["inline-flex rounded-full px-3 py-1 text-xs font-semibold", statusClasses(workOrder.process_status.value)].join(" ")}>
                    {workOrder.process_status.label}
                  </span>
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