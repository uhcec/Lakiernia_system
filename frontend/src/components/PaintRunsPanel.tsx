import { useEffect, useRef, useState } from "react";

import { fetchOpenPaintRuns, recordPaintRunConsumption } from "../api/processApi";
import { STATION_POLL_INTERVAL_MS, usePolling } from "../hooks/usePolling";
import type { PaintRun } from "../types/process";
import { getLoadErrorMessage } from "../utils/loadError";
import { getMutationErrorMessage } from "../utils/mutationError";
import {
  buildPaintCartonPreview,
  EMPTY_PAINT_CARTON_DRAFT,
  type PaintCartonDraft,
  type PaintCartonWeightKg,
} from "../utils/paintCartons";
import { NumberInput } from "./NumberInput";

// CHANGES #22: automatic-line paint consumption is entered once per paint run — same-paint orders hung
// back-to-back — and split onto the orders by m² on the backend. An open run blocks nothing; it is only
// flagged here (owner decision 2026-10-09). `mode="entry"` is the automatic-production station (form);
// `mode="alarm"` is the manager's read-only red banner for runs whose paint already changed.

type RunState = "OVERDUE" | "HANGING" | "CONTINUES" | "READY";

function getRunState(run: PaintRun): RunState {
  if (!run.is_current) {
    return "OVERDUE";
  }
  if (run.hanging_in_progress) {
    return "HANGING";
  }
  return run.next_in_queue_same_paint ? "CONTINUES" : "READY";
}

const RUN_STATE_TEXT: Record<RunState, string> = {
  OVERDUE: "Farba jest już zmieniona — wpisz zużycie tej grupy.",
  HANGING: "Trwa zawieszanie — zużycie wpiszesz po zakończeniu zawieszania.",
  CONTINUES: "Następne zlecenie w kolejce ma tę samą farbę — grupa trwa. Zużycie wpisz, gdy grupa się skończy.",
  READY: "Grupa zakończona — wpisz zużycie farby.",
};

const RUN_STATE_CLASSES: Record<RunState, string> = {
  OVERDUE: "border-rose-300 bg-rose-50",
  HANGING: "border-line bg-white",
  CONTINUES: "border-line bg-white",
  READY: "border-amber-300 bg-amber-50",
};

function formatPaintName(run: PaintRun): string {
  return `${run.ral_code} · ${run.paint_producer} · ${run.paint_code}`;
}

function formatKg(value: number | null): string {
  return typeof value === "number" ? `${value} kg` : "-";
}

