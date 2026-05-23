import type { WorkOrder } from "../types/workOrders";

interface WorkOrdersTableProps {
  workOrders: WorkOrder[];
}

function formatDate(value: string | null): string {
  if (!value) {
    return "-";
  }

  return new Intl.DateTimeFormat("pl-PL").format(new Date(value));
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
  return (
    <div className="overflow-hidden rounded-3xl border border-line bg-white shadow-panel">
      <div className="overflow-x-auto">
        <table className="min-w-full border-collapse text-left text-sm">
          <thead className="bg-mist text-steel">
            <tr>
              <th className="px-5 py-4 font-semibold">Numer</th>
              <th className="px-5 py-4 font-semibold">Tytuł</th>
              <th className="px-5 py-4 font-semibold">Klient</th>
              <th className="px-5 py-4 font-semibold">Status</th>
              <th className="px-5 py-4 font-semibold">Termin</th>
              <th className="px-5 py-4 font-semibold">Utworzono</th>
            </tr>
          </thead>
          <tbody>
            {workOrders.map((workOrder) => (
              <tr key={workOrder.id} className="border-t border-line/80 text-ink">
                <td className="px-5 py-4 font-semibold">{workOrder.order_number}</td>
                <td className="px-5 py-4">{workOrder.title}</td>
                <td className="px-5 py-4 text-steel">{workOrder.customer_name || "-"}</td>
                <td className="px-5 py-4">
                  <span className={["inline-flex rounded-full px-3 py-1 text-xs font-semibold", statusClasses(workOrder.process_status.value)].join(" ")}>
                    {workOrder.process_status.label}
                  </span>
                </td>
                <td className="px-5 py-4 text-steel">{formatDate(workOrder.due_date)}</td>
                <td className="px-5 py-4 text-steel">{formatDate(workOrder.created_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}