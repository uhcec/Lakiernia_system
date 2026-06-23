import { getWorkOrderAttachmentDownloadUrl } from "../api/workOrdersApi";
import type { WorkOrderAttachmentSummary } from "../types/workOrders";

interface TechnicalDrawingLinksProps {
  workOrderId: number;
  drawings: WorkOrderAttachmentSummary[];
}

/**
 * Read-only list of a work order's technical drawings (NA36), shown on the production station cards.
 * Each entry opens the existing attachment-download endpoint in a new tab; every station may view.
 * Renders nothing when the order has no drawings.
 */
export function TechnicalDrawingLinks({ workOrderId, drawings }: TechnicalDrawingLinksProps) {
  if (drawings.length === 0) {
    return null;
  }

  return (
    <div className="space-y-1 text-sm">
      <p className="font-medium text-steel">Rysunki techniczne</p>
      <ul className="space-y-1">
        {drawings.map((drawing) => (
          <li key={drawing.id}>
            <a
              href={getWorkOrderAttachmentDownloadUrl(workOrderId, drawing.id)}
              target="_blank"
              rel="noreferrer"
              className="font-semibold text-accent underline decoration-dotted underline-offset-2 hover:text-accent/80"
            >
              {drawing.original_filename}
            </a>
          </li>
        ))}
      </ul>
    </div>
  );
}
