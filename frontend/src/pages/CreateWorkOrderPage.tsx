import { FormEvent, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { NumberInput } from "../components/NumberInput";
import { fetchClients } from "../api/clientsApi";
import { fetchFoils } from "../api/foilsApi";
import { lookupPaintStock } from "../api/paintsApi";
import { createWorkOrder } from "../api/workOrdersApi";
import type { Foil } from "../types/foils";
import type { CoatingTypeValue, WorkOrderKindValue } from "../types/workOrders";
import { getLoadErrorMessage } from "../utils/loadError";

interface FormState {
  total_quantity: string;
  coating_type: CoatingTypeValue | "";
  decoral_foil_id: string;
  work_order_kind: WorkOrderKindValue;
  is_ocynk: boolean;
  external_order_number: string;
  description: string;
  customer_name: string;
  ral_code: string;
  paint_code: string;
  paint_producer: string;
  received_date: string;
  planned_pickup_date: string;
  total_area_m2: string;
  is_incomplete_on_arrival: boolean;
  profiles_quantity: string;
  profiles_to_count: boolean;
  accessories_quantity: string;
  accessories_to_count: boolean;
  notes: string;
}

const initialFormState: FormState = {
  total_quantity: "1",
  coating_type: "",
  decoral_foil_id: "",
  work_order_kind: "STANDARD",
  is_ocynk: false,
  external_order_number: "",
  description: "",
  customer_name: "",
  ral_code: "",
  paint_code: "",
  paint_producer: "",
  received_date: "",
  planned_pickup_date: "",
  total_area_m2: "",
  is_incomplete_on_arrival: false,
  profiles_quantity: "",
  profiles_to_count: false,
  accessories_quantity: "",
  accessories_to_count: false,
  notes: "",
};

function parseOptionalNonNegativeInteger(value: string): number | undefined {
  if (!value.trim()) {
    return undefined;
  }

  const parsed = Number(value);
  if (!Number.isInteger(parsed) || parsed < 0) {
    return Number.NaN;
  }

  return parsed;
}

function parseOptionalPositiveNumber(value: string): number | undefined {
  if (!value.trim()) {
    return undefined;
  }

  const parsed = Number(value);
  if (!Number.isFinite(parsed) || parsed <= 0) {
    return Number.NaN;
  }

  return parsed;
}

function getCategoryQuantityHint(formState: FormState): { text: string; tone: "neutral" | "success" | "warning" } {
  const totalQuantity = Number(formState.total_quantity);
  if (!Number.isInteger(totalQuantity) || totalQuantity <= 0) {
    return { text: "Suma kategorii: podaj ilość całkowitą", tone: "neutral" };
  }

  if (formState.profiles_to_count || formState.accessories_to_count) {
    return { text: "Suma kategorii: do policzenia na produkcji", tone: "neutral" };
  }

  const profilesQuantity = parseOptionalNonNegativeInteger(formState.profiles_quantity);
  const accessoriesQuantity = parseOptionalNonNegativeInteger(formState.accessories_quantity);
  if (Number.isNaN(profilesQuantity) || Number.isNaN(accessoriesQuantity)) {
    return { text: "Suma kategorii: popraw wartości", tone: "warning" };
  }
  if (profilesQuantity === undefined || accessoriesQuantity === undefined) {
    const knownCategorySum = (profilesQuantity ?? 0) + (accessoriesQuantity ?? 0);
    return { text: `Suma kategorii: ${knownCategorySum} / ${totalQuantity}`, tone: "neutral" };
  }

  const categorySum = profilesQuantity + accessoriesQuantity;
  const difference = totalQuantity - categorySum;
  if (difference === 0) {
    return { text: `Suma kategorii: ${categorySum} / ${totalQuantity}`, tone: "success" };
  }
  if (difference > 0) {
    return { text: `Suma kategorii: ${categorySum} / ${totalQuantity}. Brakuje ${difference} szt.`, tone: "warning" };
  }
  return { text: `Suma kategorii: ${categorySum} / ${totalQuantity}. O ${Math.abs(difference)} szt. za dużo`, tone: "warning" };
}

function categoryQuantityHintClasses(tone: ReturnType<typeof getCategoryQuantityHint>["tone"]): string {
  switch (tone) {
    case "success":
      return "border-emerald-200 bg-emerald-50 text-emerald-700";
    case "warning":
      return "border-amber-200 bg-amber-50 text-amber-800";
    case "neutral":
      return "border-line bg-mist text-steel";
  }
}

function calculatePredictedPaintQuantityKg(totalAreaM2: number | undefined): number | null {
  if (totalAreaM2 === undefined || Number.isNaN(totalAreaM2)) {
    return null;
  }
  const predictedQuantity = totalAreaM2 < 100 ? totalAreaM2 / 4 : totalAreaM2 / 6;
  return Math.round(predictedQuantity);
}

function formatPaintKg(value: number | null): string {
  if (value === null) {
    return "-";
  }

  return `${Number(value.toFixed(3)).toString()} kg`;
}

type PaintAvailabilityState = {
  text: string;
  tone: "neutral" | "success" | "warning";
  currentQuantityKg: number | null;
};

function getPaintAvailabilityHint(
  formState: FormState,
  paintLookupState: { currentQuantityKg: number | null; existsInInventory: boolean; isLoading: boolean; errorMessage: string | null },
): PaintAvailabilityState {
  const ralCode = formState.ral_code.trim();
  const paintProducer = formState.paint_producer.trim();
  const paintCode = formState.paint_code.trim();

  if (!ralCode || !paintProducer || !paintCode) {
    return {
      text: "Farba: wpisz RAL, producenta i kod, aby zobaczyć aktualny stan.",
      tone: "neutral",
      currentQuantityKg: null,
    };
  }

  if (paintLookupState.isLoading) {
    return {
      text: "Farba: sprawdzanie aktualnego stanu magazynowego...",
      tone: "neutral",
      currentQuantityKg: null,
    };
  }

  if (paintLookupState.errorMessage) {
    return {
      text: `Farba: ${paintLookupState.errorMessage}`,
      tone: "warning",
      currentQuantityKg: null,
    };
  }

  if (paintLookupState.currentQuantityKg === null) {
    return {
      text: "Farba: nie udało się ustalić aktualnego stanu.",
      tone: "warning",
      currentQuantityKg: null,
    };
  }

  if (!paintLookupState.existsInInventory) {
    return {
      text: "Farba: brak kartoteki w magazynie. Przyjęcie zlecenia zapisze snapshot 0 kg, dopóki biuro nie doda dostawy lub korekty.",
      tone: "warning",
      currentQuantityKg: paintLookupState.currentQuantityKg,
    };
  }

  return {
    text: `Farba: aktualny stan ${paintLookupState.currentQuantityKg} kg. Ta wartość zostanie zapisana na zleceniu jako snapshot historyczny bez rezerwacji.`,
    tone: "success",
    currentQuantityKg: paintLookupState.currentQuantityKg,
  };
}

function getPredictedPaintHint(
  formState: FormState,
  paintLookupState: { currentQuantityKg: number | null; existsInInventory: boolean; isLoading: boolean; errorMessage: string | null },
): { text: string; tone: "neutral" | "success" | "warning" } {
  const totalArea = parseOptionalPositiveNumber(formState.total_area_m2);

  if (Number.isNaN(totalArea)) {
    return { text: "Predykcja zużycia: popraw powierzchnię całkowitą.", tone: "warning" };
  }

  if (totalArea === undefined) {
    return { text: "Predykcja zużycia: podaj powierzchnię całkowitą, aby wyliczyć zapotrzebowanie farby.", tone: "neutral" };
  }

  const divisor = totalArea < 100 ? 4 : 6;
  const predictedQuantity = calculatePredictedPaintQuantityKg(totalArea);
  const currentQuantityKg = paintLookupState.currentQuantityKg;

  if (predictedQuantity !== null && currentQuantityKg !== null && predictedQuantity > currentQuantityKg) {
    const missingQuantityKg = Math.round(predictedQuantity - currentQuantityKg);
    return {
      text: `Predykcja zużycia: ${formatPaintKg(predictedQuantity)} (${totalArea} m2 / ${divisor}). Aktualny stan magazynu nie wystarczy. Brakuje około ${formatPaintKg(missingQuantityKg)} i trzeba domówić farbę.`,
      tone: "warning",
    };
  }

  return {
    text: `Predykcja zużycia: ${formatPaintKg(predictedQuantity)} (${totalArea} m2 / ${divisor}). To tylko podpowiedź planistyczna, bez wpływu na stan magazynu i bez zapisu realnego zużycia.`,
    tone: "success",
  };
}

export function CreateWorkOrderPage() {
  const navigate = useNavigate();
  const [formState, setFormState] = useState<FormState>(initialFormState);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [apiError, setApiError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [clientNameSuggestions, setClientNameSuggestions] = useState<string[]>([]);
  const [foils, setFoils] = useState<Foil[]>([]);
  const [paintLookupState, setPaintLookupState] = useState<{
    currentQuantityKg: number | null;
    existsInInventory: boolean;
    isLoading: boolean;
    errorMessage: string | null;
  }>({
    currentQuantityKg: null,
    existsInInventory: false,
    isLoading: false,
    errorMessage: null,
  });
  useEffect(() => {
    let isActive = true;
    fetchClients()
      .then((response) => {
        if (isActive) {
          setClientNameSuggestions(response.items.map((client) => client.company_name));
        }
      })
      .catch(() => {
        // Suggestions are a convenience only; ignore load failures.
      });
    return () => {
      isActive = false;
    };
  }, []);

  useEffect(() => {
    let isActive = true;
    fetchFoils()
      .then((response) => {
        if (isActive) {
          setFoils(response.items);
        }
      })
      .catch(() => {
        // The foil list is a convenience picker only; ignore load failures.
      });
    return () => {
      isActive = false;
    };
  }, []);

  const categoryQuantityHint = getCategoryQuantityHint(formState);
  const paintAvailabilityHint = getPaintAvailabilityHint(formState, paintLookupState);
  const predictedPaintHint = getPredictedPaintHint(formState, paintLookupState);

  useEffect(() => {
    const ralCode = formState.ral_code.trim();
    const paintProducer = formState.paint_producer.trim();
    const paintCode = formState.paint_code.trim();

    if (!ralCode || !paintProducer || !paintCode) {
      setPaintLookupState({
        currentQuantityKg: null,
        existsInInventory: false,
        isLoading: false,
        errorMessage: null,
      });
      return;
    }

    let isActive = true;
    setPaintLookupState((current) => ({ ...current, isLoading: true, errorMessage: null }));

    lookupPaintStock({ ralCode, paintProducer, paintCode })
      .then((lookup) => {
        if (!isActive) {
          return;
        }
        setPaintLookupState({
          currentQuantityKg: lookup.current_quantity_kg,
          existsInInventory: lookup.exists_in_inventory,
          isLoading: false,
          errorMessage: null,
        });
      })
      .catch((error) => {
        if (!isActive) {
          return;
        }
        setPaintLookupState({
          currentQuantityKg: null,
          existsInInventory: false,
          isLoading: false,
          errorMessage: getLoadErrorMessage(error, "Nie udało się pobrać stanu farby"),
        });
      });

    return () => {
      isActive = false;
    };
  }, [formState.paint_code, formState.paint_producer, formState.ral_code]);

  function updateField(fieldName: keyof FormState, value: string) {
    setFormState((current) => ({ ...current, [fieldName]: value }));
  }

  function updateToggle(
    fieldName: "profiles_to_count" | "accessories_to_count",
    quantityField: "profiles_quantity" | "accessories_quantity",
    checked: boolean,
  ) {
    setFormState((current) => ({
      ...current,
      [fieldName]: checked,
      [quantityField]: checked ? "" : current[quantityField],
    }));
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const trimmedCustomerName = formState.customer_name.trim();
    if (!trimmedCustomerName) {
      setValidationError("Klient jest wymagany");
      return;
    }

    const trimmedRalCode = formState.ral_code.trim();
    if (!trimmedRalCode) {
      setValidationError("Kod RAL jest wymagany");
      return;
    }

    const trimmedPaintProducer = formState.paint_producer.trim();
    if (!trimmedPaintProducer) {
      setValidationError("Producent farby jest wymagany");
      return;
    }

    const trimmedPaintCode = formState.paint_code.trim();
    if (!trimmedPaintCode) {
      setValidationError("Kod farby jest wymagany");
      return;
    }

    if (!formState.coating_type) {
      setValidationError("Technologia jest wymagana");
      return;
    }

    if (!formState.received_date) {
      setValidationError("Data przyjęcia jest wymagana");
      return;
    }

    const totalQuantity = Number(formState.total_quantity);
    if (!Number.isInteger(totalQuantity) || totalQuantity <= 0) {
      setValidationError("Ilość całkowita musi być dodatnią liczbą całkowitą");
      return;
    }

    const profilesQuantity = parseOptionalNonNegativeInteger(formState.profiles_quantity);
    if (Number.isNaN(profilesQuantity)) {
      setValidationError("Ilość profili musi być nieujemną liczbą całkowitą");
      return;
    }
    if (profilesQuantity !== undefined && profilesQuantity > totalQuantity) {
      setValidationError("Ilość profili nie może przekraczać ilości całkowitej");
      return;
    }
    if (profilesQuantity === undefined && !formState.profiles_to_count) {
      setValidationError("Dla profili podaj ilość albo zaznacz 'Do policzenia na produkcji'");
      return;
    }

    const accessoriesQuantity = parseOptionalNonNegativeInteger(formState.accessories_quantity);
    if (Number.isNaN(accessoriesQuantity)) {
      setValidationError("Ilość akcesoriów musi być nieujemną liczbą całkowitą");
      return;
    }
    if (accessoriesQuantity !== undefined && accessoriesQuantity > totalQuantity) {
      setValidationError("Ilość akcesoriów nie może przekraczać ilości całkowitej");
      return;
    }
    if (accessoriesQuantity === undefined && !formState.accessories_to_count) {
      setValidationError("Dla akcesoriów podaj ilość albo zaznacz 'Do policzenia na produkcji'");
      return;
    }

    if (profilesQuantity !== undefined && accessoriesQuantity !== undefined && profilesQuantity + accessoriesQuantity !== totalQuantity) {
      setValidationError("Suma profili i akcesoriów musi być równa ilości całkowitej");
      return;
    }

    if (!formState.planned_pickup_date) {
      setValidationError("Termin odbioru jest wymagany");
      return;
    }

    const totalArea = parseOptionalPositiveNumber(formState.total_area_m2);
    if (totalArea === undefined) {
      setValidationError("Powierzchnia całkowita jest wymagana");
      return;
    }
    if (Number.isNaN(totalArea)) {
      setValidationError("Powierzchnia całkowita musi być dodatnią liczbą");
      return;
    }

    setValidationError(null);
    setApiError(null);
    setIsSubmitting(true);

    try {
      await createWorkOrder({
        total_quantity: totalQuantity,
        coating_type: formState.coating_type,
        decoral_foil_id:
          formState.coating_type === "DECORAL" && formState.decoral_foil_id ? Number(formState.decoral_foil_id) : undefined,
        work_order_kind: formState.work_order_kind,
        is_ocynk: formState.is_ocynk,
        external_order_number: formState.external_order_number.trim() || undefined,
        description: formState.description.trim() || undefined,
        customer_name: trimmedCustomerName,
        ral_code: trimmedRalCode,
        paint_code: trimmedPaintCode,
        paint_producer: trimmedPaintProducer,
        received_date: formState.received_date,
        planned_pickup_date: formState.planned_pickup_date,
        total_area_m2: totalArea,
        is_incomplete_on_arrival: formState.is_incomplete_on_arrival,
        profiles_quantity: profilesQuantity,
        profiles_to_count: formState.profiles_to_count,
        accessories_quantity: accessoriesQuantity,
        accessories_to_count: formState.accessories_to_count,
        notes: formState.notes.trim() || undefined,
      });
      navigate("/zlecenia");
    } catch (error) {
      setApiError(getLoadErrorMessage(error, "Nie udało się utworzyć zlecenia"));
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-4xl flex-col gap-6 px-4 py-8 sm:px-6 lg:px-8">
      <section className="rounded-[2rem] border border-white/70 bg-white/80 p-6 shadow-panel backdrop-blur sm:p-8">
        <div className="space-y-2">
          <p className="text-sm font-semibold uppercase tracking-[0.18em] text-accent">Dodaj zlecenie</p>
          <div>
            <h2 className="text-3xl font-semibold text-ink sm:text-4xl">Nowe zlecenie</h2>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-steel sm:text-base">
              Numer zlecenia nada backend. Uzupełnij dane biurowe potrzebne do poprawnego przyjęcia zlecenia do systemu.
            </p>
          </div>
        </div>
      </section>

      <section className="rounded-[2rem] border border-white/70 bg-white/80 p-6 shadow-panel backdrop-blur sm:p-8">
        <form className="space-y-6" onSubmit={handleSubmit}>
          <div className="grid gap-5 md:grid-cols-2">
            <label className="flex flex-col gap-2 md:col-span-2">
              <span className="text-sm font-medium text-ink">Opis</span>
              <textarea
                value={formState.description}
                onChange={(event) => updateField("description", event.target.value)}
                rows={4}
                className="rounded-2xl border border-line bg-white px-4 py-3 text-sm text-ink outline-none transition focus:border-accent"
                placeholder="Opis"
              />
            </label>

            <label className="flex flex-col gap-2">
              <span className="text-sm font-medium text-ink">Nr zewnętrzny</span>
              <input
                value={formState.external_order_number}
                onChange={(event) => updateField("external_order_number", event.target.value)}
                maxLength={128}
                className="rounded-2xl border border-line bg-white px-4 py-3 text-sm text-ink outline-none transition focus:border-accent"
                placeholder="Opcjonalnie"
              />
            </label>

            <label className="flex flex-col gap-2">
              <span className="text-sm font-medium text-ink">Klient</span>
              <input
                value={formState.customer_name}
                onChange={(event) => updateField("customer_name", event.target.value)}
                list="client-name-suggestions"
                className="rounded-2xl border border-line bg-white px-4 py-3 text-sm text-ink outline-none transition focus:border-accent"
                placeholder="Klient"
              />
              <datalist id="client-name-suggestions">
                {clientNameSuggestions.map((name) => (
                  <option key={name} value={name} />
                ))}
              </datalist>
            </label>

            <label className="flex flex-col gap-2">
              <span className="text-sm font-medium text-ink">Technologia</span>
              <select
                value={formState.coating_type}
                onChange={(event) => {
                  const nextCoating = event.target.value as CoatingTypeValue | "";
                  setFormState((current) => ({
                    ...current,
                    coating_type: nextCoating,
                    decoral_foil_id: nextCoating === "DECORAL" ? current.decoral_foil_id : "",
                  }));
                }}
                className="rounded-2xl border border-line bg-white px-4 py-3 text-sm text-ink outline-none transition focus:border-accent"
              >
                <option value="">Wybierz technologię</option>
                <option value="RAL">RAL</option>
                <option value="DECORAL">Decoral</option>
              </select>
            </label>

            {formState.coating_type === "DECORAL" && (
              <label className="flex flex-col gap-2">
                <span className="text-sm font-medium text-ink">Folia Decoral</span>
                <select
                  value={formState.decoral_foil_id}
                  onChange={(event) => updateField("decoral_foil_id", event.target.value)}
                  className="rounded-2xl border border-line bg-white px-4 py-3 text-sm text-ink outline-none transition focus:border-accent"
                >
                  <option value="">Bez folii / wybierz później</option>
                  {foils.map((foil) => (
                    <option key={foil.id} value={String(foil.id)}>
                      {foil.name} ({foil.code})
                    </option>
                  ))}
                </select>
              </label>
            )}

            <label className="flex flex-col gap-2">
              <span className="text-sm font-medium text-ink">Rodzaj zlecenia</span>
              <select
                value={formState.work_order_kind}
                onChange={(event) => updateField("work_order_kind", event.target.value as WorkOrderKindValue)}
                className="rounded-2xl border border-line bg-white px-4 py-3 text-sm text-ink outline-none transition focus:border-accent"
              >
                <option value="STANDARD">Standardowe</option>
                <option value="PRZEMALOWANKA">Przemalowanka</option>
              </select>
            </label>

            <label className="flex flex-col gap-2">
              <span className="text-sm font-medium text-ink">Kod RAL</span>
              <input
                value={formState.ral_code}
                onChange={(event) => updateField("ral_code", event.target.value)}
                className="rounded-2xl border border-line bg-white px-4 py-3 text-sm text-ink outline-none transition focus:border-accent"
                placeholder="np. RAL 7016"
              />
            </label>

            <label className="flex flex-col gap-2">
              <span className="text-sm font-medium text-ink">Producent farby</span>
              <input
                value={formState.paint_producer}
                onChange={(event) => updateField("paint_producer", event.target.value)}
                className="rounded-2xl border border-line bg-white px-4 py-3 text-sm text-ink outline-none transition focus:border-accent"
                placeholder="np. AkzoNobel"
              />
            </label>

            <label className="flex flex-col gap-2">
              <span className="text-sm font-medium text-ink">Kod farby</span>
              <input
                value={formState.paint_code}
                onChange={(event) => updateField("paint_code", event.target.value)}
                className="rounded-2xl border border-line bg-white px-4 py-3 text-sm text-ink outline-none transition focus:border-accent"
                placeholder="np. P-7016-MAT"
              />
            </label>

            <div className={["rounded-2xl border px-4 py-3 text-sm md:col-span-2", categoryQuantityHintClasses(paintAvailabilityHint.tone)].join(" ")}>
              {paintAvailabilityHint.text}
            </div>

            <label className="flex flex-col gap-2">
              <span className="text-sm font-medium text-ink">Data przyjęcia *</span>
              <input
                type="date"
                value={formState.received_date}
                onChange={(event) => updateField("received_date", event.target.value)}
                className="rounded-2xl border border-line bg-white px-4 py-3 text-sm text-ink outline-none transition focus:border-accent"
              />
            </label>

            <label className="flex flex-col gap-2">
              <span className="text-sm font-medium text-ink">Termin odbioru *</span>
              <input
                type="date"
                value={formState.planned_pickup_date}
                onChange={(event) => updateField("planned_pickup_date", event.target.value)}
                className="rounded-2xl border border-line bg-white px-4 py-3 text-sm text-ink outline-none transition focus:border-accent"
              />
            </label>

            <label className="flex flex-col gap-2">
              <span className="text-sm font-medium text-ink">Ilość całkowita</span>
              <NumberInput
                min="1"
                step="1"
                value={formState.total_quantity}
                onValueChange={(value) => updateField("total_quantity", value)}
                className="rounded-2xl border border-line bg-white px-4 py-3 text-sm text-ink outline-none transition focus:border-accent"
                placeholder="1"
              />
            </label>

            <label className="flex flex-col gap-2">
              <span className="text-sm font-medium text-ink">Powierzchnia całkowita (m²)</span>
              <NumberInput
                min="0"
                step="0.01"
                value={formState.total_area_m2}
                onValueChange={(value) => updateField("total_area_m2", value)}
                className="rounded-2xl border border-line bg-white px-4 py-3 text-sm text-ink outline-none transition focus:border-accent"
                placeholder="np. 42.5"
              />
            </label>

            <div className={["rounded-2xl border px-4 py-3 text-sm md:col-span-2", categoryQuantityHintClasses(predictedPaintHint.tone)].join(" ")}>
              {predictedPaintHint.text}
            </div>

            <label className="md:col-span-2 flex items-center gap-3 rounded-3xl border border-line/80 bg-mist/40 px-4 py-4 text-sm text-ink">
              <input
                type="checkbox"
                checked={formState.is_incomplete_on_arrival}
                onChange={(event) => setFormState((current) => ({ ...current, is_incomplete_on_arrival: event.target.checked }))}
                className="h-4 w-4 rounded border-line text-accent focus:ring-accent"
              />
              Zlecenie przyszło niekompletne
            </label>

            <label className="md:col-span-2 flex items-center gap-3 rounded-3xl border border-line/80 bg-mist/40 px-4 py-4 text-sm text-ink">
              <input
                type="checkbox"
                checked={formState.is_ocynk}
                onChange={(event) => setFormState((current) => ({ ...current, is_ocynk: event.target.checked }))}
                className="h-4 w-4 rounded border-line text-accent focus:ring-accent"
              />
              Ocynk
            </label>

            <div className="space-y-3 rounded-3xl border border-line/80 bg-mist/40 p-4">
              <div className="flex flex-col gap-2">
                <span className="text-sm font-medium text-ink">Profile</span>
                <NumberInput
                  min="0"
                  step="1"
                  disabled={formState.profiles_to_count}
                  value={formState.profiles_quantity}
                  onValueChange={(value) => updateField("profiles_quantity", value)}
                  className="rounded-2xl border border-line bg-white px-4 py-3 text-sm text-ink outline-none transition disabled:bg-slate-100 disabled:text-slate-400 focus:border-accent"
                  placeholder="Podaj ilość"
                />
              </div>
              <label className="flex items-center gap-3 text-sm text-steel">
                <input
                  type="checkbox"
                  checked={formState.profiles_to_count}
                  onChange={(event) => updateToggle("profiles_to_count", "profiles_quantity", event.target.checked)}
                  className="h-4 w-4 rounded border-line text-accent focus:ring-accent"
                />
                Do policzenia na produkcji
              </label>
            </div>

            <div className="space-y-3 rounded-3xl border border-line/80 bg-mist/40 p-4">
              <div className="flex flex-col gap-2">
                <span className="text-sm font-medium text-ink">Akcesoria</span>
                <NumberInput
                  min="0"
                  step="1"
                  disabled={formState.accessories_to_count}
                  value={formState.accessories_quantity}
                  onValueChange={(value) => updateField("accessories_quantity", value)}
                  className="rounded-2xl border border-line bg-white px-4 py-3 text-sm text-ink outline-none transition disabled:bg-slate-100 disabled:text-slate-400 focus:border-accent"
                  placeholder="Podaj ilość"
                />
              </div>
              <label className="flex items-center gap-3 text-sm text-steel">
                <input
                  type="checkbox"
                  checked={formState.accessories_to_count}
                  onChange={(event) => updateToggle("accessories_to_count", "accessories_quantity", event.target.checked)}
                  className="h-4 w-4 rounded border-line text-accent focus:ring-accent"
                />
                Do policzenia na produkcji
              </label>
            </div>

            <div className={["md:col-span-2 rounded-2xl border px-4 py-3 text-sm font-semibold", categoryQuantityHintClasses(categoryQuantityHint.tone)].join(" ")}>
              {categoryQuantityHint.text}
            </div>

            <label className="flex flex-col gap-2 md:col-span-2">
              <span className="text-sm font-medium text-ink">Uwagi</span>
              <textarea
                value={formState.notes}
                onChange={(event) => updateField("notes", event.target.value)}
                rows={4}
                className="rounded-2xl border border-line bg-white px-4 py-3 text-sm text-ink outline-none transition focus:border-accent"
                placeholder="Uwagi"
              />
            </label>
          </div>

          {validationError ? (
            <div className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">{validationError}</div>
          ) : null}

          {apiError ? (
            <div className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{apiError}</div>
          ) : null}

          <div className="flex flex-col gap-3 sm:flex-row sm:justify-end">
            <Link
              to="/zlecenia"
              className="inline-flex items-center justify-center rounded-full border border-line bg-white px-5 py-3 text-sm font-medium text-steel transition hover:border-accent hover:text-accent"
            >
              Anuluj
            </Link>
            <button
              type="submit"
              disabled={isSubmitting}
              className="inline-flex items-center justify-center rounded-full bg-accent px-5 py-3 text-sm font-medium text-white transition hover:bg-teal-700 disabled:cursor-not-allowed disabled:bg-teal-300"
            >
              {isSubmitting ? "Zapisywanie..." : "Zapisz"}
            </button>
          </div>
        </form>
      </section>
    </main>
  );
}
