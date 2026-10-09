// Automatic-line paint consumption is entered as "cartons taken + what is left in the last one"
// (CHANGES #22: once per paint run). Pure so the arithmetic is testable apart from the form.

export type PaintCartonWeightKg = 20 | 25;

export interface PaintCartonDraft {
  cartonWeightKg: PaintCartonWeightKg | null;
  cartonCount: number;
  finalCartonRemainingKg: string;
}

export interface PaintCartonPreview {
  drawnPaintQuantityKg: number | null;
  finalCartonRemainingKg: number | null;
  consumedPaintQuantityKg: number | null;
  errorMessage: string | null;
}

export const EMPTY_PAINT_CARTON_DRAFT: PaintCartonDraft = {
  cartonWeightKg: null,
  cartonCount: 0,
  finalCartonRemainingKg: "",
};

function parseNonNegativeDecimal(value: string): number | null {
  if (!value.trim()) {
    return 0;
  }
  const parsed = Number(value);
  if (!Number.isFinite(parsed) || parsed < 0) {
    return null;
  }
  return parsed;
}

export function buildPaintCartonPreview(draft: PaintCartonDraft): PaintCartonPreview {
  if (draft.cartonWeightKg === null || draft.cartonCount < 1) {
    return { drawnPaintQuantityKg: null, finalCartonRemainingKg: null, consumedPaintQuantityKg: null, errorMessage: null };
  }

  const drawnPaintQuantityKg = draft.cartonWeightKg * draft.cartonCount;
  const finalCartonRemainingKg = parseNonNegativeDecimal(draft.finalCartonRemainingKg);
  if (finalCartonRemainingKg === null) {
    return {
      drawnPaintQuantityKg,
      finalCartonRemainingKg: null,
      consumedPaintQuantityKg: null,
      errorMessage: "Pozostałość w ostatnim kartonie musi być liczbą nieujemną.",
    };
  }
  if (finalCartonRemainingKg > draft.cartonWeightKg) {
    return {
      drawnPaintQuantityKg,
      finalCartonRemainingKg,
      consumedPaintQuantityKg: null,
      errorMessage: "Pozostałość w ostatnim kartonie nie może przekraczać wagi kartonu.",
    };
  }

  const consumedPaintQuantityKg = drawnPaintQuantityKg - finalCartonRemainingKg;
  if (consumedPaintQuantityKg <= 0) {
    return {
      drawnPaintQuantityKg,
      finalCartonRemainingKg,
      consumedPaintQuantityKg: null,
      errorMessage: "Zużycie farby musi być dodatnią liczbą.",
    };
  }
  return { drawnPaintQuantityKg, finalCartonRemainingKg, consumedPaintQuantityKg, errorMessage: null };
}
