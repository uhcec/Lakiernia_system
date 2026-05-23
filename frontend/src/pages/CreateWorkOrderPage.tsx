import { FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { createWorkOrder } from "../api/workOrdersApi";
import type { CoatingTypeValue } from "../types/workOrders";

interface FormState {
  title: string;
  coating_type: CoatingTypeValue | "";
  description: string;
  customer_name: string;
  due_date: string;
  notes: string;
}

const initialFormState: FormState = {
  title: "",
  coating_type: "",
  description: "",
  customer_name: "",
  due_date: "",
  notes: "",
};

export function CreateWorkOrderPage() {
  const navigate = useNavigate();
  const [formState, setFormState] = useState<FormState>(initialFormState);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [apiError, setApiError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  function updateField(fieldName: keyof FormState, value: string) {
    setFormState((current) => ({ ...current, [fieldName]: value }));
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const trimmedTitle = formState.title.trim();
    if (!trimmedTitle) {
      setValidationError("Tytuł jest wymagany");
      return;
    }

    if (!formState.coating_type) {
      setValidationError("Technologia jest wymagana");
      return;
    }

    setValidationError(null);
    setApiError(null);
    setIsSubmitting(true);

    try {
      await createWorkOrder({
        title: trimmedTitle,
        coating_type: formState.coating_type,
        description: formState.description.trim() || undefined,
        customer_name: formState.customer_name.trim() || undefined,
        due_date: formState.due_date || undefined,
        notes: formState.notes.trim() || undefined,
      });
      navigate("/zlecenia");
    } catch (error) {
      setApiError(error instanceof Error ? error.message : "Nie udało się utworzyć zlecenia");
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
              Uzupełnij podstawowe dane zlecenia. Status oraz numer zlecenia zostaną nadane automatycznie przez system.
            </p>
          </div>
        </div>
      </section>

      <section className="rounded-[2rem] border border-white/70 bg-white/80 p-6 shadow-panel backdrop-blur sm:p-8">
        <form className="space-y-6" onSubmit={handleSubmit}>
          <div className="grid gap-5 md:grid-cols-2">
            <label className="flex flex-col gap-2 md:col-span-2">
              <span className="text-sm font-medium text-ink">Tytuł</span>
              <input
                value={formState.title}
                onChange={(event) => updateField("title", event.target.value)}
                className="rounded-2xl border border-line bg-white px-4 py-3 text-sm text-ink outline-none transition focus:border-accent"
                placeholder="Tytuł"
              />
            </label>

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
              <span className="text-sm font-medium text-ink">Klient</span>
              <input
                value={formState.customer_name}
                onChange={(event) => updateField("customer_name", event.target.value)}
                className="rounded-2xl border border-line bg-white px-4 py-3 text-sm text-ink outline-none transition focus:border-accent"
                placeholder="Klient"
              />
            </label>

            <label className="flex flex-col gap-2">
              <span className="text-sm font-medium text-ink">Technologia</span>
              <select
                value={formState.coating_type}
                onChange={(event) => updateField("coating_type", event.target.value as CoatingTypeValue | "")}
                className="rounded-2xl border border-line bg-white px-4 py-3 text-sm text-ink outline-none transition focus:border-accent"
              >
                <option value="">Wybierz technologię</option>
                <option value="RAL">RAL</option>
                <option value="DECORAL">Decoral</option>
              </select>
            </label>

            <label className="flex flex-col gap-2">
              <span className="text-sm font-medium text-ink">Termin</span>
              <input
                type="date"
                value={formState.due_date}
                onChange={(event) => updateField("due_date", event.target.value)}
                className="rounded-2xl border border-line bg-white px-4 py-3 text-sm text-ink outline-none transition focus:border-accent"
              />
            </label>

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