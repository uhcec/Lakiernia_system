import { ChangeEvent, FormEvent, useCallback, useEffect, useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";

import { fetchWorkOrderAuditEvents } from "../api/auditApi";
import { buildWorkOrderDetailHref, getStationIdForLocation, getStationPanelPath } from "../api/stationContext";
import {
  deleteWorkOrderAttachment,
  fetchWorkOrder,
  fetchWorkOrderAttachments,
  getQualityControlDocumentUrl,
  openWorkOrderAttachment,
  markWorkOrderCompleteArrival,
  updateWorkOrder,
  updateWorkOrderReleaseStatus,
  uploadWorkOrderAttachment,
} from "../api/workOrdersApi";
import type { AuditEvent, AuditStationId } from "../types/audit";
import type { UpdateWorkOrderRequest, WorkOrder, WorkOrderAttachment, WorkOrderAttachmentCategory } from "../types/workOrders";
import { useConfirm } from "../components/ConfirmDialog";
import { downloadAuthedFile } from "../utils/download";
import { NumberInput } from "../components/NumberInput";
import { WorkOrderPrimaryInfoLine } from "../components/WorkOrderPrimaryInfoLine";
import {
  formatWorkOrderPrimaryInfo,
  getWorkOrderActiveCorrectionsText,
  getWorkOrderAttentionBadges,
  getWorkOrderBadgeStack,
  getWorkOrderCorrectionContextText,
  getWorkOrderDiscrepancyText,
  getHistoricalWorkOrderResultText,
  getWorkOrderProgressText,
  badgeClasses,
} from "../utils/workOrderDisplay";

const ALLOWED_ATTACHMENT_MIME_TYPES = ["application/pdf", "image/png", "image/jpeg"];

const ATTACHMENT_CATEGORY_LABELS: Record<WorkOrderAttachmentCategory, string> = {
  DOCUMENT: "Dokument",
  TECHNICAL_DRAWING: "Rysunek techniczny",
};

function processStatusClasses(statusValue: WorkOrder["process_status"]["value"]): string {
  switch (statusValue) {
    case "TO_BE_PLANNED":
      return "bg-slate-100 text-slate-700";
    case "INCOMPLETE":
      return "bg-rose-100 text-rose-700";
    case "SURFACE_PREPARATION":
      return "bg-amber-100 text-amber-800";
    case "HANGING":
      return "bg-sky-100 text-sky-700";
    case "PRODUCTION_MANUAL":
      return "bg-orange-100 text-orange-800";
    case "PRODUCTION_AUTOMATIC":
      return "bg-cyan-100 text-cyan-800";
    case "DECORAL_PRODUCTION":
      return "bg-violet-100 text-violet-800";
    case "PACKING":
      return "bg-lime-100 text-lime-800";
    case "WAITING_FOR_CORRECTIONS":
      return "bg-amber-200 text-amber-900";
    case "READY":
      return "bg-emerald-100 text-emerald-700";
  }
}

function formatDate(value: string | null): string {
  if (!value) {
    return "-";
  }

  return new Intl.DateTimeFormat("pl-PL").format(new Date(value));
}

function formatDateTime(value: string): string {
  return new Intl.DateTimeFormat("pl-PL", {
    dateStyle: "short",
    timeStyle: "short",
  }).format(new Date(value));
}

function formatCountOrFlag(quantity: number | null, toCount: boolean): string {
  if (toCount) {
    return "Do policzenia na produkcji";
  }

  return quantity === null ? "-" : String(quantity);
}

function formatPaintKg(value: number | null | undefined): string {
  return typeof value === "number" ? `${value} kg` : "-";
}

function formatFileSize(fileSize: number): string {
  if (fileSize < 1024) {
    return `${fileSize} B`;
  }

  if (fileSize < 1024 * 1024) {
    return `${(fileSize / 1024).toFixed(1)} KB`;
  }

  return `${(fileSize / (1024 * 1024)).toFixed(2)} MB`;
}

const stationLabels: Record<AuditStationId, string> = {
  OFFICE: "Biuro",
  MANAGER: "Kierownik",
  SURFACE_PREPARATION: "Przygotowanie",
  HANGING: "Zawieszanie",
  AUTOMATIC_PRODUCTION: "Produkcja automat",
  MANUAL_PRODUCTION: "Produkcja ręczna",
  PACKING: "Pakowanie",
  DECORAL_PRODUCTION: "Produkcja Decoral",
  SYSTEM: "System",
  UNKNOWN: "Nieznana stacja",
};

function formatAuditDetails(details: AuditEvent["details"]): string | null {
  if (!details || typeof details !== "object" || Array.isArray(details)) {
    return null;
  }

  const detailRecord = details as Record<string, unknown>;

  const updatedFields = detailRecord.updated_fields;
  if (Array.isArray(updatedFields) && updatedFields.length > 0) {
    return `Zmieniono: ${updatedFields.join(", ")}`;
  }

  const countedQuantity = detailRecord.counted_quantity;
  const okQuantity = detailRecord.ok_quantity;
  const correctionQuantity = detailRecord.correction_quantity;
  if (typeof countedQuantity === "number" && typeof okQuantity === "number" && typeof correctionQuantity === "number") {
    return `Policzono: ${countedQuantity} · OK: ${okQuantity} · Poprawki: ${correctionQuantity}`;
  }

  const stage = detailRecord.stage;
  const targetStatus = detailRecord.target_status;
  if (typeof stage === "string" && typeof targetStatus === "string") {
    return `${stage}: ${targetStatus}`;
  }

  const originalFilename = detailRecord.original_filename;
  if (typeof originalFilename === "string") {
    return originalFilename;
  }

  const correctionQuantityValue = detailRecord.correction_quantity;
  if (typeof correctionQuantityValue === "number") {
    return `Ilość poprawki: ${correctionQuantityValue}`;
  }

  return null;
}

function formatAuditDetailsJson(details: AuditEvent["details"]): string {
  if (details === null) {
    return "-";
  }

  return JSON.stringify(details, null, 2);
}

function isHistoricalWorkOrder(workOrder: WorkOrder): boolean {
  return workOrder.process_status.value === "READY";
}

interface EditFormState {
  title: string;
  external_order_number: string;
  customer_name: string;
  description: string;
  ral_code: string;
  paint_producer: string;
  paint_code: string;
  received_date: string;
  planned_pickup_date: string;
  total_area_m2: string;
  profiles_to_count: boolean;
  profiles_quantity: string;
  accessories_to_count: boolean;
  accessories_quantity: string;
  notes: string;
}

function buildEditFormState(wo: WorkOrder): EditFormState {
  return {
    title: wo.title ?? "",
    external_order_number: wo.external_order_number ?? "",
    customer_name: wo.customer_name,
    description: wo.description ?? "",
    ral_code: wo.ral_code,
    paint_producer: wo.paint_producer,
    paint_code: wo.paint_code ?? "",
    received_date: wo.received_date,
    planned_pickup_date: wo.planned_pickup_date ?? "",
    total_area_m2: wo.total_area_m2 != null ? String(wo.total_area_m2) : "",
    profiles_to_count: wo.profiles_to_count,
    profiles_quantity: wo.profiles_quantity != null ? String(wo.profiles_quantity) : "",
    accessories_to_count: wo.accessories_to_count,
    accessories_quantity: wo.accessories_quantity != null ? String(wo.accessories_quantity) : "",
    notes: wo.notes ?? "",
  };
}

function buildHistoricalCorrectionDeltaText(
  correctionOrder: WorkOrder["correction_orders"][number],
  parentWorkOrder: WorkOrder,
): string {
  return `Poprawiono ${correctionOrder.total_quantity} z ${parentWorkOrder.total_quantity} szt.`;
}

export function WorkOrderDetailPage() {
  const confirm = useConfirm();
  const { id } = useParams();
  const location = useLocation();
  const effectiveStationId = getStationIdForLocation(location.pathname, location.search);
  const canCompleteArrival = effectiveStationId === "OFFICE";
  const canManageAttachments = effectiveStationId === "OFFICE";
  const canUpdateReleaseStatus = effectiveStationId === "OFFICE";
  const canGenerateQualityControlDocument = effectiveStationId === "OFFICE";
  const canEditWorkOrder = effectiveStationId === "OFFICE" || effectiveStationId === "MANAGER";
  const [isDownloadingQcDoc, setIsDownloadingQcDoc] = useState(false);
  const [qcDocErrorMessage, setQcDocErrorMessage] = useState<string | null>(null);
  const [workOrder, setWorkOrder] = useState<WorkOrder | null>(null);
  const [attachments, setAttachments] = useState<WorkOrderAttachment[]>([]);
  const [auditEvents, setAuditEvents] = useState<AuditEvent[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isLoadingAttachments, setIsLoadingAttachments] = useState(true);
  const [isLoadingAuditEvents, setIsLoadingAuditEvents] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [attachmentsErrorMessage, setAttachmentsErrorMessage] = useState<string | null>(null);
  const [auditErrorMessage, setAuditErrorMessage] = useState<string | null>(null);
  const [uploadErrorMessage, setUploadErrorMessage] = useState<string | null>(null);
  const [isUpdatingArrival, setIsUpdatingArrival] = useState(false);
  const [isUpdatingReleaseStatus, setIsUpdatingReleaseStatus] = useState(false);
  const [isUploadingAttachment, setIsUploadingAttachment] = useState(false);
  const [deletingAttachmentId, setDeletingAttachmentId] = useState<number | null>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [attachmentCategory, setAttachmentCategory] = useState<WorkOrderAttachmentCategory>("DOCUMENT");
  const [attachmentType, setAttachmentType] = useState("");
  const [attachmentDescription, setAttachmentDescription] = useState("");
  const [isEditModalOpen, setIsEditModalOpen] = useState(false);
  const [editForm, setEditForm] = useState<EditFormState | null>(null);
  const [isSavingEdit, setIsSavingEdit] = useState(false);
  const [editErrorMessage, setEditErrorMessage] = useState<string | null>(null);

  const handleDownloadQcDocument = useCallback(async (wo: WorkOrder) => {
    setIsDownloadingQcDoc(true);
    setQcDocErrorMessage(null);
    try {
      await downloadAuthedFile(getQualityControlDocumentUrl(wo.id), `KJ_${wo.order_number}.pdf`);
    } catch {
      setQcDocErrorMessage("Nie udało się pobrać karty kontroli jakości.");
    } finally {
      setIsDownloadingQcDoc(false);
    }
  }, []);

  function handleOpenEditModal() {
    if (!workOrder) return;
    setEditForm(buildEditFormState(workOrder));
    setEditErrorMessage(null);
    setIsEditModalOpen(true);
  }

  function handleEditFormChange(field: keyof EditFormState, value: string | boolean) {
    setEditForm((prev) => (prev ? { ...prev, [field]: value } : prev));
  }

  async function handleSaveEdit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!id || !editForm) return;

    const payload: UpdateWorkOrderRequest = {};

    if (editForm.title.trim()) payload.title = editForm.title.trim();
    else payload.title = null;

    payload.external_order_number = editForm.external_order_number.trim() || null;
    payload.customer_name = editForm.customer_name.trim();
    payload.description = editForm.description.trim() || null;
    payload.ral_code = editForm.ral_code.trim();
    payload.paint_producer = editForm.paint_producer.trim();
    payload.paint_code = editForm.paint_code.trim() || null;
    payload.received_date = editForm.received_date;
    payload.planned_pickup_date = editForm.planned_pickup_date || null;
    payload.notes = editForm.notes.trim() || null;

    const areaValue = parseFloat(editForm.total_area_m2);
    if (!editForm.total_area_m2 || isNaN(areaValue) || areaValue <= 0) {
      setEditErrorMessage("Metraż musi być liczbą większą od 0.");
      return;
    }
    payload.total_area_m2 = areaValue;

    payload.profiles_to_count = editForm.profiles_to_count;
    if (editForm.profiles_to_count) {
      payload.profiles_quantity = null;
    } else {
      payload.profiles_quantity = editForm.profiles_quantity !== "" ? parseInt(editForm.profiles_quantity, 10) : null;
    }

    payload.accessories_to_count = editForm.accessories_to_count;
    if (editForm.accessories_to_count) {
      payload.accessories_quantity = null;
    } else {
      payload.accessories_quantity = editForm.accessories_quantity !== "" ? parseInt(editForm.accessories_quantity, 10) : null;
    }

    setIsSavingEdit(true);
    setEditErrorMessage(null);

    try {
      await updateWorkOrder(Number(id), payload);
      await Promise.all([loadWorkOrder(Number(id)), loadAuditEvents(Number(id))]);
      setIsEditModalOpen(false);
    } catch (error) {
      setEditErrorMessage(error instanceof Error ? error.message : "Nie udało się zapisać zmian");
    } finally {
      setIsSavingEdit(false);
    }
  }

  async function loadWorkOrder(workOrderId: number) {
    setIsLoading(true);
    setErrorMessage(null);

    try {
      const item = await fetchWorkOrder(workOrderId);
      setWorkOrder(item);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Nie udało się pobrać zlecenia");
    } finally {
      setIsLoading(false);
    }
  }

  async function loadAttachments(workOrderId: number) {
    setIsLoadingAttachments(true);
    setAttachmentsErrorMessage(null);

    try {
      const items = await fetchWorkOrderAttachments(workOrderId);
      setAttachments(items);
    } catch (error) {
      setAttachmentsErrorMessage(error instanceof Error ? error.message : "Nie udało się pobrać załączników");
    } finally {
      setIsLoadingAttachments(false);
    }
  }

  async function loadAuditEvents(workOrderId: number) {
    setIsLoadingAuditEvents(true);
    setAuditErrorMessage(null);

    try {
      const items = await fetchWorkOrderAuditEvents(workOrderId);
      setAuditEvents(items);
    } catch (error) {
      setAuditErrorMessage(error instanceof Error ? error.message : "Nie udało się pobrać historii zmian");
    } finally {
      setIsLoadingAuditEvents(false);
    }
  }

  useEffect(() => {
    let isActive = true;

    async function loadWorkOrderForEffect() {
      if (!id) {
        setErrorMessage("Nieprawidłowy identyfikator zlecenia");
        setIsLoading(false);
        return;
      }

      try {
        const workOrderId = Number(id);
        const [item, attachmentItems, auditItems] = await Promise.all([
          fetchWorkOrder(workOrderId),
          fetchWorkOrderAttachments(workOrderId),
          fetchWorkOrderAuditEvents(workOrderId).catch((error: unknown) => {
            if (isActive) {
              setAuditErrorMessage(error instanceof Error ? error.message : "Nie udało się pobrać historii zmian");
            }
            return [] as AuditEvent[];
          }),
        ]);
        if (!isActive) {
          return;
        }
        setErrorMessage(null);
        setWorkOrder(item);
        setAttachments(attachmentItems);
        setAuditEvents(auditItems);
        setAttachmentsErrorMessage(null);
      } catch (error) {
        if (!isActive) {
          return;
        }
        setErrorMessage(error instanceof Error ? error.message : "Nie udało się pobrać zlecenia");
      } finally {
        if (isActive) {
          setIsLoading(false);
          setIsLoadingAttachments(false);
          setIsLoadingAuditEvents(false);
        }
      }
    }

    void loadWorkOrderForEffect();

    return () => {
      isActive = false;
    };
  }, [id]);

  async function handleMarkCompleteArrival() {
    if (!id || !workOrder) {
      return;
    }

    const shouldContinue = await confirm({
      message: "Czy oznaczyć to zlecenie jako kompletne i przenieść do planowania?",
      confirmLabel: "Oznacz jako kompletne",
    });
    if (!shouldContinue) {
      return;
    }

    setIsUpdatingArrival(true);
    setErrorMessage(null);

    try {
      await markWorkOrderCompleteArrival(Number(id));
      await Promise.all([loadWorkOrder(Number(id)), loadAuditEvents(Number(id))]);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Nie udało się oznaczyć zlecenia jako kompletne");
    } finally {
      setIsUpdatingArrival(false);
    }
  }

  async function handleUpdateReleaseStatus(nextReleaseState: boolean) {
    if (!id || !workOrder) {
      return;
    }

    const shouldContinue = await confirm({
      message: nextReleaseState
        ? "Czy oznaczyć to zlecenie jako wydane klientowi?"
        : "Czy cofnąć oznaczenie wydania klientowi?",
      confirmLabel: nextReleaseState ? "Oznacz jako wydane" : "Cofnij wydanie",
    });
    if (!shouldContinue) {
      return;
    }

    setIsUpdatingReleaseStatus(true);
    setErrorMessage(null);

    try {
      await updateWorkOrderReleaseStatus(Number(id), nextReleaseState);
      await Promise.all([loadWorkOrder(Number(id)), loadAuditEvents(Number(id))]);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Nie udało się zmienić statusu wydania");
    } finally {
      setIsUpdatingReleaseStatus(false);
    }
  }

  function handleFileSelection(event: ChangeEvent<HTMLInputElement>) {
    const nextFile = event.target.files?.[0] ?? null;
    setSelectedFile(nextFile);
    setUploadErrorMessage(null);
  }

  async function handleAttachmentUpload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!id) {
      setUploadErrorMessage("Nieprawidłowy identyfikator zlecenia");
      return;
    }
    if (!selectedFile) {
      setUploadErrorMessage("Wybierz plik do przesłania.");
      return;
    }
    if (!ALLOWED_ATTACHMENT_MIME_TYPES.includes(selectedFile.type)) {
      setUploadErrorMessage("Dozwolone są tylko pliki PDF lub obrazy (PNG/JPG).");
      return;
    }

    setIsUploadingAttachment(true);
    setUploadErrorMessage(null);

    try {
      await uploadWorkOrderAttachment(Number(id), {
        file: selectedFile,
        category: attachmentCategory,
        attachmentType,
        description: attachmentDescription,
      });
      setSelectedFile(null);
      setAttachmentCategory("DOCUMENT");
      setAttachmentType("");
      setAttachmentDescription("");
      await Promise.all([loadAttachments(Number(id)), loadAuditEvents(Number(id))]);
    } catch (error) {
      setUploadErrorMessage(error instanceof Error ? error.message : "Nie udało się przesłać załącznika");
    } finally {
      setIsUploadingAttachment(false);
    }
  }

  async function handleAttachmentOpen(attachment: WorkOrderAttachment) {
    if (!workOrder) {
      return;
    }
    setAttachmentsErrorMessage(null);
    try {
      await openWorkOrderAttachment(workOrder.id, attachment.id);
    } catch (error) {
      setAttachmentsErrorMessage(error instanceof Error ? error.message : "Nie udało się otworzyć załącznika");
    }
  }

  async function handleAttachmentDelete(attachment: WorkOrderAttachment) {
    if (!id) {
      return;
    }

    const shouldContinue = await confirm({
      title: "Usunąć załącznik?",
      message: `Czy usunąć załącznik ${attachment.original_filename}?`,
      confirmLabel: "Usuń",
      tone: "danger",
    });
    if (!shouldContinue) {
      return;
    }

    setDeletingAttachmentId(attachment.id);
    setAttachmentsErrorMessage(null);

    try {
      await deleteWorkOrderAttachment(Number(id), attachment.id);
      await Promise.all([loadAttachments(Number(id)), loadAuditEvents(Number(id))]);
    } catch (error) {
      setAttachmentsErrorMessage(error instanceof Error ? error.message : "Nie udało się usunąć załącznika");
    } finally {
      setDeletingAttachmentId(null);
    }
  }

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-7xl flex-col gap-6 px-4 py-8 sm:px-6 lg:px-8">
      <section className="rounded-[2rem] border border-white/70 bg-white/80 p-6 shadow-panel backdrop-blur sm:p-8">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div className="space-y-2">
            <p className="text-sm font-semibold uppercase tracking-[0.18em] text-accent">Szczegóły zlecenia</p>
            <div>
              <h2 className="text-3xl font-semibold text-ink sm:text-4xl">{workOrder ? <WorkOrderPrimaryInfoLine workOrder={workOrder} /> : "Zlecenie"}</h2>
              <p className="mt-2 max-w-3xl text-sm leading-6 text-steel sm:text-base">
                Podgląd danych biurowych, planowania i aktualnych etapów procesu bez możliwości edycji.
              </p>
              {workOrder ? (
                <div className="mt-4 space-y-3">
                  <div className="flex flex-wrap gap-2">
                    {[...getWorkOrderBadgeStack(workOrder), ...getWorkOrderAttentionBadges(workOrder)].map((badge) => (
                      <span
                        key={`hero-${badge.label}`}
                        className={["inline-flex rounded-full px-3 py-1 text-xs font-semibold", badgeClasses(badge.tone)].join(" ")}
                      >
                        {badge.label}
                      </span>
                    ))}
                  </div>
                  <p className="text-lg font-semibold text-ink">{workOrder.process_status.label}</p>
                  {isHistoricalWorkOrder(workOrder) ? (
                    <p className="text-sm font-semibold text-emerald-700">{getHistoricalWorkOrderResultText(workOrder)}</p>
                  ) : (
                    <div className="flex flex-wrap gap-3 text-sm text-steel">
                      <span>Postęp: {getWorkOrderProgressText(workOrder)}</span>
                      {getWorkOrderActiveCorrectionsText(workOrder) ? <span>{getWorkOrderActiveCorrectionsText(workOrder)}</span> : null}
                    </div>
                  )}
                  {getWorkOrderCorrectionContextText(workOrder) ? (
                    <p className="text-sm text-amber-700">{getWorkOrderCorrectionContextText(workOrder)}</p>
                  ) : null}
                </div>
              ) : null}
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            {canGenerateQualityControlDocument && workOrder ? (
              <button
                onClick={() => handleDownloadQcDocument(workOrder)}
                disabled={isDownloadingQcDoc}
                className="inline-flex items-center justify-center rounded-full bg-accent px-5 py-3 text-sm font-medium text-white transition hover:bg-teal-700 disabled:opacity-60"
              >
                {isDownloadingQcDoc ? "Pobieranie…" : "Karta kontroli jakości"}
              </button>
            ) : null}
            {canEditWorkOrder && workOrder ? (
              <button
                onClick={handleOpenEditModal}
                className="inline-flex items-center justify-center rounded-full border border-accent bg-white px-5 py-3 text-sm font-medium text-accent transition hover:bg-accent hover:text-white"
              >
                Edytuj zlecenie
              </button>
            ) : null}
            <Link
              to={getStationPanelPath(effectiveStationId)}
              className="inline-flex items-center justify-center rounded-full border border-line bg-white px-5 py-3 text-sm font-medium text-steel transition hover:border-accent hover:text-accent"
            >
              Wróć do listy
            </Link>
          </div>
          {qcDocErrorMessage ? (
            <div className="mt-3 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
              {qcDocErrorMessage}
            </div>
          ) : null}
        </div>
      </section>

      {isLoading ? (
        <section className="rounded-[2rem] border border-white/70 bg-white/80 px-6 py-12 text-center text-base text-steel shadow-panel backdrop-blur">
          Ładowanie...
        </section>
      ) : errorMessage ? (
        <section className="rounded-[2rem] border border-rose-200 bg-rose-50 px-6 py-12 text-center text-base text-rose-700 shadow-panel">
          {errorMessage}
        </section>
      ) : workOrder ? (
        <>
          <section className="grid gap-6 lg:grid-cols-[1.5fr_1fr]">
            <div className="rounded-[2rem] border border-white/70 bg-white/80 p-6 shadow-panel backdrop-blur sm:p-8">
              <h3 className="text-2xl font-semibold text-ink">Dane zlecenia</h3>
              <dl className="mt-6 grid gap-5 md:grid-cols-2">
                <div>
                  <dt className="text-sm font-medium text-steel">Nr zlecenia</dt>
                  <dd className="mt-1 text-base font-semibold text-ink">{workOrder.order_number}</dd>
                </div>
                <div>
                  <dt className="text-sm font-medium text-steel">Nr zewnętrzny</dt>
                  <dd className="mt-1 text-base text-ink">{workOrder.external_order_number ?? "-"}</dd>
                </div>
                <div>
                  <dt className="text-sm font-medium text-steel">Dane główne</dt>
                  <dd className="mt-1 flex flex-wrap items-center gap-2 text-base font-semibold text-ink">
                    <WorkOrderPrimaryInfoLine workOrder={workOrder} />
                    {getWorkOrderBadgeStack(workOrder).map((badge) => (
                      <span
                        key={`details-${badge.label}`}
                        className={["inline-flex rounded-full px-3 py-1 text-xs font-semibold", badgeClasses(badge.tone)].join(" ")}
                      >
                        {badge.label}
                      </span>
                    ))}
                  </dd>
                </div>
                <div>
                  <dt className="text-sm font-medium text-steel">Firma</dt>
                  <dd className="mt-1 text-base text-ink">{workOrder.customer_name}</dd>
                </div>
                <div>
                  <dt className="text-sm font-medium text-steel">Technologia</dt>
                  <dd className="mt-1 text-base text-ink">{workOrder.coating_type.label}</dd>
                </div>
                {workOrder.coating_type.value === "DECORAL" && (
                  <div>
                    <dt className="text-sm font-medium text-steel">Folia Decoral</dt>
                    <dd className="mt-1 text-base text-ink">
                      {workOrder.decoral_foil ? `${workOrder.decoral_foil.name} (${workOrder.decoral_foil.code})` : "—"}
                    </dd>
                  </div>
                )}
                <div>
                  <dt className="text-sm font-medium text-steel">Kod RAL</dt>
                  <dd className="mt-1 text-base text-ink">{workOrder.ral_code}</dd>
                </div>
                <div>
                  <dt className="text-sm font-medium text-steel">Producent farby</dt>
                  <dd className="mt-1 text-base text-ink">{workOrder.paint_producer}</dd>
                </div>
                <div className="md:col-span-2">
                  <dt className="text-sm font-medium text-steel">Farba</dt>
                  <dd className="mt-2 rounded-3xl border border-line/80 bg-white px-5 py-4 text-base text-ink">
                    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                      <div className="rounded-2xl border border-line/70 bg-mist/35 px-4 py-3 min-w-0">
                        <p className="text-xs font-semibold uppercase tracking-[0.14em] text-steel">Kod farby</p>
                        <p className="mt-2 break-words font-semibold text-ink">{workOrder.paint_code ?? "-"}</p>
                      </div>
                      <div className="rounded-2xl border border-line/70 bg-mist/35 px-4 py-3 min-w-0">
                        <p className="text-xs font-semibold uppercase tracking-[0.14em] text-steel">Stan przy przyjęciu</p>
                        <p className="mt-2 font-semibold text-ink">{formatPaintKg(workOrder.paint_stock_snapshot_quantity_kg)}</p>
                      </div>
                      <div className="rounded-2xl border border-line/70 bg-mist/35 px-4 py-3 min-w-0">
                        <p className="text-xs font-semibold uppercase tracking-[0.14em] text-steel">Zużyto</p>
                        <p className="mt-2 font-semibold text-ink">{formatPaintKg(workOrder.consumed_paint_quantity_kg)}</p>
                      </div>
                      <div className="rounded-2xl border border-line/70 bg-mist/35 px-4 py-3 min-w-0">
                        <p className="text-xs font-semibold uppercase tracking-[0.14em] text-steel">Predykcja</p>
                        <p className="mt-2 font-semibold text-ink">{formatPaintKg(workOrder.predicted_paint_quantity_kg)}</p>
                      </div>
                    </div>
                    <p className="mt-4 text-sm text-steel">
                      Stan przy przyjęciu to historyczny snapshot zapisany automatycznie z magazynu podczas tworzenia lub
                      zmiany konfiguracji farby na zleceniu. Predykcja wynika z metrażu zlecenia i służy tylko jako
                      podpowiedź planistyczna. System nie pokazuje tutaj bieżącego globalnego stanu magazynu.
                    </p>
                  </dd>
                </div>
                <div>
                  <dt className="text-sm font-medium text-steel">Ilość całkowita</dt>
                  <dd className="mt-1 text-base text-ink">{workOrder.total_quantity}</dd>
                </div>
                <div>
                  <dt className="text-sm font-medium text-steel">Policzono na przygotowaniu</dt>
                  <dd className="mt-1 text-base text-ink">{workOrder.surface_preparation_counted_quantity ?? "-"}</dd>
                </div>
                {getWorkOrderDiscrepancyText(workOrder) ? (
                  <div className="md:col-span-2">
                    <dt className="text-sm font-medium text-steel">Rozbieżność ilości</dt>
                    <dd className="mt-1 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-base font-medium text-amber-800">
                      {getWorkOrderDiscrepancyText(workOrder)}
                    </dd>
                  </div>
                ) : null}
                {workOrder.quantity_leak_flagged ? (
                  <div className="md:col-span-2">
                    <dt className="text-sm font-medium text-steel">Wyciek ilości</dt>
                    <dd className="mt-1 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-base font-medium text-rose-800">
                      Zarejestrowane sztuki nie zgadzały się z całością przy zamknięciu zlecenia. Zlecenie
                      domknięto do pełnej ilości, ale rozbieżność wymaga sprawdzenia — prawdopodobny błąd
                      liczenia wyżej w procesie.
                    </dd>
                  </div>
                ) : null}
                {!isHistoricalWorkOrder(workOrder) ? (
                  <div>
                    <dt className="text-sm font-medium text-steel">Aktywna ilość</dt>
                    <dd className="mt-1 text-base text-ink">{workOrder.current_active_quantity}</dd>
                  </div>
                ) : null}
                <div>
                  <dt className="text-sm font-medium text-steel">Podsumowanie stanu</dt>
                  <dd className="mt-1 text-base font-semibold text-ink">{workOrder.process_status.label}</dd>
                </div>
                <div>
                  <dt className="text-sm font-medium text-steel">
                    {isHistoricalWorkOrder(workOrder) ? "Wynik końcowy" : "Postęp"}
                  </dt>
                  <dd className="mt-1 text-base text-ink">
                    {isHistoricalWorkOrder(workOrder) ? getHistoricalWorkOrderResultText(workOrder) : getWorkOrderProgressText(workOrder)}
                  </dd>
                </div>
                <div>
                  <dt className="text-sm font-medium text-steel">Data przyjęcia</dt>
                  <dd className="mt-1 text-base text-ink">{formatDate(workOrder.received_date)}</dd>
                </div>
                <div>
                  <dt className="text-sm font-medium text-steel">Planowany odbiór</dt>
                  <dd className="mt-1 text-base text-ink">{formatDate(workOrder.planned_pickup_date)}</dd>
                </div>
                <div>
                  <dt className="text-sm font-medium text-steel">Powierzchnia całkowita (m²)</dt>
                  <dd className="mt-1 text-base text-ink">{workOrder.total_area_m2 ?? "-"}</dd>
                </div>
                <div>
                  <dt className="text-sm font-medium text-steel">Kompletność przy przyjęciu</dt>
                  <dd className="mt-1 text-base text-ink">{workOrder.is_incomplete_on_arrival ? "Niekompletne" : "Kompletne"}</dd>
                </div>
                <div>
                  <dt className="text-sm font-medium text-steel">Profile</dt>
                  <dd className="mt-1 text-base text-ink">{formatCountOrFlag(workOrder.profiles_quantity, workOrder.profiles_to_count)}</dd>
                </div>
                <div>
                  <dt className="text-sm font-medium text-steel">Akcesoria</dt>
                  <dd className="mt-1 text-base text-ink">{formatCountOrFlag(workOrder.accessories_quantity, workOrder.accessories_to_count)}</dd>
                </div>
                <div className="md:col-span-2">
                  <dt className="text-sm font-medium text-steel">Uwagi</dt>
                  <dd className="mt-1 whitespace-pre-wrap text-base text-ink">{workOrder.notes || "-"}</dd>
                </div>
                <div className="md:col-span-2">
                  <dt className="text-sm font-medium text-steel">Zlecenie nadrzędne</dt>
                  <dd className="mt-1 text-base text-ink">
                    {workOrder.parent_order ? (
                      <Link to={buildWorkOrderDetailHref(workOrder.parent_order.id, effectiveStationId)} className="font-semibold text-accent hover:underline">
                        {formatWorkOrderPrimaryInfo(workOrder.parent_order)} · {workOrder.parent_order.total_quantity} szt.
                      </Link>
                    ) : (
                      "-"
                    )}
                  </dd>
                </div>
                <div className="md:col-span-2">
                  <dt className="text-sm font-medium text-steel">Zlecenia poprawek</dt>
                  <dd className="mt-1 text-base text-ink">
                    {workOrder.correction_orders.length > 0 ? (
                      <div className="flex flex-col gap-2">
                        {workOrder.correction_orders.map((correctionOrder) => (
                          <Link
                            key={correctionOrder.id}
                            to={buildWorkOrderDetailHref(correctionOrder.id, effectiveStationId)}
                            className="rounded-2xl border border-line/80 bg-white px-4 py-3 font-semibold text-accent hover:underline"
                          >
                            <div>{formatWorkOrderPrimaryInfo(correctionOrder)} · {correctionOrder.total_quantity} szt.</div>
                            <div className="mt-1 text-sm font-medium text-steel">
                              {correctionOrder.is_historical_correction
                                ? buildHistoricalCorrectionDeltaText(correctionOrder, workOrder)
                                : `Status: ${correctionOrder.process_status.label} · Postęp: ${correctionOrder.completed_quantity}/${correctionOrder.total_quantity}`}
                            </div>
                          </Link>
                        ))}
                      </div>
                    ) : (
                      "-"
                    )}
                  </dd>
                </div>
              </dl>
            </div>

            <div className="space-y-6">
              <section className="rounded-[2rem] border border-white/70 bg-white/80 p-6 shadow-panel backdrop-blur sm:p-8">
                <h3 className="text-2xl font-semibold text-ink">Planowanie</h3>
                <dl className="mt-6 space-y-5">
                  <div>
                    <dt className="text-sm font-medium text-steel">Typ produkcji</dt>
                    <dd className="mt-1 text-base text-ink">{workOrder.production_type?.label ?? "-"}</dd>
                  </div>
                  <div>
                    <dt className="text-sm font-medium text-steel">Pozycja w kolejce</dt>
                    <dd className="mt-1 text-base text-ink">{workOrder.queue_position ?? "-"}</dd>
                  </div>
                </dl>
              </section>

              <section className="rounded-[2rem] border border-white/70 bg-white/80 p-6 shadow-panel backdrop-blur sm:p-8">
                <h3 className="text-2xl font-semibold text-ink">Status procesu</h3>
                <div className={["mt-6 inline-flex rounded-full px-4 py-2 text-sm font-semibold", processStatusClasses(workOrder.process_status.value)].join(" ")}>
                  {workOrder.process_status.label}
                </div>
                {getWorkOrderActiveCorrectionsText(workOrder) ? (
                  <p className="mt-2 text-sm text-rose-700">{getWorkOrderActiveCorrectionsText(workOrder)}</p>
                ) : null}
                {isHistoricalWorkOrder(workOrder) ? (
                  <div className="mt-6 grid gap-3">
                    <div className="rounded-3xl border border-line/80 bg-white p-4">
                      <p className="text-xs font-semibold uppercase tracking-[0.14em] text-steel">Wynik końcowy</p>
                      <p className="mt-2 text-2xl font-semibold text-ink">{getHistoricalWorkOrderResultText(workOrder)}</p>
                    </div>
                    <div className="rounded-3xl border border-line/80 bg-white p-4">
                      <p className="text-xs font-semibold uppercase tracking-[0.14em] text-steel">Wydanie klientowi</p>
                      <p className="mt-2 text-lg font-semibold text-ink">
                        {workOrder.is_released_to_client ? "Wydane" : "Do wydania"}
                      </p>
                      {workOrder.released_to_client_at ? (
                        <p className="mt-1 text-sm text-steel">{formatDateTime(workOrder.released_to_client_at)}</p>
                      ) : null}
                      {canUpdateReleaseStatus ? (
                        <button
                          type="button"
                          onClick={() => void handleUpdateReleaseStatus(!workOrder.is_released_to_client)}
                          disabled={isUpdatingReleaseStatus}
                          className="mt-4 inline-flex items-center justify-center rounded-full bg-accent px-5 py-3 text-sm font-medium text-white transition hover:bg-teal-700 disabled:cursor-not-allowed disabled:bg-teal-300"
                        >
                          {isUpdatingReleaseStatus
                            ? "Zapisywanie..."
                            : workOrder.is_released_to_client
                              ? "Cofnij wydanie"
                              : "Oznacz jako wydane"}
                        </button>
                      ) : null}
                    </div>
                  </div>
                ) : (
                  <div className="mt-6 grid gap-3 sm:grid-cols-3">
                    <div className="rounded-3xl border border-line/80 bg-white p-4">
                      <p className="text-xs font-semibold uppercase tracking-[0.14em] text-steel">Łączny postęp</p>
                      <p className="mt-2 text-2xl font-semibold text-ink">
                        {getWorkOrderProgressText(workOrder)}
                      </p>
                    </div>
                    <div className="rounded-3xl border border-line/80 bg-white p-4">
                      <p className="text-xs font-semibold uppercase tracking-[0.14em] text-steel">OK w oczekiwaniu</p>
                      <p className="mt-2 text-2xl font-semibold text-ink">{workOrder.waiting_ok_quantity}</p>
                    </div>
                    <div className="rounded-3xl border border-line/80 bg-white p-4">
                      <p className="text-xs font-semibold uppercase tracking-[0.14em] text-steel">Poprawki w toku</p>
                      <p className="mt-2 text-2xl font-semibold text-ink">{workOrder.pending_correction_quantity}</p>
                    </div>
                  </div>
                )}
                {workOrder.correction_orders.length > 0 ? (
                  <div className="mt-6 space-y-3 rounded-3xl border border-line/80 bg-white p-5">
                    <p className="text-sm font-semibold uppercase tracking-[0.14em] text-steel">Statusy zleceń poprawek</p>
                    {workOrder.correction_orders.map((correctionOrder) => (
                      <Link
                        key={correctionOrder.id}
                        to={buildWorkOrderDetailHref(correctionOrder.id, effectiveStationId)}
                        className="flex flex-col gap-3 rounded-2xl border border-line/80 bg-mist/40 px-4 py-3 transition hover:border-accent/40"
                      >
                        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                          <span className="font-semibold text-ink">{correctionOrder.order_number}</span>
                          <span className={["inline-flex w-fit rounded-full px-3 py-1 text-xs font-semibold", processStatusClasses(correctionOrder.process_status.value)].join(" ")}>
                            {correctionOrder.process_status.label}
                          </span>
                        </div>
                        <p className="text-sm text-steel">{formatWorkOrderPrimaryInfo(correctionOrder)}</p>
                        {correctionOrder.is_historical_correction ? (
                          <p className="text-sm font-medium text-amber-700">
                            {buildHistoricalCorrectionDeltaText(correctionOrder, workOrder)}
                          </p>
                        ) : (
                          <p className="text-sm text-steel">
                            Postęp: {correctionOrder.completed_quantity}/{correctionOrder.total_quantity} · Aktywne: {correctionOrder.current_active_quantity}
                          </p>
                        )}
                      </Link>
                    ))}
                  </div>
                ) : null}
                {workOrder.process_status.value === "INCOMPLETE" && canCompleteArrival ? (
                  <button
                    type="button"
                    onClick={() => void handleMarkCompleteArrival()}
                    disabled={isUpdatingArrival}
                    className="mt-4 inline-flex items-center justify-center rounded-full bg-accent px-5 py-3 text-sm font-medium text-white transition hover:bg-teal-700 disabled:cursor-not-allowed disabled:bg-teal-300"
                  >
                    {isUpdatingArrival ? "Zapisywanie..." : "Oznacz jako kompletne"}
                  </button>
                ) : null}
              </section>
            </div>
          </section>

          <section className="rounded-[2rem] border border-white/70 bg-white/80 p-6 shadow-panel backdrop-blur sm:p-8">
            <h3 className="text-2xl font-semibold text-ink">Etapy</h3>
            <div className="mt-6 space-y-4">
              {workOrder.stage_states.map((stageState) => (
                <div key={stageState.stage.value} className="flex flex-col gap-3 rounded-3xl border border-line/80 bg-white p-5 sm:flex-row sm:items-center sm:justify-between">
                  <div>
                    <p className="text-base font-semibold text-ink">{stageState.stage.label}</p>
                  </div>
                  <span className="inline-flex w-fit rounded-full bg-mist px-3 py-1 text-xs font-semibold text-ink">
                    {stageState.status.label}
                  </span>
                </div>
              ))}
            </div>
          </section>

          <section className="rounded-[2rem] border border-white/70 bg-white/80 p-6 shadow-panel backdrop-blur sm:p-8">
            <h3 className="text-2xl font-semibold text-ink">Historia ilości</h3>
            <div className="mt-6 space-y-4">
              {workOrder.batches.map((batch) => (
                <div key={batch.id} className="rounded-3xl border border-line/80 bg-white p-5">
                  <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                    <div className="space-y-2">
                      <p className="text-base font-semibold text-ink">
                        {batch.type.value === "MAIN" ? "Partia główna" : "Poprawka"}: {batch.quantity} szt.
                      </p>
                      <p className="text-sm text-steel">Utworzono: {formatDateTime(batch.created_at)}</p>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {batch.is_active ? (
                        <span className="inline-flex rounded-full bg-amber-100 px-3 py-1 text-xs font-semibold text-amber-800">
                          Aktywna
                        </span>
                      ) : null}
                      {batch.is_finished ? (
                        <span className="inline-flex rounded-full bg-mist px-3 py-1 text-xs font-semibold text-ink">
                          Zakończona
                        </span>
                      ) : null}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </section>

          <section className="rounded-[2rem] border border-white/70 bg-white/80 p-6 shadow-panel backdrop-blur sm:p-8">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
              <div>
                <h3 className="text-2xl font-semibold text-ink">Załączniki</h3>
                <p className="mt-2 text-sm text-steel">Sekcja jest neutralna biznesowo i gotowa na kolejne typy oraz kategorie plików. Aktualnie dozwolone są tylko PDF.</p>
              </div>
            </div>

            {canManageAttachments ? (
              <form className="mt-6 grid gap-4 rounded-3xl border border-line/80 bg-white p-5 md:grid-cols-[1.1fr_0.9fr]" onSubmit={handleAttachmentUpload}>
                <div className="space-y-4">
                  <label className="flex flex-col gap-2">
                    <span className="text-sm font-medium text-ink">Plik (PDF lub obraz PNG/JPG)</span>
                    <input
                      type="file"
                      accept="application/pdf,.pdf,image/png,.png,image/jpeg,.jpg,.jpeg"
                      onChange={handleFileSelection}
                      className="rounded-2xl border border-line bg-white px-4 py-3 text-sm text-ink outline-none transition file:mr-4 file:rounded-full file:border-0 file:bg-mist file:px-4 file:py-2 file:text-sm file:font-medium file:text-ink hover:file:bg-line/40"
                    />
                  </label>
                  <p className="text-sm text-steel">{selectedFile ? `Wybrano: ${selectedFile.name}` : "Nie wybrano pliku"}</p>
                </div>

                <div className="grid gap-4">
                  <label className="flex flex-col gap-2">
                    <span className="text-sm font-medium text-ink">Kategoria</span>
                    <select
                      value={attachmentCategory}
                      onChange={(event) => setAttachmentCategory(event.target.value as WorkOrderAttachmentCategory)}
                      className="rounded-2xl border border-line bg-white px-4 py-3 text-sm text-ink outline-none transition focus:border-accent"
                    >
                      <option value="DOCUMENT">Dokument</option>
                      <option value="TECHNICAL_DRAWING">Rysunek techniczny</option>
                    </select>
                  </label>
                  <label className="flex flex-col gap-2">
                    <span className="text-sm font-medium text-ink">Typ załącznika</span>
                    <input
                      value={attachmentType}
                      onChange={(event) => setAttachmentType(event.target.value)}
                      className="rounded-2xl border border-line bg-white px-4 py-3 text-sm text-ink outline-none transition focus:border-accent"
                      placeholder="Np. SPEC, KARTA, OFERTA"
                    />
                  </label>
                  <label className="flex flex-col gap-2">
                    <span className="text-sm font-medium text-ink">Opis</span>
                    <textarea
                      value={attachmentDescription}
                      onChange={(event) => setAttachmentDescription(event.target.value)}
                      rows={3}
                      className="rounded-2xl border border-line bg-white px-4 py-3 text-sm text-ink outline-none transition focus:border-accent"
                      placeholder="Opcjonalny opis załącznika"
                    />
                  </label>
                  <div className="flex flex-wrap items-center gap-3">
                    <button
                      type="submit"
                      disabled={isUploadingAttachment}
                      className="inline-flex items-center justify-center rounded-full bg-accent px-5 py-3 text-sm font-medium text-white transition hover:bg-teal-700 disabled:cursor-not-allowed disabled:bg-teal-300"
                    >
                      {isUploadingAttachment ? "Przesyłanie..." : "Dodaj załącznik"}
                    </button>
                    <span className="text-sm text-steel">Maksymalny rozmiar kontroluje backend.</span>
                  </div>
                </div>
              </form>
            ) : null}

            {canManageAttachments && uploadErrorMessage ? (
              <div className="mt-4 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{uploadErrorMessage}</div>
            ) : null}

            {attachmentsErrorMessage ? (
              <div className="mt-4 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{attachmentsErrorMessage}</div>
            ) : null}

            {isLoadingAttachments ? (
              <div className="mt-6 rounded-3xl border border-line/80 bg-white px-5 py-8 text-center text-sm text-steel">Ładowanie załączników...</div>
            ) : attachments.length === 0 ? (
              <div className="mt-6 rounded-3xl border border-dashed border-line bg-white px-5 py-8 text-center text-sm text-steel">
                Brak załączników dla tego zlecenia.
              </div>
            ) : (
              <div className="mt-6 overflow-hidden rounded-3xl border border-line bg-white shadow-panel">
                <div className="overflow-x-auto">
                  <table className="min-w-full border-collapse text-left text-sm">
                    <thead className="bg-mist text-steel">
                      <tr>
                        <th className="px-5 py-4 font-semibold">Nazwa pliku</th>
                        <th className="px-5 py-4 font-semibold">Rozmiar</th>
                        <th className="px-5 py-4 font-semibold">Data dodania</th>
                        <th className="px-5 py-4 font-semibold">Kategoria</th>
                        <th className="px-5 py-4 font-semibold">Typ</th>
                        <th className="px-5 py-4 font-semibold">Opis</th>
                        <th className="px-5 py-4 font-semibold text-right">Akcje</th>
                      </tr>
                    </thead>
                    <tbody>
                      {attachments.map((attachment) => (
                        <tr key={attachment.id} className="border-t border-line/80 text-ink">
                          <td className="px-5 py-4 font-medium">{attachment.original_filename}</td>
                          <td className="px-5 py-4 text-steel">{formatFileSize(attachment.file_size)}</td>
                          <td className="px-5 py-4 text-steel">{formatDateTime(attachment.uploaded_at)}</td>
                          <td className="px-5 py-4 text-steel">{ATTACHMENT_CATEGORY_LABELS[attachment.category] ?? attachment.category}</td>
                          <td className="px-5 py-4 text-steel">{attachment.attachment_type ?? "-"}</td>
                          <td className="px-5 py-4 text-steel">{attachment.description ?? "-"}</td>
                          <td className="px-5 py-4">
                            <div className="flex justify-end gap-3">
                              <button
                                type="button"
                                onClick={() => void handleAttachmentOpen(attachment)}
                                className="inline-flex items-center justify-center rounded-full border border-line bg-white px-4 py-2 text-sm font-medium text-steel transition hover:border-accent hover:text-accent"
                              >
                                Otwórz
                              </button>
                              {canManageAttachments ? (
                                <button
                                  type="button"
                                  onClick={() => void handleAttachmentDelete(attachment)}
                                  disabled={deletingAttachmentId === attachment.id}
                                  className="inline-flex items-center justify-center rounded-full border border-rose-200 bg-rose-50 px-4 py-2 text-sm font-medium text-rose-700 transition hover:border-rose-300 hover:bg-rose-100 disabled:cursor-not-allowed disabled:opacity-60"
                                >
                                  {deletingAttachmentId === attachment.id ? "Usuwanie..." : "Usuń"}
                                </button>
                              ) : null}
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </section>

          <section className="rounded-[2rem] border border-white/70 bg-white/80 p-6 shadow-panel backdrop-blur sm:p-8">
            <h3 className="text-2xl font-semibold text-ink">Historia zmian</h3>

            {auditErrorMessage ? (
              <div className="mt-4 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">{auditErrorMessage}</div>
            ) : null}

            {isLoadingAuditEvents ? (
              <div className="mt-6 rounded-3xl border border-line/80 bg-white px-5 py-8 text-center text-sm text-steel">Ładowanie historii...</div>
            ) : auditEvents.length === 0 ? (
              <div className="mt-6 rounded-3xl border border-dashed border-line bg-white px-5 py-8 text-center text-sm text-steel">
                Brak zdarzeń historii dla tego zlecenia.
              </div>
            ) : (
              <div className="mt-6 space-y-4">
                {auditEvents.map((event) => {
                  const detailsText = formatAuditDetails(event.details);
                  return (
                    <article key={event.id} className="rounded-3xl border border-line/80 bg-white p-5">
                      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                        <div className="space-y-2">
                          <p className="text-base font-semibold text-ink">{event.summary}</p>
                          {detailsText ? <p className="text-sm text-steel">{detailsText}</p> : null}
                          {event.actors.length > 0 ? (
                            <p className="text-xs text-steel">
                              Operatorzy: {event.actors.map((actor) => actor.employee_name).join(", ")}
                            </p>
                          ) : null}
                        </div>
                        <div className="flex flex-wrap gap-2 sm:justify-end">
                          <span className="inline-flex rounded-full bg-mist px-3 py-1 text-xs font-semibold text-ink">
                            {stationLabels[event.station_id]}
                          </span>
                          <span className="inline-flex rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-700">
                            {formatDateTime(event.created_at)}
                          </span>
                        </div>
                      </div>
                      {event.details !== null ? (
                        <details className="mt-4 rounded-2xl border border-line/80 bg-mist/40 px-4 py-3 text-sm text-steel">
                          <summary className="cursor-pointer font-medium text-ink">Szczegóły</summary>
                          <pre className="mt-3 overflow-x-auto whitespace-pre-wrap text-xs leading-5 text-steel">{formatAuditDetailsJson(event.details)}</pre>
                        </details>
                      ) : null}
                    </article>
                  );
                })}
              </div>
            )}
          </section>
        </>
      ) : null}

      {isEditModalOpen && editForm ? (
        <div
          className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/40 px-4 py-8 backdrop-blur-sm"
          onClick={(e) => { if (e.target === e.currentTarget) setIsEditModalOpen(false); }}
        >
          <div className="w-full max-w-2xl rounded-[2rem] border border-white/70 bg-white shadow-panel">
            <div className="flex items-center justify-between border-b border-line/80 px-8 py-6">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-accent">Edycja</p>
                <h2 className="mt-1 text-2xl font-semibold text-ink">Dane zlecenia</h2>
              </div>
              <button
                type="button"
                onClick={() => setIsEditModalOpen(false)}
                className="rounded-full p-2 text-steel transition hover:bg-mist hover:text-ink"
                aria-label="Zamknij"
              >
                <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            <form onSubmit={(e) => void handleSaveEdit(e)} className="p-8">
              <div className="grid gap-5 sm:grid-cols-2">
                <div className="sm:col-span-2">
                  <label className="block text-sm font-medium text-steel">Firma / Klient *</label>
                  <input
                    type="text"
                    required
                    value={editForm.customer_name}
                    onChange={(e) => handleEditFormChange("customer_name", e.target.value)}
                    className="mt-1 w-full rounded-2xl border border-line bg-mist/40 px-4 py-2.5 text-base text-ink focus:border-accent focus:outline-none"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-steel">Nr zewnętrzny</label>
                  <input
                    type="text"
                    value={editForm.external_order_number}
                    onChange={(e) => handleEditFormChange("external_order_number", e.target.value)}
                    className="mt-1 w-full rounded-2xl border border-line bg-mist/40 px-4 py-2.5 text-base text-ink focus:border-accent focus:outline-none"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-steel">Nazwa zlecenia</label>
                  <input
                    type="text"
                    value={editForm.title}
                    onChange={(e) => handleEditFormChange("title", e.target.value)}
                    className="mt-1 w-full rounded-2xl border border-line bg-mist/40 px-4 py-2.5 text-base text-ink focus:border-accent focus:outline-none"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-steel">Kod RAL *</label>
                  <input
                    type="text"
                    required
                    value={editForm.ral_code}
                    onChange={(e) => handleEditFormChange("ral_code", e.target.value)}
                    className="mt-1 w-full rounded-2xl border border-line bg-mist/40 px-4 py-2.5 text-base text-ink focus:border-accent focus:outline-none"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-steel">Producent farby *</label>
                  <input
                    type="text"
                    required
                    value={editForm.paint_producer}
                    onChange={(e) => handleEditFormChange("paint_producer", e.target.value)}
                    className="mt-1 w-full rounded-2xl border border-line bg-mist/40 px-4 py-2.5 text-base text-ink focus:border-accent focus:outline-none"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-steel">Kod farby</label>
                  <input
                    type="text"
                    value={editForm.paint_code}
                    onChange={(e) => handleEditFormChange("paint_code", e.target.value)}
                    className="mt-1 w-full rounded-2xl border border-line bg-mist/40 px-4 py-2.5 text-base text-ink focus:border-accent focus:outline-none"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-steel">Data przyjęcia *</label>
                  <input
                    type="date"
                    required
                    value={editForm.received_date}
                    onChange={(e) => handleEditFormChange("received_date", e.target.value)}
                    className="mt-1 w-full rounded-2xl border border-line bg-mist/40 px-4 py-2.5 text-base text-ink focus:border-accent focus:outline-none"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-steel">Planowany odbiór</label>
                  <input
                    type="date"
                    value={editForm.planned_pickup_date}
                    onChange={(e) => handleEditFormChange("planned_pickup_date", e.target.value)}
                    className="mt-1 w-full rounded-2xl border border-line bg-mist/40 px-4 py-2.5 text-base text-ink focus:border-accent focus:outline-none"
                  />
                </div>

                <div className="sm:col-span-2">
                  <label className="block text-sm font-medium text-steel">Metraż (m²) *</label>
                  <NumberInput
                    step="0.01"
                    min="0.01"
                    required
                    value={editForm.total_area_m2}
                    onValueChange={(value) => handleEditFormChange("total_area_m2", value)}
                    className="mt-1 w-full rounded-2xl border border-line bg-mist/40 px-4 py-2.5 text-base text-ink focus:border-accent focus:outline-none"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-steel">Ilość profili</label>
                  <div className="mt-1 flex flex-col gap-2">
                    <label className="flex items-center gap-2 text-sm text-steel">
                      <input
                        type="checkbox"
                        checked={editForm.profiles_to_count}
                        onChange={(e) => handleEditFormChange("profiles_to_count", e.target.checked)}
                        className="rounded"
                      />
                      Do policzenia na produkcji
                    </label>
                    {!editForm.profiles_to_count && (
                      <NumberInput
                        min="0"
                        step="1"
                        value={editForm.profiles_quantity}
                        onValueChange={(value) => handleEditFormChange("profiles_quantity", value)}
                        placeholder="Ilość"
                        className="w-full rounded-2xl border border-line bg-mist/40 px-4 py-2.5 text-base text-ink focus:border-accent focus:outline-none"
                      />
                    )}
                  </div>
                </div>

                <div>
                  <label className="block text-sm font-medium text-steel">Ilość akcesoriów</label>
                  <div className="mt-1 flex flex-col gap-2">
                    <label className="flex items-center gap-2 text-sm text-steel">
                      <input
                        type="checkbox"
                        checked={editForm.accessories_to_count}
                        onChange={(e) => handleEditFormChange("accessories_to_count", e.target.checked)}
                        className="rounded"
                      />
                      Do policzenia na produkcji
                    </label>
                    {!editForm.accessories_to_count && (
                      <NumberInput
                        min="0"
                        step="1"
                        value={editForm.accessories_quantity}
                        onValueChange={(value) => handleEditFormChange("accessories_quantity", value)}
                        placeholder="Ilość"
                        className="w-full rounded-2xl border border-line bg-mist/40 px-4 py-2.5 text-base text-ink focus:border-accent focus:outline-none"
                      />
                    )}
                  </div>
                </div>

                <div className="sm:col-span-2">
                  <label className="block text-sm font-medium text-steel">Opis</label>
                  <textarea
                    rows={2}
                    value={editForm.description}
                    onChange={(e) => handleEditFormChange("description", e.target.value)}
                    className="mt-1 w-full rounded-2xl border border-line bg-mist/40 px-4 py-2.5 text-base text-ink focus:border-accent focus:outline-none"
                  />
                </div>

                <div className="sm:col-span-2">
                  <label className="block text-sm font-medium text-steel">Notatki</label>
                  <textarea
                    rows={2}
                    value={editForm.notes}
                    onChange={(e) => handleEditFormChange("notes", e.target.value)}
                    className="mt-1 w-full rounded-2xl border border-line bg-mist/40 px-4 py-2.5 text-base text-ink focus:border-accent focus:outline-none"
                  />
                </div>
              </div>

              {editErrorMessage ? (
                <div className="mt-5 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
                  {editErrorMessage}
                </div>
              ) : null}

              <div className="mt-6 flex justify-end gap-3">
                <button
                  type="button"
                  onClick={() => setIsEditModalOpen(false)}
                  disabled={isSavingEdit}
                  className="inline-flex items-center justify-center rounded-full border border-line bg-white px-5 py-2.5 text-sm font-medium text-steel transition hover:border-accent hover:text-accent disabled:opacity-60"
                >
                  Anuluj
                </button>
                <button
                  type="submit"
                  disabled={isSavingEdit}
                  className="inline-flex items-center justify-center rounded-full bg-accent px-6 py-2.5 text-sm font-medium text-white transition hover:bg-teal-700 disabled:opacity-60"
                >
                  {isSavingEdit ? "Zapisywanie…" : "Zapisz zmiany"}
                </button>
              </div>
            </form>
          </div>
        </div>
      ) : null}
    </main>
  );
}
