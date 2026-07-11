import { describe, expect, it } from "vitest";

import { ApiError } from "../src/api/apiError";
import { getLoadErrorMessage, NETWORK_ERROR_MESSAGE_PL } from "../src/utils/loadError";
import { readStoredAuthUser, USER_KEY } from "../src/context/AuthContext";

const GENERIC = "Nie udało się pobrać zleceń";

describe("getLoadErrorMessage (CHANGES #16c)", () => {
  it("surfaces an ApiError's controlled Polish message verbatim", () => {
    expect(getLoadErrorMessage(new ApiError(409, "Pozycja w kolejce jest już zajęta."), GENERIC)).toBe(
      "Pozycja w kolejce jest już zajęta.",
    );
    expect(getLoadErrorMessage(new ApiError(500, "Nie udało się pobrać zleceń"), GENERIC)).toBe(
      "Nie udało się pobrać zleceń",
    );
  });

  it("translates a browser-level fetch rejection to the Polish network message", () => {
    // A backend-unreachable fetch rejects with the browser's raw English TypeError.
    expect(getLoadErrorMessage(new TypeError("Failed to fetch"), GENERIC)).toBe(NETWORK_ERROR_MESSAGE_PL);
    expect(getLoadErrorMessage(new TypeError("NetworkError when attempting to fetch resource."), GENERIC)).toBe(
      NETWORK_ERROR_MESSAGE_PL,
    );
  });

  it("keeps the caller's generic Polish message for anything else", () => {
    expect(getLoadErrorMessage(new Error("some internal detail"), GENERIC)).toBe(GENERIC);
    expect(getLoadErrorMessage("not an error", GENERIC)).toBe(GENERIC);
    expect(getLoadErrorMessage(new ApiError(500, "   "), GENERIC)).toBe(GENERIC);
  });
});

describe("readStoredAuthUser (CHANGES #16a)", () => {
  it("returns the parsed user for a valid stored value", () => {
    localStorage.setItem(USER_KEY, JSON.stringify({ login: "biuro", station_id: "OFFICE", is_admin: false }));
    expect(readStoredAuthUser()).toEqual({ login: "biuro", station_id: "OFFICE", is_admin: false });
    localStorage.removeItem(USER_KEY);
  });

  it("survives a corrupt stored value instead of white-screening the app, and clears it", () => {
    localStorage.setItem(USER_KEY, "{corrupt json!!");
    expect(readStoredAuthUser()).toBeNull();
    expect(localStorage.getItem(USER_KEY)).toBeNull();
  });

  it("returns null when nothing is stored", () => {
    localStorage.removeItem(USER_KEY);
    expect(readStoredAuthUser()).toBeNull();
  });
});
