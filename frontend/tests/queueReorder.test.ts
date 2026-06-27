import { describe, expect, it } from "vitest";

import {
  assignSequentialQueuePositions,
  buildQueueReorderPayload,
  buildQueueReorderRequest,
  getQueueRevisionFromPlannedOrders,
  moveWorkOrderWithinQueueSlots,
} from "../src/utils/queueReorder";

describe("queueReorder", () => {
  it("reorders mixed normal and correction orders within global queue slots", () => {
    const activeItems = [
      { id: 10, queue_position: 1 },
      { id: 20, queue_position: 3 },
    ];

    const reordered = moveWorkOrderWithinQueueSlots(activeItems, 20, 10);

    expect(reordered).toEqual([
      { id: 20, queue_position: 1 },
      { id: 10, queue_position: 3 },
    ]);
  });

  it("builds a full ordered payload that preserves completed queue slots", () => {
    const activeItems = assignSequentialQueuePositions([
      { id: 200, queue_position: 1 },
      { id: 100, queue_position: 3 },
    ]);

    expect(buildQueueReorderPayload(activeItems)).toEqual([
      { work_order_id: 200, queue_position: 1 },
      { work_order_id: 100, queue_position: 2 },
    ]);
  });

  it("builds a reorder request with queue revision", () => {
    const activeItems = assignSequentialQueuePositions([
      { id: 7, queue_position: 2 },
      { id: 9, queue_position: 4 },
    ]);

    expect(buildQueueReorderRequest(activeItems, "2026-05-27T08:30:00Z")).toEqual({
      queue_revision: "2026-05-27T08:30:00Z",
      items: [
        { work_order_id: 7, queue_position: 1 },
        { work_order_id: 9, queue_position: 2 },
      ],
    });
  });

  it("derives queue revision from the latest planned work order update", () => {
    expect(
      getQueueRevisionFromPlannedOrders([
        { updated_at: "2026-05-27T08:30:00Z" },
        { updated_at: "2026-05-27T08:35:00Z" },
        { updated_at: "2026-05-27T08:32:00Z" },
      ] as never[]),
    ).toBe("2026-05-27T08:35:00Z");
  });

  it("picks chronologically, not lexicographically, when the backend omits zero microseconds (B3)", () => {
    // The real backend (Pydantic v2 + datetime.now(UTC)) drops the fractional part when microseconds
    // are exactly zero. The whole-second stamp is EARLIER but sorts LATER as a raw string ('Z' > '.'),
    // so a string compare would wrongly return it. The latest here is the .500000 one.
    expect(
      getQueueRevisionFromPlannedOrders([
        { updated_at: "2026-05-27T08:35:00Z" },
        { updated_at: "2026-05-27T08:35:00.500000Z" },
      ] as never[]),
    ).toBe("2026-05-27T08:35:00.500000Z");

    // ...and the order in the array must not matter.
    expect(
      getQueueRevisionFromPlannedOrders([
        { updated_at: "2026-05-27T08:35:00.500000Z" },
        { updated_at: "2026-05-27T08:35:00Z" },
      ] as never[]),
    ).toBe("2026-05-27T08:35:00.500000Z");

    // A fractional stamp in a strictly later second still wins (microseconds don't outrank seconds).
    expect(
      getQueueRevisionFromPlannedOrders([
        { updated_at: "2026-05-27T08:35:00.900000Z" },
        { updated_at: "2026-05-27T08:36:00Z" },
      ] as never[]),
    ).toBe("2026-05-27T08:36:00Z");
  });
});
