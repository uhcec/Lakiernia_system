import { FormEvent, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import {
  Check,
  ChevronDown,
  ChevronUp,
  FileText,
  Package,
  Phone,
  Plus,
  Search,
  Trash2,
  X,
} from "lucide-react";

import { createClient, deleteClient, fetchClientDetail, fetchClients, updateClient } from "../api/clientsApi";
import { buildWorkOrderDetailHref } from "../api/stationContext";
import type { Client, ClientDetail, ClientOrderHistoryItem } from "../types/clients";
import type { ProcessStatusValue, WorkOrderStatusValue } from "../types/workOrders";

// ─── Helpers ──────────────────────────────────────────────────────────────────

const inputClass =
  "w-full rounded-2xl border border-[#ece7f4] bg-[#f4f0fb] px-4 py-3 text-sm text-[#2e1a47] outline-none transition placeholder:text-[#a89fba] focus-visible:border-[#f2761b] focus-visible:ring-2 focus-visible:ring-[#f2761b]/30";

function getInitials(name: string): string {
  return name
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0].toUpperCase())
    .join("");
}

// Maps ProcessStatusValue → active step index (steps 0-4; 5 = all done)
const PROCESS_STATUS_STEP: Record<ProcessStatusValue, number> = {
  TO_BE_PLANNED: 0,
  INCOMPLETE: 0,
  SURFACE_PREPARATION: 1,
  HANGING: 2,
  PRODUCTION_MANUAL: 2,
  PRODUCTION_AUTOMATIC: 2,
  PACKING: 3,
  WAITING_FOR_CORRECTIONS: 3,
  DECORAL_PRODUCTION: 4,
  READY: 5,
};

// Fallback when process_status is absent
const LEGACY_STATUS_STEP: Record<WorkOrderStatusValue, number> = {
  ENTERED: 0,
  INCOMPLETE: 0,
  ASSIGNED: 1,
  IN_PROGRESS: 2,
  FINISHED: 5,
};

const STEPPER_STEPS = [
  "Wprowadzone",
  "Przygotowanie",
  "Produkcja",
  "Pakowanie",
  "Gotowe",
];

function StatusStepper({
  processStatusValue,
  legacyStatusValue,
}: {
  processStatusValue: ProcessStatusValue | null;
  legacyStatusValue: WorkOrderStatusValue;
}) {
  const current =
    processStatusValue != null
      ? (PROCESS_STATUS_STEP[processStatusValue] ?? 0)
      : (LEGACY_STATUS_STEP[legacyStatusValue] ?? 0);
  return (
    <div className="mt-3 flex items-start gap-0">
      {STEPPER_STEPS.map((label, i) => {
        const done = i < current;
        const active = i === current;
        const future = i > current;
        const isLast = i === STEPPER_STEPS.length - 1;
        return (
          <div key={label} className="flex flex-1 flex-col items-center">
            <div className="flex w-full items-center">
              {/* Connector before */}
              <div
                className={[
                  "h-0.5 flex-1",
                  i === 0 ? "invisible" : done || active ? "bg-[#f2761b]" : "bg-[#ece7f4]",
                ].join(" ")}
              />
              {/* Node */}
              <div
                className={[
                  "flex h-6 w-6 shrink-0 items-center justify-center rounded-full border-2 transition-all",
                  done
                    ? "border-[#2e1a47] bg-[#2e1a47]"
                    : active
                    ? "border-[#f2761b] bg-[#f2761b] ring-4 ring-[#fff1e4]"
                    : "border-[#ece7f4] bg-white",
                ].join(" ")}
              >
                {done && <Check className="h-3 w-3 text-white" strokeWidth={2.5} />}
                {active && <div className="h-2 w-2 rounded-full bg-white" />}
              </div>
              {/* Connector after */}
              <div
                className={[
                  "h-0.5 flex-1",
                  isLast ? "invisible" : done ? "bg-[#f2761b]" : "bg-[#ece7f4]",
                ].join(" ")}
              />
            </div>
            <p
              className={[
                "mt-1 text-center text-[10px] font-semibold leading-tight",
                active ? "text-[#f2761b]" : future ? "text-[#a89fba]" : "text-[#7b7390]",
              ].join(" ")}
            >
              {label}
            </p>
          </div>
        );
      })}
    </div>
  );
}

