from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.foils.schemas import FoilSummaryRead
from app.process.enums import ProcessStage, QuantityBatchType, StageStatus
from app.work_orders.schemas import CoatingTypeView, ProductionTypeView, QueueNamespaceView, WorkOrderKindView


class StageStatusView(BaseModel):
    value: StageStatus
    label: str


class ProcessStageStatusRead(BaseModel):
    stage: ProcessStage
    status: StageStatusView


class WorkOrderAttachmentSummaryRead(BaseModel):
    """Minimal attachment descriptor surfaced on station cards (NA36 technical drawings)."""

    id: int
    original_filename: str
    content_type: str


class ProcessStageWorkOrderRead(BaseModel):
    id: int
    batch_id: int | None = None
    is_correction: bool
    is_correction_round: bool = False
    is_historical_correction: bool = False
    is_decoral_incomplete: bool = False
    work_order_kind: WorkOrderKindView
    is_ocynk: bool = False
    order_number: str
    title: str
    completed_quantity: int = 0
    ral_code: str
    paint_code: str | None = None
    paint_producer: str
    current_paint_stock_quantity_kg: float | None = None
    paint_stock_snapshot_quantity_kg: float | None = None
    consumed_paint_quantity_kg: float
    total_area_m2: float | None = None
    total_quantity: int
    current_active_quantity: int
    # Operator-facing count = actual received (surface-prep counted) once counted, else total_quantity
    # (for tracked batches: the batch quantity). `planned_quantity` stays the original expected (audit).
    operational_quantity: int
    batch_quantity: int | None = None
    planned_quantity: int
    counted_quantity: int | None = None
    quantity_difference: int | None = None
    customer_name: str | None
    profiles_quantity: int | None = None
    profiles_to_count: bool = False
    accessories_quantity: int | None = None
    accessories_to_count: bool = False
    queue_position: int | None
    # Shared-stage derivation (N49-10). At the two physically shared stages — SURFACE_PREPARATION and
    # PACKING — both lines are merged, so the per-line `queue_position` is NOT a valid global rank (two
    # different orders would otherwise collide on the same "Poz. N"). At those stages the backend derives
    # a single order and stamps a line label here; the frontend renders that label (not `Poz.`).
    # `is_next_at_shared_stage` marks the head of the surface-prep feeder ("NASTĘPNE"). Both stay unset /
    # False at the per-line painting stages, where `queue_position` remains the correct rank.
    shared_stage_line_label: str | None = None
    is_next_at_shared_stage: bool = False
    queue_namespace: QueueNamespaceView
    production_type: ProductionTypeView | None
    coating_type: CoatingTypeView
    decoral_foil: FoilSummaryRead | None = None
    # Technical drawings (NA36): office-attached PDFs/images the station operator can open while working.
    technical_drawings: list[WorkOrderAttachmentSummaryRead] = Field(default_factory=list)
    batch_type: QuantityBatchType | None = None
    batch_is_partial: bool = False
    is_being_packed: bool = False
    holds_packing_slot: bool = False
    packing_slots_total: int = 1
    # Packing completion gate (automatic orders pack in parallel with the line, but cannot finish
    # until HANGING is DONE and paint consumption is recorded). `packing_blocked_reason` is the
    # operator-facing Polish message shown when `can_complete_packing` is False.
    can_complete_packing: bool = True
    packing_blocked_reason: str | None = None
    stage_status: ProcessStageStatusRead


class StageTransitionRequest(BaseModel):
    counted_quantity: int | None = None

    model_config = ConfigDict(extra="forbid")


class PackingCompleteRequest(BaseModel):
    counted_quantity: int = Field(gt=0)
    ok_quantity: int = Field(ge=0)
    correction_quantity: int = Field(ge=0)
    correction_profiles_quantity: int | None = Field(default=None, ge=0)
    correction_accessories_quantity: int | None = Field(default=None, ge=0)
    correction_reason_category: str | None = Field(default=None, min_length=1, max_length=64)
    correction_reason_note: str | None = Field(default=None, max_length=500)
    # NA34: "fixed on the spot" (od razu poprawiona) — the correction is logged as a statistic only and
    # the order completes as-is (no replan, no child). Otherwise the correction is re-planned.
    stat_only_correction: bool = False

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    @model_validator(mode="after")
    def validate_correction_reason(self) -> "PackingCompleteRequest":
        has_reason = self.correction_reason_category is not None
        has_note = self.correction_reason_note is not None
        if self.stat_only_correction and self.correction_quantity == 0:
            raise ValueError("A stat-only correction requires a correction quantity greater than zero.")
        if self.correction_quantity > 0 and not has_reason:
            raise ValueError("Correction reason is required when correction quantity is greater than zero.")
        if self.correction_quantity == 0 and (has_reason or has_note):
            raise ValueError("Correction reason can only be set when correction quantity is greater than zero.")
        has_profile_split = self.correction_profiles_quantity is not None
        has_accessory_split = self.correction_accessories_quantity is not None
        if self.correction_quantity == 0 and (has_profile_split or has_accessory_split):
            raise ValueError("Correction category quantities can only be set when correction quantity is greater than zero.")
        if self.correction_quantity > 0:
            if not has_profile_split or not has_accessory_split:
                raise ValueError("Correction profile and accessory quantities are required when correction quantity is greater than zero.")
            if self.correction_profiles_quantity + self.correction_accessories_quantity != self.correction_quantity:
                raise ValueError("Correction profile and accessory quantities must add up to correction quantity.")
        return self


class DecoralProductionCompleteRequest(BaseModel):
    ok_quantity: int = Field(ge=0)
    correction_quantity: int = Field(ge=0)
    correction_profiles_quantity: int | None = Field(default=None, ge=0)
    correction_accessories_quantity: int | None = Field(default=None, ge=0)
    correction_reason_category: str | None = Field(default=None, min_length=1, max_length=64)
    correction_reason_note: str | None = Field(default=None, max_length=500)

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    @model_validator(mode="after")
    def validate_correction_reason(self) -> "DecoralProductionCompleteRequest":
        if self.ok_quantity + self.correction_quantity <= 0:
            raise ValueError("Total quantity must be greater than zero.")
        has_reason = self.correction_reason_category is not None
        has_note = self.correction_reason_note is not None
        if self.correction_quantity > 0 and not has_reason:
            raise ValueError("Correction reason is required when correction quantity is greater than zero.")
        if self.correction_quantity == 0 and (has_reason or has_note):
            raise ValueError("Correction reason can only be set when correction quantity is greater than zero.")
        has_profile_split = self.correction_profiles_quantity is not None
        has_accessory_split = self.correction_accessories_quantity is not None
        if self.correction_quantity == 0 and (has_profile_split or has_accessory_split):
            raise ValueError("Correction category quantities can only be set when correction quantity is greater than zero.")
        if self.correction_quantity > 0:
            if not has_profile_split or not has_accessory_split:
                raise ValueError("Correction profile and accessory quantities are required when correction quantity is greater than zero.")
            if self.correction_profiles_quantity + self.correction_accessories_quantity != self.correction_quantity:
                raise ValueError("Correction profile and accessory quantities must add up to correction quantity.")
        return self


class AutomaticPaintConsumptionRequest(BaseModel):
    consumed_paint_quantity_kg: float = Field(gt=0)

    model_config = ConfigDict(extra="forbid")
