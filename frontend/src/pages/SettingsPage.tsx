import { FormEvent, useEffect, useState } from "react";

import {
  HANGING_MAX_ACTIVE_ORDERS_LIMIT,
  fetchShopSettings,
  updateShopSettings,
} from "../api/shopSettingsApi";
import { NumberInput } from "../components/NumberInput";
import { getLoadErrorMessage } from "../utils/loadError";
import { getMutationErrorMessage } from "../utils/mutationError";

// CHANGES #29 (owner 2026-10-15): shop-floor parameters the manager calibrates without a code change.
// Only the manager (and admin) sees this tab; the backend refuses everyone else.

const inputClass =
  "w-28 rounded-2xl border border-[#ece7f4] bg-[#f4f0fb] px-4 py-3 text-base font-semibold text-[#2e1a47] outline-none transition focus-visible:border-[#f2761b] focus-visible:ring-2 focus-visible:ring-[#f2761b]/30";

function parseLimit(value: string): number | null {
  const parsed = Number(value);
  if (!Number.isInteger(parsed) || parsed < 1 || parsed > HANGING_MAX_ACTIVE_ORDERS_LIMIT) {
    return null;
  }
  return parsed;
}

export function SettingsPage() {
  const [savedLimit, setSavedLimit] = useState<number | null>(null);
  const [draftLimit, setDraftLimit] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [savedMessage, setSavedMessage] = useState<string | null>(null);

  useEffect(() => {
    void (async () => {
      try {
        const settings = await fetchShopSettings();
        setSavedLimit(settings.hanging_max_active_orders);
        setDraftLimit(String(settings.hanging_max_active_orders));
      } catch (error) {
        setErrorMessage(getLoadErrorMessage(error, "Nie udało się pobrać ustawień"));
      } finally {
        setIsLoading(false);
      }
    })();
  }, []);

  const parsedLimit = parseLimit(draftLimit);
  const isDirty = parsedLimit !== null && parsedLimit !== savedLimit;

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (parsedLimit === null) {
      return;
    }
    setIsSaving(true);
    setErrorMessage(null);
    setSavedMessage(null);
    try {
      const settings = await updateShopSettings({ hanging_max_active_orders: parsedLimit });
      setSavedLimit(settings.hanging_max_active_orders);
      setDraftLimit(String(settings.hanging_max_active_orders));
      setSavedMessage("Zapisano. Zmiana działa od razu na stanowisku zawieszania.");
    } catch (error) {
      setErrorMessage(getMutationErrorMessage(error, "Nie udało się zapisać ustawień"));
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <main className="mx-auto flex w-full max-w-4xl flex-col gap-6 px-4 py-8 sm:px-6 lg:px-8">
      <section className="rounded-[2rem] border border-white/70 bg-white/80 p-6 shadow-panel backdrop-blur sm:p-8">
        <p className="text-sm font-semibold uppercase tracking-[0.18em] text-accent">Kierownik</p>
        <h2 className="text-3xl font-semibold text-ink sm:text-4xl">Ustawienia</h2>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-steel sm:text-base">
          Parametry hali, które można zmienić bez zmiany programu. Każda zmiana jest zapisywana w audycie.
        </p>
      </section>

      {errorMessage ? (
        <section className="rounded-2xl border border-rose-200 bg-rose-50 px-5 py-4 text-sm text-rose-700">{errorMessage}</section>
      ) : null}

      <section className="rounded-[2rem] border border-white/70 bg-white/80 p-6 shadow-panel backdrop-blur sm:p-8">
        {isLoading ? (
          <p className="text-sm text-steel">Ładowanie...</p>
        ) : (
          <form onSubmit={(event) => void handleSubmit(event)} className="space-y-4">
            <div className="space-y-1">
              <h3 className="text-lg font-semibold text-ink">Zawieszanie</h3>
              <label htmlFor="hanging-max-active" className="block text-sm text-steel">
                Ile zleceń można zawieszać jednocześnie. Zlecenia wieszane razem muszą mieć tę samą farbę
                (RAL, producent, kod). 1 = jedno zlecenie naraz.
              </label>
            </div>
            <div className="flex flex-wrap items-center gap-3">
              <NumberInput
                id="hanging-max-active"
                min={1}
                max={HANGING_MAX_ACTIVE_ORDERS_LIMIT}
                step={1}
                value={draftLimit}
                onValueChange={(value) => {
                  setDraftLimit(value);
                  setSavedMessage(null);
                }}
                className={inputClass}
              />
              <button
                type="submit"
                disabled={!isDirty || isSaving}
                className="inline-flex items-center justify-center rounded-2xl bg-gradient-to-r from-[#f2761b] to-[#f59446] px-5 py-3 text-sm font-semibold text-white shadow-lg shadow-[#f2761b]/30 transition disabled:cursor-not-allowed disabled:opacity-50"
              >
                {isSaving ? "Zapisywanie..." : "Zapisz"}
              </button>
            </div>
            {parsedLimit === null ? (
              <p className="text-sm text-rose-700">Podaj liczbę całkowitą od 1 do {HANGING_MAX_ACTIVE_ORDERS_LIMIT}.</p>
            ) : null}
            {savedMessage ? <p className="text-sm font-medium text-emerald-700">{savedMessage}</p> : null}
          </form>
        )}
      </section>
    </main>
  );
}