function StatusChip({ label, value }: { label: string; value: WorkOrderStatusValue }) {
  const isFinished = value === "FINISHED";
  const isInProgress = value === "IN_PROGRESS";
  return (
    <span
      className={[
        "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold",
        isFinished
          ? "bg-[#e6f6ef] text-[#1f9d6b]"
          : isInProgress
          ? "bg-[#fff1e4] text-[#f2761b]"
          : "bg-[#f4f0fb] text-[#7b7390]",
      ].join(" ")}
    >
      {label}
    </span>
  );
}

const PRODUCTION_TYPE_ICON: Record<string, string> = {
  MANUAL: "✋",
  AUTOMATIC: "⚙️",
};

function OrderHistoryCard({ order }: { order: ClientOrderHistoryItem }) {
  return (
    <div className="rounded-2xl border border-[#ece7f4] bg-white p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <Link
            to={buildWorkOrderDetailHref(order.id)}
            className="text-sm font-bold text-[#f2761b] hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#f2761b]/50"
          >
            {order.order_number}
          </Link>
          {order.external_order_number && (
            <span className="ml-2 text-xs text-[#a89fba]">({order.external_order_number})</span>
          )}
          <p className="mt-0.5 text-sm font-semibold text-[#2e1a47]">{order.title}</p>
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          {order.production_type && (
            <span className="inline-flex items-center gap-1 rounded-full border border-[#ece7f4] bg-[#f4f0fb] px-2.5 py-0.5 text-xs font-semibold text-[#7b7390]">
              <span>{PRODUCTION_TYPE_ICON[order.production_type.value] ?? ""}</span>
              {order.production_type.label}
            </span>
          )}
          <StatusChip label={order.status.label} value={order.status.value} />
        </div>
      </div>
      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-[#7b7390]">
        <span>Ilość: <strong className="text-[#2e1a47]">{order.total_quantity}</strong></span>
        <span>Przyjęto: <strong className="text-[#2e1a47]">{order.received_date}</strong></span>
        {order.planned_pickup_date && (
          <span>Odbiór: <strong className="text-[#2e1a47]">{order.planned_pickup_date}</strong></span>
        )}
        <span>RAL: <strong className="text-[#2e1a47]">{order.ral_code}</strong></span>
      </div>
      <StatusStepper
        processStatusValue={order.process_status?.value ?? null}
        legacyStatusValue={order.status.value}
      />
    </div>
  );
}

// ─── Main component ────────────────────────────────────────────────────────────

export function ClientsPage() {
  const [clients, setClients] = useState<Client[]>([]);
  const [search, setSearch] = useState("");
  const [selectedClientId, setSelectedClientId] = useState<number | null>(null);
  const [detail, setDetail] = useState<ClientDetail | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Add form state
  const [isAddFormOpen, setIsAddFormOpen] = useState(false);
  const [newName, setNewName] = useState("");
  const [newPhone, setNewPhone] = useState("");
  const [newNip, setNewNip] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  // Edit form state
  const [editName, setEditName] = useState("");
  const [editPhone, setEditPhone] = useState("");
  const [editNip, setEditNip] = useState("");
  const [isUpdating, setIsUpdating] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  const addFormRef = useRef<HTMLDivElement>(null);
  const nameInputRef = useRef<HTMLInputElement>(null);

  // Listen for topbar "Dodaj klienta" button event
  useEffect(() => {
    function handleOpenForm() {
      setIsAddFormOpen(true);
      setTimeout(() => {
        addFormRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
        setTimeout(() => nameInputRef.current?.focus(), 250);
      }, 50);
    }
    document.addEventListener("clients:open-add-form", handleOpenForm);
    return () => document.removeEventListener("clients:open-add-form", handleOpenForm);
  }, []);

  async function loadClients(searchValue: string) {
    setIsLoading(true);
    setErrorMessage(null);
    try {
      const response = await fetchClients(searchValue);
      setClients(response.items);
      setSelectedClientId((current) => {
        if (current !== null && response.items.some((client) => client.id === current)) {
          return current;
        }
        return response.items[0]?.id ?? null;
      });
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Nie udało się pobrać klientów");
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    const timeout = setTimeout(() => {
      void loadClients(search);
    }, 250);
    return () => clearTimeout(timeout);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search]);

  useEffect(() => {
    if (selectedClientId === null) {
      setDetail(null);
      return;
    }

    let isActive = true;

    function doFetch(isInitial: boolean) {
      fetchClientDetail(selectedClientId!)
        .then((response) => {
          if (!isActive) return;
          setDetail(response);
          if (isInitial) {
            setEditName(response.company_name);
            setEditPhone(response.contact_phone ?? "");
            setEditNip(response.nip ?? "");
          }
        })
        .catch((error) => {
          if (!isActive || !isInitial) return;
          setDetailError(error instanceof Error ? error.message : "Nie udało się pobrać danych klienta");
        });
    }

    setDetailError(null);
    doFetch(true);

    const interval = setInterval(() => doFetch(false), 15_000);

    return () => {
      isActive = false;
      clearInterval(interval);
    };
  }, [selectedClientId]);

  async function handleCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setCreateError(null);
    if (!newName.trim()) {
      setCreateError("Nazwa firmy jest wymagana.");
      return;
    }
    setIsSaving(true);
    try {
      const created = await createClient({
        company_name: newName.trim(),
        contact_phone: newPhone.trim() || null,
        nip: newNip.trim() || null,
      });
      setNewName("");
      setNewPhone("");
      setNewNip("");
      setIsAddFormOpen(false);
      await loadClients(search);
      setSelectedClientId(created.id);
    } catch (error) {
      setCreateError(error instanceof Error ? error.message : "Nie udało się zapisać klienta");
    } finally {
      setIsSaving(false);
    }
  }

  async function handleUpdate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (selectedClientId === null) return;
    setDetailError(null);
    if (!editName.trim()) {
      setDetailError("Nazwa firmy jest wymagana.");
      return;
    }
    setIsUpdating(true);
    try {
      await updateClient(selectedClientId, {
        company_name: editName.trim(),
        contact_phone: editPhone.trim(),
        nip: editNip.trim(),
      });
      await loadClients(search);
      const refreshed = await fetchClientDetail(selectedClientId);
      setDetail(refreshed);
    } catch (error) {
      setDetailError(error instanceof Error ? error.message : "Nie udało się zaktualizować klienta");
    } finally {
      setIsUpdating(false);
    }
  }

  async function handleDelete() {
    if (selectedClientId === null || detail === null) return;
    if (!window.confirm(`Usunąć klienta "${detail.company_name}"? Zlecenia pozostaną bez zmian.`)) {
      return;
    }
    setDetailError(null);
    try {
      await deleteClient(selectedClientId);
      setSelectedClientId(null);
      setDetail(null);
      await loadClients(search);
    } catch (error) {
      setDetailError(error instanceof Error ? error.message : "Nie udało się usunąć klienta");
    }
  }

  const totalOrders = clients.reduce((sum, c) => sum + c.order_count, 0);

  return (
    <div className="space-y-4">

      {/* Intro row */}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-[1.9rem] bg-white px-6 py-4 shadow-panel ring-1 ring-[#ece7f4]">
        <p className="text-sm text-[#7b7390]">
          Rejestr nazw firm i telefonów. Historia zleceń łączona po nazwie firmy ze zlecenia.
        </p>
        <div className="flex gap-3">
          <div className="rounded-2xl border border-[#ece7f4] bg-[#f4f0fb] px-4 py-2 text-center">
            <p className="text-[10px] font-semibold uppercase tracking-widest text-[#a89fba]">Klientów</p>
            <p className="text-lg font-bold text-[#2e1a47]">{clients.length}</p>
          </div>
          <div className="rounded-2xl border border-[#ece7f4] bg-[#f4f0fb] px-4 py-2 text-center">
            <p className="text-[10px] font-semibold uppercase tracking-widest text-[#a89fba]">Zleceń łącznie</p>
            <p className="text-lg font-bold text-[#2e1a47]">{totalOrders}</p>
          </div>
        </div>
      </div>

      {/* Main grid */}
      <div className="grid gap-4 lg:grid-cols-[380px_1fr]">

        {/* LEFT column */}
        <div className="flex flex-col gap-4">

          {/* Client list */}
          <div className="rounded-[1.9rem] bg-white p-5 shadow-panel ring-1 ring-[#ece7f4]">
            <div className="flex items-center justify-between gap-3">
              <h2 className="text-base font-bold text-[#2e1a47]">Lista klientów</h2>
              <span className="rounded-full bg-[#f4f0fb] px-3 py-1 text-xs font-semibold text-[#7b7390]">
                {clients.length}
              </span>
            </div>

            {/* Search */}
            <div className="relative mt-3">
              <Search className="absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-[#a89fba]" strokeWidth={1.8} />
              <input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Szukaj po nazwie firmy…"
                className="w-full rounded-2xl border border-[#ece7f4] bg-[#f4f0fb] py-2.5 pl-10 pr-4 text-sm text-[#2e1a47] outline-none transition placeholder:text-[#a89fba] focus-visible:border-[#f2761b] focus-visible:ring-2 focus-visible:ring-[#f2761b]/30"
              />
            </div>

            {/* List */}
            <div className="mt-3 max-h-80 overflow-y-auto space-y-1.5 lg:max-h-[420px]">
              {isLoading ? (
                <div className="rounded-2xl border border-dashed border-[#ece7f4] bg-[#f4f0fb] px-4 py-10 text-center text-sm text-[#a89fba]">
                  Ładowanie…
                </div>
              ) : errorMessage ? (
                <div className="rounded-2xl border border-[#f6d3da] bg-[#fdedf0] px-4 py-10 text-center text-sm text-[#d6455d]">
                  {errorMessage}
                </div>
              ) : clients.length === 0 ? (
                <div className="rounded-2xl border border-dashed border-[#ece7f4] bg-[#f4f0fb] px-4 py-10 text-center text-sm text-[#a89fba]">
                  Brak klientów
                </div>
              ) : (
                clients.map((client) => (
                  <button
                    key={client.id}
                    type="button"
                    onClick={() => setSelectedClientId(client.id)}
                    className={[
                      "flex w-full items-center justify-between gap-3 rounded-2xl border px-4 py-3 text-left transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#f2761b]/50",
                      selectedClientId === client.id
                        ? "border-[#f2761b] bg-[#f4f0fb]"
                        : "border-[#ece7f4] bg-white hover:border-[#ece7f4] hover:bg-[#f4f0fb]/60",
                    ].join(" ")}
                  >
                    <div className="min-w-0">
                      <p className="truncate text-sm font-semibold text-[#2e1a47]">{client.company_name}</p>
                      <p className="truncate text-xs text-[#7b7390]">
                        {client.contact_phone || "Brak telefonu"}
                        {client.nip ? ` · NIP ${client.nip}` : ""}
                      </p>
                    </div>
                    <span className="shrink-0 rounded-full bg-[#f4f0fb] px-2.5 py-0.5 text-xs font-semibold text-[#7b7390]">
                      {client.order_count} zlec.
                    </span>
                  </button>
                ))
              )}
            </div>
          </div>

          {/* Add client form (collapsible) */}
          <div ref={addFormRef} className="rounded-[1.9rem] bg-white shadow-panel ring-1 ring-[#ece7f4] overflow-hidden">
            <button
              type="button"
              onClick={() => setIsAddFormOpen((v) => !v)}
              className="flex w-full items-center justify-between gap-3 px-5 py-4 text-left transition hover:bg-[#f4f0fb]/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[#f2761b]/50"
            >
              <span className="flex items-center gap-2 text-sm font-bold text-[#2e1a47]">
                <Plus className="h-4 w-4 text-[#f2761b]" strokeWidth={2} />
                Dodaj nowego klienta
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
                  placeholder="Nazwa firmy *"
                  className={inputClass}
                />
                <input
                  value={newPhone}
                  onChange={(event) => setNewPhone(event.target.value)}
                  placeholder="Telefon kontaktowy (opcjonalny)"
                  className={inputClass}
                />
                <input
                  value={newNip}
                  onChange={(event) => setNewNip(event.target.value)}
                  placeholder="NIP (opcjonalny)"
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
                    {isSaving ? "Zapisywanie…" : "Zapisz klienta"}
                  </button>
                  <button
                    type="button"
                    onClick={() => { setIsAddFormOpen(false); setCreateError(null); }}
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
          {detail === null ? (
            <div className="flex h-full min-h-[300px] items-center justify-center rounded-2xl border border-dashed border-[#ece7f4] bg-[#f4f0fb]">
              <p className="text-sm text-[#a89fba]">Wybierz klienta z listy, aby zobaczyć dane i historię zleceń.</p>
            </div>
          ) : (
            <div className="space-y-6">

              {/* Client header */}
              <div className="flex flex-wrap items-start gap-4">
                <div className="flex h-[54px] w-[54px] shrink-0 items-center justify-center rounded-2xl bg-[#2e1a47] text-lg font-bold text-white">
                  {getInitials(detail.company_name)}
                </div>
                <div className="min-w-0 flex-1">
                  <h2 className="text-lg font-bold text-[#2e1a47]">{detail.company_name}</h2>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {detail.contact_phone && (
                      <span className="inline-flex items-center gap-1.5 rounded-full border border-[#ece7f4] bg-[#f4f0fb] px-3 py-1 text-xs text-[#7b7390]">
                        <Phone className="h-3 w-3" strokeWidth={1.8} />
                        {detail.contact_phone}
                      </span>
                    )}
                    {detail.nip && (
                      <span className="inline-flex items-center gap-1.5 rounded-full border border-[#ece7f4] bg-[#f4f0fb] px-3 py-1 text-xs text-[#7b7390]">
                        <FileText className="h-3 w-3" strokeWidth={1.8} />
                        NIP {detail.nip}
                      </span>
                    )}
                    <span className="inline-flex items-center gap-1.5 rounded-full border border-[#ece7f4] bg-[#f4f0fb] px-3 py-1 text-xs text-[#7b7390]">
                      <Package className="h-3 w-3" strokeWidth={1.8} />
                      {detail.orders.length} zleceń
                    </span>
                  </div>
                </div>
              </div>

              {/* Edit form */}
              <div className="rounded-2xl border border-[#ece7f4] bg-[#f4f0fb]/50 p-4">
                <h3 className="mb-3 text-sm font-bold text-[#2e1a47]">Dane klienta</h3>
                <form className="grid gap-3 sm:grid-cols-2" onSubmit={handleUpdate}>
                  <label className="space-y-1">
                    <span className="text-[10px] font-semibold uppercase tracking-widest text-[#a89fba]">Nazwa firmy</span>
                    <input value={editName} onChange={(event) => setEditName(event.target.value)} className={inputClass} />
                  </label>
                  <label className="space-y-1">
                    <span className="text-[10px] font-semibold uppercase tracking-widest text-[#a89fba]">Telefon kontaktowy</span>
                    <input value={editPhone} onChange={(event) => setEditPhone(event.target.value)} className={inputClass} />
                  </label>
                  <label className="space-y-1 sm:col-span-2">
                    <span className="text-[10px] font-semibold uppercase tracking-widest text-[#a89fba]">NIP</span>
                    <input value={editNip} onChange={(event) => setEditNip(event.target.value)} className={inputClass} />
                  </label>
                  {detailError && (
                    <p className="sm:col-span-2 rounded-xl bg-[#fdedf0] px-3 py-2 text-xs text-[#d6455d]">{detailError}</p>
                  )}
                  <div className="sm:col-span-2 flex flex-wrap gap-2">
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
                      Usuń klienta
                    </button>
                  </div>
                </form>
              </div>

              {/* Order history */}
              <div>
                <h3 className="mb-3 text-sm font-bold text-[#2e1a47]">
                  Historia zleceń
                  <span className="ml-2 rounded-full bg-[#f4f0fb] px-2.5 py-0.5 text-xs font-semibold text-[#7b7390]">
                    {detail.orders.length}
                  </span>
                </h3>
                {detail.orders.length === 0 ? (
                  <div className="rounded-2xl border border-dashed border-[#ece7f4] bg-[#f4f0fb] px-4 py-10 text-center text-sm text-[#a89fba]">
                    Brak zleceń powiązanych z tą nazwą firmy.
                  </div>
                ) : (
                  <div className="space-y-3">
                    {detail.orders.map((order) => (
                      <OrderHistoryCard key={order.id} order={order} />
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
