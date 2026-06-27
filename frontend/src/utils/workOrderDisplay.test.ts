import { describe, expect, it } from "vitest";

import {
  buildCorrectionQuantityContext,
  buildCorrectionReference,
  buildMergedCorrectionDeltaText,
  formatDisplayOrderNumber,
  isPartiallyComplete,
} from "./workOrderDisplay";

// Pins the shared display helpers de-duplicated from the stage-completion pages (FRONTEND_TRIAGE C3/C4),
// so the single definition keeps the exact behaviour all five former copies had.

describe("formatDisplayOrderNumber", () => {
  it("prefixes a Decoral-incomplete root with N", () => {
    expect(
      formatDisplayOrderNumber({ order_number: "0042", is_decoral_incomplete: true, completed_quantity: 0, total_quantity: 10 }),
    ).toBe("N0042");
  });

  it("N takes precedence over a partial P", () => {
    expect(
      formatDisplayOrderNumber({ order_number: "0042", is_decoral_incomplete: true, completed_quantity: 5, total_quantity: 10 }),
    ).toBe("N0042");
  });

  it("prefixes a partially-complete order with P", () => {
    expect(
      formatDisplayOrderNumber({ order_number: "0042", completed_quantity: 5, total_quantity: 10 }),
    ).toBe("P0042");
  });

  it("does not double-prefix an order already starting with P", () => {
    expect(
      formatDisplayOrderNumber({ order_number: "P0042", completed_quantity: 5, total_quantity: 10 }),
    ).toBe("P0042");
  });

  it("leaves a not-started order unchanged", () => {
    expect(
      formatDisplayOrderNumber({ order_number: "0042", completed_quantity: 0, total_quantity: 10 }),
    ).toBe("0042");
  });

  it("leaves a fully-complete order unchanged", () => {
    expect(
      formatDisplayOrderNumber({ order_number: "0042", completed_quantity: 10, total_quantity: 10 }),
    ).toBe("0042");
  });
});

describe("isPartiallyComplete", () => {
  it("is true only strictly between 0 and total", () => {
    expect(isPartiallyComplete({ completed_quantity: 0, total_quantity: 10 })).toBe(false);
    expect(isPartiallyComplete({ completed_quantity: 5, total_quantity: 10 })).toBe(true);
    expect(isPartiallyComplete({ completed_quantity: 10, total_quantity: 10 })).toBe(false);
  });
});

const round = { is_correction: true, is_correction_round: true, order_number: "P0007", total_quantity: 3 };
const child = { is_correction: true, is_correction_round: false, order_number: "P0007", total_quantity: 3 };
const plain = { is_correction: false, is_correction_round: false, order_number: "0007", total_quantity: 10 };

describe("buildCorrectionReference", () => {
  it("labels a correction round by its own number", () => {
    expect(buildCorrectionReference(round, undefined)).toBe("Poprawka — runda P0007");
  });
  it("names the parent for a correction child when context is known", () => {
    expect(buildCorrectionReference(child, { parentOrderNumber: "0007", parentTotalQuantity: 10 })).toBe("Poprawka do 0007");
  });
  it("falls back when the parent context is missing", () => {
    expect(buildCorrectionReference(child, undefined)).toBe("Poprawka do zlecenia nadrzędnego");
  });
  it("is empty for a non-correction order", () => {
    expect(buildCorrectionReference(plain, undefined)).toBe("");
  });
});

describe("buildCorrectionQuantityContext", () => {
  it("shows the round quantity", () => {
    expect(buildCorrectionQuantityContext(round, undefined)).toBe("3 szt. poprawki");
  });
  it("shows quantity out of the parent total when known", () => {
    expect(buildCorrectionQuantityContext(child, { parentOrderNumber: "0007", parentTotalQuantity: 10 })).toBe("3 szt. poprawki z 10");
  });
  it("shows quantity alone without parent context", () => {
    expect(buildCorrectionQuantityContext(child, undefined)).toBe("3 szt. poprawki");
  });
});

describe("buildMergedCorrectionDeltaText", () => {
  it("shows corrected-out-of-parent when known", () => {
    expect(buildMergedCorrectionDeltaText(child, { parentOrderNumber: "0007", parentTotalQuantity: 10 })).toBe("Poprawiono 3 z 10 szt.");
  });
  it("shows corrected count alone otherwise", () => {
    expect(buildMergedCorrectionDeltaText(child, undefined)).toBe("Poprawiono 3 szt.");
  });
});
