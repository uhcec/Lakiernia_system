import { FormEvent, useEffect, useState } from "react";

import { NumberInput } from "../components/NumberInput";
import { fetchPaintMovements, fetchPaints, recordPaintAdjustment, recordPaintDelivery } from "../api/paintsApi";
import type { Paint, PaintStockMovement } from "../types/paints";

interface DeliveryFormState {
  ral_code: string;
  paint_producer: string;
  paint_code: string;
  quantity_kg: string;
  movement_date: string;
  note: string;
}

interface AdjustmentFormState {
  ral_code: string;
  paint_producer: string;
  paint_code: string;
  quantity_delta_kg: string;
  movement_date: string;
  note: string;
}

const initialDeliveryFormState: DeliveryFormState = {
  ral_code: "",
  paint_producer: "",
  paint_code: "",
  quantity_kg: "",
  movement_date: "",
  note: "",
};

const initialAdjustmentFormState: AdjustmentFormState = {
  ral_code: "",
  paint_producer: "",
  paint_code: "",
  quantity_delta_kg: "",
  movement_date: "",
  note: "",
};

function parseNumber(value: string): number | undefined {
  if (!value.trim()) {
    return undefined;
  }

  const parsed = Number(value);
  if (!Number.isFinite(parsed)) {
    return Number.NaN;
  }
  return parsed;
}

// A paint is identified by RAL + producer + code (all required, DB-enforced). Validate them client-side
// so an empty field gives a clear message instead of a raw 422 from the backend.
function validatePaintIdentity(form: { ral_code: string; paint_producer: string; paint_code: string }): string | null {
  if (!form.ral_code.trim()) return "Podaj kod RAL.";
  if (!form.paint_producer.trim()) return "Podaj producenta farby.";
  if (!form.paint_code.trim()) return "Podaj kod farby.";
  return null;
}

function formatQuantity(quantity: number): string {
  return `${quantity} kg`;
}

