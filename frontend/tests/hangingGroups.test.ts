import { describe, expect, it } from "vitest";

import { getHangingStartBlock, groupHangingQueue } from "../src/utils/hangingGroups";
import type { StageWorkOrder } from "../src/types/process";

function buildStageWorkOrder(overrides: Partial<StageWorkOrder> = {}): StageWorkOrder {
  return {
    id: 1,
    batch_id: null,
    is_correction: false,
    is_correction_round: false,
    is_historical_correction: false,
    work_order_kind: { value: "STANDARD", label: "Standardowe" },
    is_ocynk: false,
    order_number: "0001",
    title: "0001",
    ral_code: "RAL 7016",
    paint_code: "INV-7016-M",
    paint_producer: "Inver",
    consumed_paint_quantity_kg: 0,
    total_area_m2: 150,
    total_quantity: 10,
    completed_quantity: 0,
    current_active_quantity: 10,
    operational_quantity: 10,
    batch_quantity: null,
    planned_quantity: 10,
    counted_quantity: null,
    quantity_difference: null,
    customer_name: "Profil-Tech",
    profiles_quantity: null,
    profiles_to_count: false,
    accessories_quantity: null,
    accessories_to_count: false,
    queue_position: 1,
    shared_stage_line_label: null,
    is_next_at_shared_stage: false,
    queue_namespace: { value: "MAIN", label: "Główna" },
    production_type: { value: "AUTOMATIC", label: "Automatyczna" },
    coating_type: { value: "RAL", label: "RAL" },
    technical_drawings: [],
    batch_type: null,
    batch_is_partial: false,
    is_being_packed: false,
    holds_packing_slot: false,
    packing_slots_total: 2,
    can_complete_packing: false,
    packing_blocked_reason: null,
    stage_status: { stage: "HANGING", status: { value: "NOT_STARTED", label: "Nie rozpoczęto" } },
    ...overrides,
  };
}

describe("groupHangingQueue (CHANGES #27)", () => {
  it("groups consecutive orders with the same paint, keeping queue order", () => {
    const groups = groupHangingQueue([
      buildStageWorkOrder({ id: 1, order_number: "0001" }),
      buildStageWorkOrder({ id: 4, order_number: "0004" }),
      buildStageWorkOrder({ id: 2, order_number: "0002" }),
    ]);

    expect(groups).toHaveLength(1);
    expect(groups[0]).toMatchObject({ ralCode: "RAL 7016", paintProducer: "Inver", paintCode: "INV-7016-M" });
    expect(groups[0].workOrders.map((workOrder) => workOrder.order_number)).toEqual(["0001", "0004", "0002"]);
  });

  it("splits the same paint into two groups when another paint stands between them (owner choice a)", () => {
    const groups = groupHangingQueue([
      buildStageWorkOrder({ id: 1 }),
      buildStageWorkOrder({ id: 2, ral_code: "RAL 9016", paint_code: "INV-9016" }),
      buildStageWorkOrder({ id: 3 }),
    ]);

    expect(groups.map((group) => group.ralCode)).toEqual(["RAL 7016", "RAL 9016", "RAL 7016"]);
  });

  it("treats a different producer or paint code as a different paint, like a paint run", () => {
    const groups = groupHangingQueue([
      buildStageWorkOrder({ id: 1 }),
      buildStageWorkOrder({ id: 2, paint_producer: "Tiger" }),
      buildStageWorkOrder({ id: 3, paint_producer: "Tiger", paint_code: "TIG-7016-S" }),
    ]);

    expect(groups).toHaveLength(3);
  });

  it("never groups orders without a paint code, since they never join a paint run", () => {
    const groups = groupHangingQueue([
      buildStageWorkOrder({ id: 1, paint_code: null }),
      buildStageWorkOrder({ id: 2, paint_code: null }),
    ]);

    expect(groups).toHaveLength(2);
  });

  it("gives every group a distinct key even for repeated paints", () => {
    const groups = groupHangingQueue([
      buildStageWorkOrder({ id: 1 }),
      buildStageWorkOrder({ id: 2, paint_code: "OTHER" }),
      buildStageWorkOrder({ id: 1, batch_id: 7 }),
    ]);

    expect(new Set(groups.map((group) => group.key)).size).toBe(3);
  });
});

describe("getHangingStartBlock (CHANGES #29)", () => {
  const hanging = buildStageWorkOrder({ id: 10, stage_status: { stage: "HANGING", status: { value: "IN_PROGRESS", label: "W trakcie" } } });

  it("lets an order start when nothing hangs", () => {
    expect(getHangingStartBlock(buildStageWorkOrder({ id: 1 }), [], 1)).toBeNull();
  });

  it("keeps the old wording when the limit is one", () => {
    expect(getHangingStartBlock(buildStageWorkOrder({ id: 1 }), [hanging], 1)).toBe("Zawieszanie zajęte");
  });

  it("lets a same-paint order join while there is room", () => {
    expect(getHangingStartBlock(buildStageWorkOrder({ id: 1 }), [hanging], 2)).toBeNull();
  });

  it("says the station is full once the limit is reached", () => {
    const second = buildStageWorkOrder({ id: 11 });
    expect(getHangingStartBlock(buildStageWorkOrder({ id: 1 }), [hanging, second], 2)).toBe("Zawieszanie pełne (2/2)");
  });

  it("refuses a different paint (RAL, producer or code)", () => {
    expect(getHangingStartBlock(buildStageWorkOrder({ id: 1, paint_code: "OTHER" }), [hanging], 3)).toBe(
      "Na zawieszaniu inna farba",
    );
    expect(getHangingStartBlock(buildStageWorkOrder({ id: 1, paint_producer: "Tiger" }), [hanging], 3)).toBe(
      "Na zawieszaniu inna farba",
    );
  });
});
