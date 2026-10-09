import { describe, expect, it } from "vitest";

import { buildPaintCartonPreview, EMPTY_PAINT_CARTON_DRAFT } from "./paintCartons";

// Pins the carton arithmetic of the paint-run consumption form (CHANGES #22).

describe("buildPaintCartonPreview", () => {
  it("is empty until a carton weight and at least one carton are chosen", () => {
    expect(buildPaintCartonPreview(EMPTY_PAINT_CARTON_DRAFT).consumedPaintQuantityKg).toBeNull();
    expect(buildPaintCartonPreview({ ...EMPTY_PAINT_CARTON_DRAFT, cartonWeightKg: 25 }).errorMessage).toBeNull();
  });

  it("consumption = cartons × weight − what is left in the last carton", () => {
    const preview = buildPaintCartonPreview({ cartonWeightKg: 25, cartonCount: 3, finalCartonRemainingKg: "7.5" });
    expect(preview.drawnPaintQuantityKg).toBe(75);
    expect(preview.consumedPaintQuantityKg).toBe(67.5);
    expect(preview.errorMessage).toBeNull();
  });

  it("an empty remainder means the last carton was used up", () => {
    expect(buildPaintCartonPreview({ cartonWeightKg: 20, cartonCount: 2, finalCartonRemainingKg: "" }).consumedPaintQuantityKg).toBe(40);
  });

  it("rejects a remainder heavier than a carton", () => {
    const preview = buildPaintCartonPreview({ cartonWeightKg: 20, cartonCount: 1, finalCartonRemainingKg: "21" });
    expect(preview.consumedPaintQuantityKg).toBeNull();
    expect(preview.errorMessage).toBe("Pozostałość w ostatnim kartonie nie może przekraczać wagi kartonu.");
  });

  it("rejects a remainder equal to the whole carton (nothing used)", () => {
    const preview = buildPaintCartonPreview({ cartonWeightKg: 20, cartonCount: 1, finalCartonRemainingKg: "20" });
    expect(preview.errorMessage).toBe("Zużycie farby musi być dodatnią liczbą.");
  });
});