export function PaintInventoryPage() {
  const [paints, setPaints] = useState<Paint[]>([]);
  const [selectedPaintId, setSelectedPaintId] = useState<number | null>(null);
  const [movements, setMovements] = useState<PaintStockMovement[]>([]);
  const [deliveryFormState, setDeliveryFormState] = useState<DeliveryFormState>(initialDeliveryFormState);
  const [adjustmentFormState, setAdjustmentFormState] = useState<AdjustmentFormState>(initialAdjustmentFormState);
  const [isLoading, setIsLoading] = useState(true);
  const [isSavingDelivery, setIsSavingDelivery] = useState(false);
  const [isSavingAdjustment, setIsSavingAdjustment] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [deliveryErrorMessage, setDeliveryErrorMessage] = useState<string | null>(null);
  const [adjustmentErrorMessage, setAdjustmentErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    let isActive = true;

    async function loadPaints() {
      setIsLoading(true);
      setErrorMessage(null);

      try {
        const response = await fetchPaints();
        if (!isActive) {
          return;
        }
        setPaints(response.items);
        setSelectedPaintId((current) => {
          if (current !== null && response.items.some((paint) => paint.id === current)) {
            return current;
          }
          return response.items[0]?.id ?? null;
        });
      } catch (error) {
        if (!isActive) {
          return;
        }
        setErrorMessage(error instanceof Error ? error.message : "Nie udało się pobrać farb");
      } finally {
        if (isActive) {
          setIsLoading(false);
        }
      }
    }

    loadPaints();

    return () => {
      isActive = false;
    };
  }, []);

  useEffect(() => {
    if (selectedPaintId === null) {
      setMovements([]);
      return;
    }

    let isActive = true;
    fetchPaintMovements(selectedPaintId)
      .then((response) => {
        if (!isActive) {
          return;
        }
        setMovements(response.items);
      })
      .catch((error) => {
        if (!isActive) {
          return;
        }
        setErrorMessage(error instanceof Error ? error.message : "Nie udało się pobrać ruchów farby");
      });

    return () => {
      isActive = false;
    };
  }, [selectedPaintId]);

  async function reloadPaintsAndSelect(identity: { ral_code: string; paint_producer: string; paint_code: string }) {
    const response = await fetchPaints();
    setPaints(response.items);
    const selectedPaint = response.items.find(
      (paint) =>
        paint.ral_code === identity.ral_code &&
        paint.paint_producer === identity.paint_producer &&
        paint.paint_code === identity.paint_code,
    );
    setSelectedPaintId(selectedPaint?.id ?? response.items[0]?.id ?? null);
  }

  async function handleDeliverySubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setDeliveryErrorMessage(null);
    const identityError = validatePaintIdentity(deliveryFormState);
    if (identityError) {
      setDeliveryErrorMessage(identityError);
      return;
    }
    const quantityKg = parseNumber(deliveryFormState.quantity_kg);
    if (quantityKg === undefined || Number.isNaN(quantityKg) || quantityKg <= 0) {
      setDeliveryErrorMessage("Ilość dostawy musi być dodatnią liczbą.");
      return;
    }

    setIsSavingDelivery(true);
    try {
      await recordPaintDelivery({
        ral_code: deliveryFormState.ral_code.trim(),
        paint_producer: deliveryFormState.paint_producer.trim(),
        paint_code: deliveryFormState.paint_code.trim(),
        quantity_kg: quantityKg,
        movement_date: deliveryFormState.movement_date || undefined,
        note: deliveryFormState.note.trim() || undefined,
      });
      await reloadPaintsAndSelect({
        ral_code: deliveryFormState.ral_code.trim(),
        paint_producer: deliveryFormState.paint_producer.trim(),
        paint_code: deliveryFormState.paint_code.trim(),
      });
      setDeliveryFormState(initialDeliveryFormState);
    } catch (error) {
      setDeliveryErrorMessage(error instanceof Error ? error.message : "Nie udało się zapisać dostawy farby");
    } finally {
      setIsSavingDelivery(false);
    }
  }

  async function handleAdjustmentSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setAdjustmentErrorMessage(null);
    const identityError = validatePaintIdentity(adjustmentFormState);
    if (identityError) {
      setAdjustmentErrorMessage(identityError);
      return;
    }
    const quantityDeltaKg = parseNumber(adjustmentFormState.quantity_delta_kg);
    if (quantityDeltaKg === undefined || Number.isNaN(quantityDeltaKg) || quantityDeltaKg === 0) {
      setAdjustmentErrorMessage("Korekta musi być liczbą różną od zera.");
      return;
    }
    if (!adjustmentFormState.note.trim()) {
      setAdjustmentErrorMessage("Notatka do korekty jest wymagana.");
      return;
    }

    setIsSavingAdjustment(true);
    try {
      await recordPaintAdjustment({
        ral_code: adjustmentFormState.ral_code.trim(),
        paint_producer: adjustmentFormState.paint_producer.trim(),
        paint_code: adjustmentFormState.paint_code.trim(),
        quantity_delta_kg: quantityDeltaKg,
        movement_date: adjustmentFormState.movement_date || undefined,
        note: adjustmentFormState.note.trim(),
      });
      await reloadPaintsAndSelect({
        ral_code: adjustmentFormState.ral_code.trim(),
        paint_producer: adjustmentFormState.paint_producer.trim(),
        paint_code: adjustmentFormState.paint_code.trim(),
      });
      setAdjustmentFormState(initialAdjustmentFormState);
    } catch (error) {
      setAdjustmentErrorMessage(error instanceof Error ? error.message : "Nie udało się zapisać korekty farby");
    } finally {
      setIsSavingAdjustment(false);
    }
  }

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-7xl flex-col gap-6 px-4 py-8 sm:px-6 lg:px-8">
      <section className="rounded-[2rem] border border-white/70 bg-white/80 p-6 shadow-panel backdrop-blur sm:p-8">
        <div className="space-y-2">
          <p className="text-sm font-semibold uppercase tracking-[0.18em] text-accent">Biuro</p>
          <div>
            <h1 className="text-3xl font-semibold text-ink sm:text-4xl">Farby</h1>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-steel sm:text-base">
              Magazyn farb jest źródłem prawdy dla bieżącego stanu. Zlecenie tylko pokazuje aktualny stan i zapisuje jego
              historyczny snapshot bez rezerwacji.
            </p>
          </div>
        </div>
      </section>

      <section className="grid gap-6 xl:grid-cols-[1.2fr_0.8fr]">
        <div className="space-y-6">
          <section className="rounded-[2rem] border border-white/70 bg-white/80 p-6 shadow-panel backdrop-blur sm:p-8">
            <div className="flex items-center justify-between gap-3">
              <div>
                <h2 className="text-lg font-semibold text-ink">Stany magazynowe</h2>
                <p className="mt-1 text-sm text-steel">Łączny stan na kartę farby, bez rozliczania po partiach.</p>
              </div>
              <div className="rounded-2xl border border-line bg-mist px-4 py-3 text-sm text-steel">
                Kart farb: <span className="font-semibold text-ink">{paints.length}</span>
              </div>
            </div>

            {isLoading ? (
              <div className="mt-6 rounded-3xl border border-dashed border-line bg-mist px-6 py-12 text-center text-base text-steel">
                Ładowanie farb...
              </div>
            ) : errorMessage ? (
              <div className="mt-6 rounded-3xl border border-rose-200 bg-rose-50 px-6 py-12 text-center text-base text-rose-700">
                {errorMessage}
              </div>
            ) : paints.length === 0 ? (
              <div className="mt-6 rounded-3xl border border-dashed border-line bg-mist px-6 py-12 text-center text-base text-steel">
                Brak farb w magazynie
              </div>
            ) : (
              <div className="mt-6 overflow-hidden rounded-3xl border border-line">
                <table className="min-w-full divide-y divide-line text-left text-sm">
                  <thead className="bg-mist text-steel">
                    <tr>
                      <th className="px-4 py-3 font-medium">RAL</th>
                      <th className="px-4 py-3 font-medium">Producent</th>
                      <th className="px-4 py-3 font-medium">Kod</th>
                      <th className="px-4 py-3 font-medium">Stan</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-line bg-white text-ink">
                    {paints.map((paint) => (
                      <tr
                        key={paint.id}
                        onClick={() => setSelectedPaintId(paint.id)}
                        className={[
                          "cursor-pointer transition hover:bg-mist/60",
                          selectedPaintId === paint.id ? "bg-mist/60" : "",
                        ].join(" ")}
                      >
                        <td className="px-4 py-3">{paint.ral_code}</td>
                        <td className="px-4 py-3">{paint.paint_producer}</td>
                        <td className="px-4 py-3">{paint.paint_code}</td>
                        <td className="px-4 py-3 font-semibold">{formatQuantity(paint.current_quantity_kg)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          <section className="rounded-[2rem] border border-white/70 bg-white/80 p-6 shadow-panel backdrop-blur sm:p-8">
            <div>
              <h2 className="text-lg font-semibold text-ink">Historia ruchów</h2>
              <p className="mt-1 text-sm text-steel">Wybierz kartę farby z listy, aby zobaczyć jej dostawy, zużycia i korekty.</p>
            </div>

            {selectedPaintId === null ? (
              <div className="mt-6 rounded-3xl border border-dashed border-line bg-mist px-6 py-12 text-center text-base text-steel">
                Wybierz farbę z listy.
              </div>
            ) : movements.length === 0 ? (
              <div className="mt-6 rounded-3xl border border-dashed border-line bg-mist px-6 py-12 text-center text-base text-steel">
                Brak ruchów dla wybranej farby.
              </div>
            ) : (
              <div className="mt-6 space-y-3">
                {movements.map((movement) => (
                  <article key={movement.id} className="rounded-3xl border border-line bg-mist/35 px-5 py-4">
                    <div className="flex flex-col gap-2 lg:flex-row lg:items-center lg:justify-between">
                      <div>
                        <p className="text-sm font-semibold text-ink">{movement.movement_type.label}</p>
                        <p className="text-xs text-steel">Data ruchu: {movement.movement_date}</p>
                      </div>
                      <div className="text-sm text-steel">
                        <span className="font-medium text-ink">{formatQuantity(movement.quantity_delta_kg)}</span>
                        <span> | Stan po ruchu: {formatQuantity(movement.resulting_quantity_kg)}</span>
                      </div>
                    </div>
                    {movement.note ? <p className="mt-3 text-sm text-steel">{movement.note}</p> : null}
                  </article>
                ))}
              </div>
            )}
          </section>
        </div>

        <div className="space-y-6">
          <section className="rounded-[2rem] border border-white/70 bg-white/80 p-6 shadow-panel backdrop-blur sm:p-8">
            <div>
              <h2 className="text-lg font-semibold text-ink">Dostawa farby</h2>
              <p className="mt-1 text-sm text-steel">Przyjęcie zwiększa bieżący stan magazynowy wybranej farby.</p>
            </div>

            <form className="mt-6 space-y-4" onSubmit={handleDeliverySubmit}>
              <input value={deliveryFormState.ral_code} onChange={(event) => setDeliveryFormState((current) => ({ ...current, ral_code: event.target.value }))} placeholder="RAL" className="w-full rounded-2xl border border-line bg-white px-4 py-3 text-sm text-ink outline-none transition focus:border-accent" />
              <input value={deliveryFormState.paint_producer} onChange={(event) => setDeliveryFormState((current) => ({ ...current, paint_producer: event.target.value }))} placeholder="Producent farby" className="w-full rounded-2xl border border-line bg-white px-4 py-3 text-sm text-ink outline-none transition focus:border-accent" />
              <input value={deliveryFormState.paint_code} onChange={(event) => setDeliveryFormState((current) => ({ ...current, paint_code: event.target.value }))} placeholder="Kod farby" className="w-full rounded-2xl border border-line bg-white px-4 py-3 text-sm text-ink outline-none transition focus:border-accent" />
              <NumberInput min="0" step="0.01" value={deliveryFormState.quantity_kg} onValueChange={(value) => setDeliveryFormState((current) => ({ ...current, quantity_kg: value }))} placeholder="Ilość [kg]" className="w-full rounded-2xl border border-line bg-white px-4 py-3 text-sm text-ink outline-none transition focus:border-accent" />
              <input type="date" value={deliveryFormState.movement_date} onChange={(event) => setDeliveryFormState((current) => ({ ...current, movement_date: event.target.value }))} className="w-full rounded-2xl border border-line bg-white px-4 py-3 text-sm text-ink outline-none transition focus:border-accent" />
              <textarea value={deliveryFormState.note} onChange={(event) => setDeliveryFormState((current) => ({ ...current, note: event.target.value }))} rows={3} placeholder="Notatka opcjonalna" className="w-full rounded-2xl border border-line bg-white px-4 py-3 text-sm text-ink outline-none transition focus:border-accent" />
              {deliveryErrorMessage ? <p className="text-sm text-rose-700">{deliveryErrorMessage}</p> : null}
              <button type="submit" disabled={isSavingDelivery} className="inline-flex items-center justify-center rounded-full bg-accent px-5 py-3 text-sm font-medium text-white transition hover:bg-teal-700 disabled:cursor-not-allowed disabled:opacity-70">
                {isSavingDelivery ? "Zapisywanie..." : "Zapisz dostawę"}
              </button>
            </form>
          </section>

          <section className="rounded-[2rem] border border-white/70 bg-white/80 p-6 shadow-panel backdrop-blur sm:p-8">
            <div>
              <h2 className="text-lg font-semibold text-ink">Korekta magazynowa</h2>
              <p className="mt-1 text-sm text-steel">Korekta może być dodatnia lub ujemna, ale nie może zepchnąć stanu poniżej zera.</p>
            </div>

            <form className="mt-6 space-y-4" onSubmit={handleAdjustmentSubmit}>
              <input value={adjustmentFormState.ral_code} onChange={(event) => setAdjustmentFormState((current) => ({ ...current, ral_code: event.target.value }))} placeholder="RAL" className="w-full rounded-2xl border border-line bg-white px-4 py-3 text-sm text-ink outline-none transition focus:border-accent" />
              <input value={adjustmentFormState.paint_producer} onChange={(event) => setAdjustmentFormState((current) => ({ ...current, paint_producer: event.target.value }))} placeholder="Producent farby" className="w-full rounded-2xl border border-line bg-white px-4 py-3 text-sm text-ink outline-none transition focus:border-accent" />
              <input value={adjustmentFormState.paint_code} onChange={(event) => setAdjustmentFormState((current) => ({ ...current, paint_code: event.target.value }))} placeholder="Kod farby" className="w-full rounded-2xl border border-line bg-white px-4 py-3 text-sm text-ink outline-none transition focus:border-accent" />
              <NumberInput step="0.01" value={adjustmentFormState.quantity_delta_kg} onValueChange={(value) => setAdjustmentFormState((current) => ({ ...current, quantity_delta_kg: value }))} placeholder="Korekta [+/- kg]" className="w-full rounded-2xl border border-line bg-white px-4 py-3 text-sm text-ink outline-none transition focus:border-accent" />
              <input type="date" value={adjustmentFormState.movement_date} onChange={(event) => setAdjustmentFormState((current) => ({ ...current, movement_date: event.target.value }))} className="w-full rounded-2xl border border-line bg-white px-4 py-3 text-sm text-ink outline-none transition focus:border-accent" />
              <textarea value={adjustmentFormState.note} onChange={(event) => setAdjustmentFormState((current) => ({ ...current, note: event.target.value }))} rows={3} placeholder="Powód korekty" className="w-full rounded-2xl border border-line bg-white px-4 py-3 text-sm text-ink outline-none transition focus:border-accent" />
              {adjustmentErrorMessage ? <p className="text-sm text-rose-700">{adjustmentErrorMessage}</p> : null}
              <button type="submit" disabled={isSavingAdjustment} className="inline-flex items-center justify-center rounded-full bg-accent px-5 py-3 text-sm font-medium text-white transition hover:bg-teal-700 disabled:cursor-not-allowed disabled:opacity-70">
                {isSavingAdjustment ? "Zapisywanie..." : "Zapisz korektę"}
              </button>
            </form>
          </section>
        </div>
      </section>
    </main>
  );
}
