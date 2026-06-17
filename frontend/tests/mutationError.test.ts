import { describe, expect, it } from "vitest";

import { ApiError } from "../src/api/apiError";
import { getMutationErrorMessage } from "../src/utils/mutationError";

const GENERIC = "Nie udało się. Widok odświeżony.";

describe("getMutationErrorMessage", () => {
  it("surfaces the backend reason for a 403 (e.g. wrong station)", () => {
    const error = new ApiError(403, "Station PACKING is not allowed to perform HANGING stage actions.");
    expect(getMutationErrorMessage(error, GENERIC)).toBe(
      "Station PACKING is not allowed to perform HANGING stage actions.",
    );
  });

  it("surfaces 409 conflicts and 422 validation messages", () => {
    expect(getMutationErrorMessage(new ApiError(409, "Konflikt etapu"), GENERIC)).toBe("Konflikt etapu");
    expect(getMutationErrorMessage(new ApiError(422, "Nieprawidłowa ilość"), GENERIC)).toBe("Nieprawidłowa ilość");
  });

  it("keeps the generic message for server errors and network failures", () => {
    expect(getMutationErrorMessage(new ApiError(500, "Internal Server Error"), GENERIC)).toBe(GENERIC);
    expect(getMutationErrorMessage(new Error("network down"), GENERIC)).toBe(GENERIC);
  });
});