export function PaintRunsPanel({ mode }: { mode: "entry" | "alarm" }) {
  const [runs, setRuns] = useState<PaintRun[]>([]);
  const [drafts, setDrafts] = useState<Record<number, PaintCartonDraft>>({});
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [submittingRunId, setSubmittingRunId] = useState<number | null>(null);
  const loadRequestSequenceRef = useRef(0);

  async function loadRuns(options?: { background?: boolean; preserveErrorMessage?: boolean }): Promise<void> {
    const requestId = ++loadRequestSequenceRef.current;
    try {
      const overview = await fetchOpenPaintRuns();
      if (requestId !== loadRequestSequenceRef.current) {
        return;
      }
      setRuns(overview.runs);
      if (!options?.background && !options?.preserveErrorMessage) {
        setErrorMessage(null);
      }
    } catch (error) {
      if (!options?.background && requestId === loadRequestSequenceRef.current) {
        setErrorMessage(getLoadErrorMessage(error, "Nie udało się pobrać grup farby"));
      }
    }
  }

  useEffect(() => {
    void loadRuns();
  }, []);

  usePolling(
    () => {
      void loadRuns({ background: true });
    },
    STATION_POLL_INTERVAL_MS,
    submittingRunId === null,
  );

  function updateDraft(runId: number, change: Partial<PaintCartonDraft>) {
    setDrafts((current) => ({
      ...current,
      [runId]: { ...(current[runId] ?? EMPTY_PAINT_CARTON_DRAFT), ...change },
    }));
  }

  async function handleRecord(run: PaintRun) {
    const preview = buildPaintCartonPreview(drafts[run.id] ?? EMPTY_PAINT_CARTON_DRAFT);
    if (preview.consumedPaintQuantityKg === null) {
      setErrorMessage(preview.errorMessage ?? "Wybierz wagę kartonu i dodaj pobrane kartony.");
      return;
    }

    setSubmittingRunId(run.id);
    setErrorMessage(null);
    try {
      await recordPaintRunConsumption(run.id, preview.consumedPaintQuantityKg);
      setDrafts((current) => {
        const next = { ...current };
        delete next[run.id];
        return next;
      });
      await loadRuns();
    } catch (error) {
      const message = getMutationErrorMessage(error, "Nie udało się zapisać zużycia farby.");
      await loadRuns({ preserveErrorMessage: true });
      setErrorMessage(message);
    } finally {
      setSubmittingRunId(null);
    }
  }

  if (mode === "alarm") {
    const overdueRuns = runs.filter((run) => !run.is_current);
    if (overdueRuns.length === 0) {
      return null;
    }
    return (
      <section className="rounded-2xl border border-rose-300 bg-rose-50 px-5 py-4 text-sm text-rose-800">
        <p className="font-semibold">
          {overdueRuns.length === 1
            ? "1 grupa farby na automacie nie ma wpisanego zużycia"
            : `${overdueRuns.length} grupy farby na automacie nie mają wpisanego zużycia`}
          {" "}(farba jest już zmieniona):
        </p>
        <ul className="mt-1 list-disc pl-5">
          {overdueRuns.map((run) => (
            <li key={run.id}>
              {formatPaintName(run)} — zlecenia {run.members.map((member) => member.order_number).join(", ")}
            </li>
          ))}
        </ul>
        <p className="mt-1">Zużycie wpisuje stanowisko Produkcja automat.</p>
      </section>
    );
  }

  return (
    <section className="rounded-[2rem] border border-white/70 bg-white/80 p-6 shadow-panel backdrop-blur sm:p-8">
      <div className="space-y-1">
        <h3 className="text-lg font-semibold text-ink">Zużycie farby — grupy</h3>
        <p className="text-sm text-steel">
          Zlecenia w tej samej farbie zawieszone jedno po drugim tworzą grupę. Zużycie wpisujesz raz dla całej grupy,
          a system dzieli je na zlecenia według m².
        </p>
      </div>

      {errorMessage ? (
        <p className="mt-4 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{errorMessage}</p>
      ) : null}

      {runs.length === 0 ? (
        <div className="mt-4 rounded-3xl border border-dashed border-line bg-mist px-6 py-8 text-center text-sm text-steel">
          Brak grup czekających na wpis zużycia.
        </div>
      ) : (
        <div className="mt-4 space-y-3">
          {runs.map((run) => {
            const state = getRunState(run);
            const draft = drafts[run.id] ?? EMPTY_PAINT_CARTON_DRAFT;
            const preview = buildPaintCartonPreview(draft);
            const isSubmitting = submittingRunId === run.id;
            const canRecord = !run.hanging_in_progress;

            return (
              <article key={run.id} className={["rounded-lg border p-5 text-ink shadow-sm", RUN_STATE_CLASSES[state]].join(" ")}>
                <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(14rem,18rem)]">
                  <div className="space-y-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-lg font-semibold">{formatPaintName(run)}</span>
                      <span className="inline-flex rounded-full bg-mist px-3 py-1 text-xs font-semibold text-steel">
                        Grupa nr {run.id}
                      </span>
                      {state === "OVERDUE" ? (
                        <span className="inline-flex rounded-full bg-rose-100 px-3 py-1 text-xs font-semibold text-rose-700">
                          BRAK WPISU
                        </span>
                      ) : null}
                    </div>
                    <p className={["text-sm font-medium", state === "OVERDUE" ? "text-rose-700" : state === "READY" ? "text-amber-800" : "text-steel"].join(" ")}>
                      {RUN_STATE_TEXT[state]}
                    </p>
                    <ul className="space-y-1 text-sm text-steel">
                      {run.members.map((member) => (
                        <li key={member.work_order_id}>
                          <span className="font-semibold text-ink">{member.order_number}</span> · {member.customer_name} · {member.area_m2} m²
                          {member.is_hanging ? " · w zawieszaniu" : ""}
                        </li>
                      ))}
                    </ul>
                    <p className="text-sm text-steel">Razem: {run.total_area_m2} m²</p>
                  </div>

                  <div className="space-y-3 border-t border-line/80 pt-4 lg:border-l lg:border-t-0 lg:pl-5 lg:pt-0">
                    <div className="space-y-2">
                      <p className="text-sm font-medium text-steel">Waga kartonu</p>
                      <div className="flex gap-2">
                        {([20, 25] as PaintCartonWeightKg[]).map((weight) => (
                          <button
                            key={`${run.id}-${weight}`}
                            type="button"
                            onClick={() => updateDraft(run.id, { cartonWeightKg: weight })}
                            className={[
                              "inline-flex items-center justify-center rounded-lg border px-3 py-2 text-sm font-semibold transition",
                              draft.cartonWeightKg === weight
                                ? "border-accent bg-white text-accent"
                                : "border-line bg-white text-steel hover:border-accent hover:text-accent",
                            ].join(" ")}
                          >
                            {weight} kg
                          </button>
                        ))}
                      </div>
                    </div>

                    <div className="space-y-2">
                      <p className="text-sm font-medium text-steel">Pobrane kartony</p>
                      <div className="inline-flex items-center rounded-lg border border-line bg-white">
                        <button
                          type="button"
                          aria-label="Usuń karton"
                          onClick={() => {
                            const nextCount = Math.max(draft.cartonCount - 1, 0);
                            updateDraft(run.id, {
                              cartonCount: nextCount,
                              finalCartonRemainingKg: nextCount === 0 ? "" : draft.finalCartonRemainingKg,
                            });
                          }}
                          className="inline-flex h-11 w-11 items-center justify-center text-lg font-semibold text-steel transition hover:text-accent"
                        >
                          -
                        </button>
                        <span className="min-w-12 border-x border-line px-4 text-center text-base font-semibold text-ink">
                          {draft.cartonCount}
                        </span>
                        <button
                          type="button"
                          aria-label="Dodaj karton"
                          onClick={() => updateDraft(run.id, { cartonCount: draft.cartonCount + 1 })}
                          className="inline-flex h-11 w-11 items-center justify-center text-lg font-semibold text-steel transition hover:text-accent"
                        >
                          +
                        </button>
                      </div>
                    </div>

                    <label className="block space-y-1 text-sm font-medium text-steel">
                      <span>Pozostało w ostatnim kartonie [kg]</span>
                      <NumberInput
                        min={0}
                        step="0.01"
                        value={draft.finalCartonRemainingKg}
                        onValueChange={(value) => updateDraft(run.id, { finalCartonRemainingKg: value })}
                        className="w-full rounded-lg border border-line bg-white px-3 py-2 text-base font-semibold text-ink outline-none transition focus:border-accent focus:ring-2 focus:ring-accent/20"
                        placeholder="0"
                      />
                    </label>

                    <div className="space-y-1 text-sm">
                      <p className="text-steel">Pobrano z kartonów: {formatKg(preview.drawnPaintQuantityKg)}</p>
                      <p className="text-steel">Zużycie grupy do zapisu: {formatKg(preview.consumedPaintQuantityKg)}</p>
                    </div>
                    {preview.errorMessage ? <p className="text-sm text-amber-800">{preview.errorMessage}</p> : null}

                    <button
                      type="button"
                      disabled={isSubmitting || !canRecord || preview.consumedPaintQuantityKg === null}
                      onClick={() => void handleRecord(run)}
                      className="inline-flex w-full items-center justify-center rounded-lg border border-line bg-white px-4 py-3 text-sm font-semibold text-steel transition hover:border-accent hover:text-accent disabled:cursor-not-allowed disabled:border-line disabled:text-slate-400"
                    >
                      {isSubmitting ? "Zapisywanie..." : "Zapisz zużycie grupy"}
                    </button>
                  </div>
                </div>
              </article>
            );
          })}
        </div>
      )}
    </section>
  );
}
