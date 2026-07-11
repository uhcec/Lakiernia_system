import { useEffect, useMemo, useState } from "react";

import { generateWzDocument } from "../api/workOrdersApi";
import type { WorkOrder } from "../types/workOrders";

// "Generuj WZ" flow for the office (WorkOrdersListPage). The clerk picks one client, ticks which of
// that client's ready-to-release orders go on the document, optionally enters a loaded-basket count
// ("Kosze dłużycowe" — the only manual line), and gets a WZ PDF. One WZ = one recipient, so the client
// picker enforces a single customer; the backend re-validates (READY, same customer). Generating a WZ
// does NOT mark the orders released — that stays a separate step.

function quantitySummary(order: WorkOrder): string {
  const parts: string[] = [];
  if (order.profiles_quantity && order.profiles_quantity > 0) parts.push(`${order.profiles_quantity} profili`);
  if (order.accessories_quantity && order.accessories_quantity > 0) parts.push(`${order.accessories_quantity} akcesoriów`);
  if (parts.length === 0) parts.push(`${order.total_quantity} szt`);
  return parts.join(" + ");
}

export function GenerateWzModal({
  orders,
  onClose,
  onGenerated,
}: {
  orders: WorkOrder[];
  onClose: () => void;
  onGenerated?: () => void;
}) {
  // Candidates grouped by recipient. Sorted client list; orders within a client by our number.
  const clients = useMemo(() => {
    const byClient = new Map<string, WorkOrder[]>();
    for (const order of orders) {
      const list = byClient.get(order.customer_name) ?? [];
      list.push(order);
      byClient.set(order.customer_name, list);
    }
    return [...byClient.entries()]
      .map(([name, clientOrders]) => ({
        name,
        orders: [...clientOrders].sort((a, b) => a.order_number.localeCompare(b.order_number)),
      }))
      .sort((a, b) => a.name.localeCompare(b.name));
  }, [orders]);

  const [selectedClient, setSelectedClient] = useState<string | null>(clients[0]?.name ?? null);
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [basketsText, setBasketsText] = useState("");
  const [isGenerating, setIsGenerating] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const activeClient = clients.find((client) => client.name === selectedClient) ?? null;

  // When the chosen client changes, default to all of that client's orders ticked.
  useEffect(() => {
    setSelectedIds(new Set(activeClient?.orders.map((order) => order.id) ?? []));
    setErrorMessage(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedClient]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !isGenerating) onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose, isGenerating]);

  function toggleOrder(id: number) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function handleGenerate() {
    const ids = activeClient?.orders.filter((order) => selectedIds.has(order.id)).map((order) => order.id) ?? [];
    if (ids.length === 0) {
      setErrorMessage("Zaznacz przynajmniej jedno zlecenie.");
      return;
    }
    const trimmed = basketsText.trim();
    const baskets = trimmed === "" ? null : Number(trimmed);
    if (baskets !== null && (!Number.isInteger(baskets) || baskets < 0)) {
      setErrorMessage("Liczba koszy musi być liczbą całkowitą nie mniejszą od zera.");
      return;
    }

    setIsGenerating(true);
    setErrorMessage(null);
    try {
      await generateWzDocument({ work_order_ids: ids, baskets_count: baskets });
      onGenerated?.();
      onClose();
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Nie udało się wygenerować WZ.");
    } finally {
      setIsGenerating(false);
    }
  }

  const selectedCount = activeClient?.orders.filter((order) => selectedIds.has(order.id)).length ?? 0;

  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center overflow-y-auto bg-black/40 px-4 py-8 backdrop-blur-sm"
      onClick={(event) => {
        if (event.target === event.currentTarget && !isGenerating) onClose();
      }}
    >
      <div role="dialog" aria-modal="true" className="flex max-h-[85vh] w-full max-w-2xl flex-col rounded-[2rem] border border-white/70 bg-white shadow-panel">
        <div className="border-b border-line/80 px-8 py-6">
          <h2 className="text-xl font-semibold text-brand-ink">Generuj WZ</h2>
          <p className="mt-2 text-sm text-brand-muted">
            Wybierz odbiorcę i zaznacz zlecenia do wydania. Jeden dokument WZ dotyczy jednego odbiorcy.
          </p>
        </div>

        {clients.length === 0 ? (
          <div className="px-8 py-10 text-center text-base text-brand-muted">
            Brak zleceń gotowych do wydania.
          </div>
        ) : (
          <div className="flex-1 space-y-5 overflow-y-auto px-8 py-6">
            <label className="flex flex-col gap-2">
              <span className="text-sm font-semibold text-brand-ink">Odbiorca</span>
              <select
                value={selectedClient ?? ""}
                onChange={(event) => setSelectedClient(event.target.value)}
                className="rounded-[1.2rem] border border-brand-line bg-brand-soft px-4 py-3 text-sm text-brand-ink outline-none transition focus:border-brand-900"
              >
                {clients.map((client) => (
                  <option key={client.name} value={client.name}>
                    {client.name} ({client.orders.length})
                  </option>
                ))}
              </select>
            </label>

            <div className="space-y-2">
              <span className="text-sm font-semibold text-brand-ink">
                Zlecenia do wydania <span className="text-brand-muted">({selectedCount} zazn.)</span>
              </span>
              <ul className="space-y-2">
                {activeClient?.orders.map((order) => (
                  <li key={order.id}>
                    <label className="flex cursor-pointer items-center gap-3 rounded-[1.2rem] border border-brand-line bg-brand-soft px-4 py-3 transition hover:border-brand-900">
                      <input
                        type="checkbox"
                        checked={selectedIds.has(order.id)}
                        onChange={() => toggleOrder(order.id)}
                        className="h-4 w-4 flex-none accent-brand-900"
                      />
                      <span className="flex min-w-0 flex-1 flex-wrap items-baseline gap-x-3 gap-y-1">
                        <span className="font-semibold text-brand-ink">{order.order_number}</span>
                        {order.external_order_number ? (
                          <span className="text-xs text-brand-muted">zam. klienta {order.external_order_number}</span>
                        ) : null}
                        <span className="text-sm text-brand-muted">{order.ral_code}</span>
                        <span className="text-sm text-brand-muted">· {quantitySummary(order)}</span>
                      </span>
                    </label>
                  </li>
                ))}
              </ul>
            </div>

            <label className="flex flex-col gap-2">
              <span className="text-sm font-semibold text-brand-ink">Kosze dłużycowe (opcjonalnie)</span>
              <input
                type="number"
                min={0}
                step={1}
                inputMode="numeric"
                value={basketsText}
                onChange={(event) => setBasketsText(event.target.value)}
                placeholder="np. 4"
                className="w-40 rounded-[1.2rem] border border-brand-line bg-brand-soft px-4 py-3 text-sm text-brand-ink outline-none transition focus:border-brand-900"
              />
              <span className="text-xs text-brand-muted">
                Liczba załadowanych koszy dopisywana jako osobna pozycja. Zostaw puste, jeśli brak.
              </span>
            </label>

            {errorMessage ? (
              <p className="rounded-[1.2rem] border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{errorMessage}</p>
            ) : null}
          </div>
        )}

        <div className="flex justify-end gap-3 border-t border-line/80 px-8 py-5">
          <button
            type="button"
            onClick={onClose}
            disabled={isGenerating}
            className="inline-flex items-center justify-center rounded-full border border-line bg-white px-5 py-2.5 text-sm font-medium text-steel transition hover:border-accent hover:text-accent disabled:opacity-60"
          >
            Anuluj
          </button>
          <button
            type="button"
            onClick={handleGenerate}
            disabled={isGenerating || clients.length === 0 || selectedCount === 0}
            className="inline-flex items-center justify-center rounded-full bg-brand-900 px-6 py-2.5 text-sm font-semibold text-white transition hover:bg-brand-800 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {isGenerating ? "Generowanie…" : "Generuj WZ"}
          </button>
        </div>
      </div>
    </div>
  );
}
