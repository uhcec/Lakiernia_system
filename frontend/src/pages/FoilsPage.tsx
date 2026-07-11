import { FormEvent, useEffect, useRef, useState } from "react";
import { Check, ChevronDown, ChevronUp, Layers, Plus, Search, Trash2, Truck, X } from "lucide-react";

import { useConfirm } from "../components/ConfirmDialog";
import { createFoil, deleteFoil, fetchFoils, updateFoil } from "../api/foilsApi";
import type { Foil } from "../types/foils";
import { getLoadErrorMessage } from "../utils/loadError";

const inputClass =
  "w-full rounded-2xl border border-[#ece7f4] bg-[#f4f0fb] px-4 py-3 text-sm text-[#2e1a47] outline-none transition placeholder:text-[#a89fba] focus-visible:border-[#f2761b] focus-visible:ring-2 focus-visible:ring-[#f2761b]/30";

export function FoilsPage() {
  const confirm = useConfirm();
  const [foils, setFoils] = useState<Foil[]>([]);
  const [search, setSearch] = useState("");
  const [selectedFoilId, setSelectedFoilId] = useState<number | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Add form state
  const [isAddFormOpen, setIsAddFormOpen] = useState(false);
  const [newName, setNewName] = useState("");
  const [newCode, setNewCode] = useState("");
  const [newSupplier, setNewSupplier] = useState("");
  const [newNotes, setNewNotes] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  // Edit form state
  const [editName, setEditName] = useState("");
  const [editCode, setEditCode] = useState("");
  const [editSupplier, setEditSupplier] = useState("");
  const [editNotes, setEditNotes] = useState("");
  const [isUpdating, setIsUpdating] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  const addFormRef = useRef<HTMLDivElement>(null);
  const nameInputRef = useRef<HTMLInputElement>(null);

  // Listen for topbar "Dodaj folię" button event
  useEffect(() => {
    function handleOpenForm() {
      setIsAddFormOpen(true);
      setTimeout(() => {
        addFormRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
        setTimeout(() => nameInputRef.current?.focus(), 250);
      }, 50);
    }
    document.addEventListener("foils:open-add-form", handleOpenForm);
    return () => document.removeEventListener("foils:open-add-form", handleOpenForm);
  }, []);

  async function loadFoils(searchValue: string) {
    setIsLoading(true);
    setErrorMessage(null);
    try {
      const response = await fetchFoils(searchValue);
      setFoils(response.items);
      setSelectedFoilId((current) => {
        if (current !== null && response.items.some((foil) => foil.id === current)) {
          return current;
        }
        return response.items[0]?.id ?? null;
      });
    } catch (error) {
      setErrorMessage(getLoadErrorMessage(error, "Nie udało się pobrać folii"));
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    const timeout = setTimeout(() => {
      void loadFoils(search);
    }, 250);
    return () => clearTimeout(timeout);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search]);

  const selectedFoil = foils.find((foil) => foil.id === selectedFoilId) ?? null;

  useEffect(() => {
    if (selectedFoil === null) {
      return;
    }
    setDetailError(null);
    setEditName(selectedFoil.name);
    setEditCode(selectedFoil.code);
    setEditSupplier(selectedFoil.supplier ?? "");
    setEditNotes(selectedFoil.notes ?? "");
  }, [selectedFoilId]); // eslint-disable-line react-hooks/exhaustive-deps

  async function handleCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setCreateError(null);
    if (!newName.trim()) {
      setCreateError("Nazwa folii jest wymagana.");
      return;
    }
    if (!newCode.trim()) {
      setCreateError("Kod folii jest wymagany.");
      return;
    }
    setIsSaving(true);
    try {
      const created = await createFoil({
        name: newName.trim(),
        code: newCode.trim(),
        supplier: newSupplier.trim() || null,
        notes: newNotes.trim() || null,
      });
      setNewName("");
      setNewCode("");
      setNewSupplier("");
      setNewNotes("");
      setIsAddFormOpen(false);
      await loadFoils(search);
      setSelectedFoilId(created.id);
    } catch (error) {
      setCreateError(getLoadErrorMessage(error, "Nie udało się zapisać folii"));
    } finally {
      setIsSaving(false);
    }
  }

  async function handleUpdate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (selectedFoilId === null) return;
    setDetailError(null);
    if (!editName.trim()) {
      setDetailError("Nazwa folii jest wymagana.");
      return;
    }
    if (!editCode.trim()) {
      setDetailError("Kod folii jest wymagany.");
      return;
    }
    setIsUpdating(true);
    try {
      await updateFoil(selectedFoilId, {
        name: editName.trim(),
        code: editCode.trim(),
        supplier: editSupplier.trim(),
        notes: editNotes.trim(),
      });
      await loadFoils(search);
    } catch (error) {
      setDetailError(getLoadErrorMessage(error, "Nie udało się zaktualizować folii"));
    } finally {
      setIsUpdating(false);
    }
  }

  async function handleDelete() {
    if (selectedFoil === null) return;
    const confirmed = await confirm({
      title: "Usunąć folię?",
      message: `Usunąć folię "${selectedFoil.name}"? Powiązane zlecenia stracą wybór folii.`,
      confirmLabel: "Usuń",
      tone: "danger",
    });
    if (!confirmed) {
      return;
    }
    setDetailError(null);
    try {
      await deleteFoil(selectedFoil.id);
      setSelectedFoilId(null);
      await loadFoils(search);
    } catch (error) {
      setDetailError(getLoadErrorMessage(error, "Nie udało się usunąć folii"));
    }
  }

  return (
    <div className="space-y-4">
      {/* Intro row */}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-[1.9rem] bg-white px-6 py-4 shadow-panel ring-1 ring-[#ece7f4]">
        <p className="text-sm text-[#7b7390]">
          Rejestr folii Decoral. Folię wybiera się przy dodawaniu zlecenia w technologii Decoral.
        </p>
        <div className="rounded-2xl border border-[#ece7f4] bg-[#f4f0fb] px-4 py-2 text-center">
          <p className="text-[10px] font-semibold uppercase tracking-widest text-[#a89fba]">Folii</p>
          <p className="text-lg font-bold text-[#2e1a47]">{foils.length}</p>
        </div>
      </div>

      {/* Main grid */}
      <div className="grid gap-4 lg:grid-cols-[380px_1fr]">
        {/* LEFT column */}
        <div className="flex flex-col gap-4">
          {/* Foil list */}
          <div className="rounded-[1.9rem] bg-white p-5 shadow-panel ring-1 ring-[#ece7f4]">
            <div className="flex items-center justify-between gap-3">
              <h2 className="text-base font-bold text-[#2e1a47]">Lista folii</h2>
              <span className="rounded-full bg-[#f4f0fb] px-3 py-1 text-xs font-semibold text-[#7b7390]">
                {foils.length}
              </span>
            </div>

            {/* Search */}
            <div className="relative mt-3">
              <Search className="absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-[#a89fba]" strokeWidth={1.8} />
              <input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Szukaj po nazwie lub kodzie…"
                className="w-full rounded-2xl border border-[#ece7f4] bg-[#f4f0fb] py-2.5 pl-10 pr-4 text-sm text-[#2e1a47] outline-none transition placeholder:text-[#a89fba] focus-visible:border-[#f2761b] focus-visible:ring-2 focus-visible:ring-[#f2761b]/30"
              />
            </div>

            {/* List */}
            <div className="mt-3 max-h-80 space-y-1.5 overflow-y-auto lg:max-h-[420px]">
              {isLoading ? (
                <div className="rounded-2xl border border-dashed border-[#ece7f4] bg-[#f4f0fb] px-4 py-10 text-center text-sm text-[#a89fba]">
                  Ładowanie…
                </div>
              ) : errorMessage ? (
                <div className="rounded-2xl border border-[#f6d3da] bg-[#fdedf0] px-4 py-10 text-center text-sm text-[#d6455d]">
                  {errorMessage}
                </div>
              ) : foils.length === 0 ? (
                <div className="rounded-2xl border border-dashed border-[#ece7f4] bg-[#f4f0fb] px-4 py-10 text-center text-sm text-[#a89fba]">
                  Brak folii
                </div>
              ) : (
                foils.map((foil) => (
                  <button
                    key={foil.id}
                    type="button"
                    onClick={() => setSelectedFoilId(foil.id)}
                    className={[
                      "flex w-full items-center justify-between gap-3 rounded-2xl border px-4 py-3 text-left transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#f2761b]/50",
                      selectedFoilId === foil.id
                        ? "border-[#f2761b] bg-[#f4f0fb]"
                        : "border-[#ece7f4] bg-white hover:border-[#ece7f4] hover:bg-[#f4f0fb]/60",
                    ].join(" ")}
                  >
                    <div className="min-w-0">
                      <p className="truncate text-sm font-semibold text-[#2e1a47]">{foil.name}</p>
                      <p className="truncate text-xs text-[#7b7390]">
                        {foil.code}
                        {foil.supplier ? ` · ${foil.supplier}` : ""}
                      </p>
                    </div>
                    <span className="shrink-0 rounded-full bg-[#f4f0fb] px-2.5 py-0.5 text-xs font-semibold text-[#7b7390]">
                      {foil.usage_count} zlec.
                    </span>
                  </button>
                ))
              )}
            </div>
          </div>

          {/* Add foil form (collapsible) */}
          <div ref={addFormRef} className="overflow-hidden rounded-[1.9rem] bg-white shadow-panel ring-1 ring-[#ece7f4]">
            <button
              type="button"
              onClick={() => setIsAddFormOpen((v) => !v)}
              className="flex w-full items-center justify-between gap-3 px-5 py-4 text-left transition hover:bg-[#f4f0fb]/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[#f2761b]/50"
            >
              <span className="flex items-center gap-2 text-sm font-bold text-[#2e1a47]">
                <Plus className="h-4 w-4 text-[#f2761b]" strokeWidth={2} />
                Dodaj nową folię
              </span>
              {isAddFormOpen ? (
                <ChevronUp className="h-4 w-4 text-[#a89fba]" strokeWidth={1.8} />
              ) : (
                <ChevronDown className="h-4 w-4 text-[#a89fba]" strokeWidth={1.8} />
              )}
            </button>

            {isAddFormOpen && (
              <form className="space-y-3 border-t border-[#ece7f4] px-5 pb-5 pt-4" onSubmit={handleCreate}>
                <input
                  ref={nameInputRef}
                  value={newName}
                  onChange={(event) => setNewName(event.target.value)}
                  placeholder="Nazwa folii *"
                  className={inputClass}
                />
                <input
                  value={newCode}
                  onChange={(event) => setNewCode(event.target.value)}
                  placeholder="Kod folii *"
                  className={inputClass}
                />
                <input
                  value={newSupplier}
                  onChange={(event) => setNewSupplier(event.target.value)}
                  placeholder="Dostawca (opcjonalny)"
                  className={inputClass}
                />
                <textarea
                  value={newNotes}
                  onChange={(event) => setNewNotes(event.target.value)}
                  placeholder="Notatki (opcjonalne)"
                  rows={3}
                  className={inputClass}
                />
                {createError && (
                  <p className="rounded-xl bg-[#fdedf0] px-3 py-2 text-xs text-[#d6455d]">{createError}</p>
                )}
                <div className="flex gap-2">
                  <button
                    type="submit"
                    disabled={isSaving}
                    className="inline-flex items-center gap-2 rounded-full bg-[#2e1a47] px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-[#3d2560] disabled:cursor-not-allowed disabled:opacity-60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#f2761b]/50"
                  >
                    <Check className="h-4 w-4" strokeWidth={2} />
                    {isSaving ? "Zapisywanie…" : "Zapisz folię"}
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setIsAddFormOpen(false);
                      setCreateError(null);
                    }}
                    className="inline-flex items-center gap-2 rounded-full border border-[#ece7f4] bg-[#f4f0fb] px-4 py-2.5 text-sm font-semibold text-[#7b7390] transition hover:bg-[#ece7f4] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#f2761b]/50"
                  >
                    <X className="h-4 w-4" strokeWidth={2} />
                    Anuluj
                  </button>
                </div>
              </form>
            )}
          </div>
        </div>

        {/* RIGHT column */}
        <div className="rounded-[1.9rem] bg-white p-5 shadow-panel ring-1 ring-[#ece7f4] sm:p-6">
          {selectedFoil === null ? (
            <div className="flex h-full min-h-[300px] items-center justify-center rounded-2xl border border-dashed border-[#ece7f4] bg-[#f4f0fb]">
              <p className="text-sm text-[#a89fba]">Wybierz folię z listy, aby zobaczyć i edytować dane.</p>
            </div>
          ) : (
            <div className="space-y-6">
              {/* Foil header */}
              <div className="flex flex-wrap items-start gap-4">
                <div className="flex h-[54px] w-[54px] shrink-0 items-center justify-center rounded-2xl bg-[#2e1a47] text-white">
                  <Layers className="h-6 w-6" strokeWidth={1.8} />
                </div>
                <div className="min-w-0 flex-1">
                  <h2 className="text-lg font-bold text-[#2e1a47]">{selectedFoil.name}</h2>
                  <div className="mt-2 flex flex-wrap gap-2">
                    <span className="inline-flex items-center gap-1.5 rounded-full border border-[#ece7f4] bg-[#f4f0fb] px-3 py-1 text-xs text-[#7b7390]">
                      Kod {selectedFoil.code}
                    </span>
                    {selectedFoil.supplier && (
                      <span className="inline-flex items-center gap-1.5 rounded-full border border-[#ece7f4] bg-[#f4f0fb] px-3 py-1 text-xs text-[#7b7390]">
                        <Truck className="h-3 w-3" strokeWidth={1.8} />
                        {selectedFoil.supplier}
                      </span>
                    )}
                    <span className="inline-flex items-center gap-1.5 rounded-full border border-[#ece7f4] bg-[#f4f0fb] px-3 py-1 text-xs text-[#7b7390]">
                      {selectedFoil.usage_count} zleceń
                    </span>
                  </div>
                </div>
              </div>

              {/* Edit form */}
              <div className="rounded-2xl border border-[#ece7f4] bg-[#f4f0fb]/50 p-4">
                <h3 className="mb-3 text-sm font-bold text-[#2e1a47]">Dane folii</h3>
                <form className="grid gap-3 sm:grid-cols-2" onSubmit={handleUpdate}>
                  <label className="space-y-1">
                    <span className="text-[10px] font-semibold uppercase tracking-widest text-[#a89fba]">Nazwa</span>
                    <input value={editName} onChange={(event) => setEditName(event.target.value)} className={inputClass} />
                  </label>
                  <label className="space-y-1">
                    <span className="text-[10px] font-semibold uppercase tracking-widest text-[#a89fba]">Kod</span>
                    <input value={editCode} onChange={(event) => setEditCode(event.target.value)} className={inputClass} />
                  </label>
                  <label className="space-y-1 sm:col-span-2">
                    <span className="text-[10px] font-semibold uppercase tracking-widest text-[#a89fba]">Dostawca</span>
                    <input value={editSupplier} onChange={(event) => setEditSupplier(event.target.value)} className={inputClass} />
                  </label>
                  <label className="space-y-1 sm:col-span-2">
                    <span className="text-[10px] font-semibold uppercase tracking-widest text-[#a89fba]">Notatki</span>
                    <textarea value={editNotes} onChange={(event) => setEditNotes(event.target.value)} rows={3} className={inputClass} />
                  </label>
                  {detailError && (
                    <p className="rounded-xl bg-[#fdedf0] px-3 py-2 text-xs text-[#d6455d] sm:col-span-2">{detailError}</p>
                  )}
                  <div className="flex flex-wrap gap-2 sm:col-span-2">
                    <button
                      type="submit"
                      disabled={isUpdating}
                      className="inline-flex items-center gap-2 rounded-full bg-[#2e1a47] px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-[#3d2560] disabled:cursor-not-allowed disabled:opacity-60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#f2761b]/50"
                    >
                      <Check className="h-4 w-4" strokeWidth={2} />
                      {isUpdating ? "Zapisywanie…" : "Zapisz zmiany"}
                    </button>
                    <button
                      type="button"
                      onClick={handleDelete}
                      className="inline-flex items-center gap-2 rounded-full border border-[#f6d3da] bg-[#fdedf0] px-5 py-2.5 text-sm font-semibold text-[#d6455d] transition hover:bg-[#f9c8d0] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#d6455d]/40"
                    >
                      <Trash2 className="h-4 w-4" strokeWidth={1.8} />
                      Usuń folię
                    </button>
                  </div>
                </form>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
