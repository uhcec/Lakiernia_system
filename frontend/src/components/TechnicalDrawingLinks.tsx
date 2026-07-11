import { useState } from "react";

import { openWorkOrderAttachment } from "../api/workOrdersApi";
import type { WorkOrderAttachmentSummary } from "../types/workOrders";
import { getLoadErrorMessage } from "../utils/loadError";

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
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  if (drawings.length === 0) {
    return null;
  }

  async function open(attachmentId: number) {
    setErrorMessage(null);
    try {
      await openWorkOrderAttachment(workOrderId, attachmentId);
    } catch (error) {
      setErrorMessage(getLoadErrorMessage(error, "Nie udało się otworzyć rysunku"));
    }
  }

  return (
    <div className="space-y-1 text-sm">
      <p className="font-medium text-steel">Rysunki techniczne</p>
      <ul className="space-y-1">
        {drawings.map((drawing) => (
          <li key={drawing.id}>
            <button
              type="button"
              onClick={() => void open(drawing.id)}
              className="text-left font-semibold text-accent underline decoration-dotted underline-offset-2 hover:text-accent/80"
            >
              {drawing.original_filename}
            </button>
          </li>
        ))}
      </ul>
      {errorMessage ? <p className="text-rose-600">{errorMessage}</p> : null}
    </div>
  );
}
