import { describe, expect, it } from "vitest";

import { API_ORIGIN, isApiRequest } from "./workOrdersApi";

// Pins the auth-token scoping (FRONTEND_TRIAGE B1): the global fetch interceptor must attach the
// Bearer token (and act on 401s) only for requests aimed at our own API origin. With no
// VITE_API_BASE_URL set in the test env, the API origin is the app's own origin.

describe("isApiRequest", () => {
  it("treats the app origin as the API origin when no API base URL is configured", () => {
    expect(API_ORIGIN).toBe(window.location.origin);
  });

  it("accepts relative paths (same-origin API calls)", () => {
    expect(isApiRequest("/work-orders")).toBe(true);
    expect(isApiRequest("/auth/login")).toBe(true);
  });

  it("accepts absolute URLs on our own origin", () => {
    expect(isApiRequest(`${window.location.origin}/manager/work-orders`)).toBe(true);
    expect(isApiRequest(new URL("/foils", window.location.origin))).toBe(true);
  });

  it("rejects third-party origins so the token never leaks off-site", () => {
    expect(isApiRequest("https://evil.example.com/steal")).toBe(false);
    expect(isApiRequest("http://attacker.test/collect?x=1")).toBe(false);
    expect(isApiRequest(new Request("https://other.example.org/x"))).toBe(false);
  });

  it("resolves non-absolute strings against our own origin (safe same-origin default)", () => {
    // Anything that isn't a parseable absolute URL is treated as a relative same-origin path,
    // so it counts as an API request — the safe direction (token only ever stays on our origin).
    expect(isApiRequest("work-orders?weird value")).toBe(true);
  });
});
