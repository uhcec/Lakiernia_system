import { afterEach, describe, expect, it, vi } from "vitest";

import { API_ORIGIN, fetchAllWorkOrders, isApiRequest } from "./workOrdersApi";

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

// CHANGES #15: the office list used to fetch a single page (backend default limit=50) and compute
// its tiles/tabs from the truncated result. fetchAllWorkOrders must page through until `total`.
describe("fetchAllWorkOrders", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  function jsonResponse(body: unknown): Response {
    return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
  }

  it("pages through the whole list and returns every order with the true total", async () => {
    const firstPage = Array.from({ length: 100 }, (_, index) => ({ id: index + 1 }));
    const secondPage = Array.from({ length: 30 }, (_, index) => ({ id: 100 + index + 1 }));
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ items: firstPage, total: 130, limit: 100, offset: 0 }))
      .mockResolvedValueOnce(jsonResponse({ items: secondPage, total: 130, limit: 100, offset: 100 }));
    vi.stubGlobal("fetch", fetchMock);

    const result = await fetchAllWorkOrders();

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(String(fetchMock.mock.calls[0][0])).toContain("limit=100");
    expect(String(fetchMock.mock.calls[0][0])).toContain("offset=0");
    expect(String(fetchMock.mock.calls[1][0])).toContain("offset=100");
    expect(result.items).toHaveLength(130);
    expect(result.total).toBe(130);
  });

  it("stops after one request when the first page covers the total", async () => {
    const items = Array.from({ length: 40 }, (_, index) => ({ id: index + 1 }));
    const fetchMock = vi.fn().mockResolvedValueOnce(jsonResponse({ items, total: 40, limit: 100, offset: 0 }));
    vi.stubGlobal("fetch", fetchMock);

    const result = await fetchAllWorkOrders();

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(result.items).toHaveLength(40);
    expect(result.total).toBe(40);
  });

  it("stops on an empty page even if the reported total is never reached (backstop)", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ items: [{ id: 1 }], total: 999, limit: 100, offset: 0 }))
      .mockResolvedValueOnce(jsonResponse({ items: [], total: 999, limit: 100, offset: 100 }));
    vi.stubGlobal("fetch", fetchMock);

    const result = await fetchAllWorkOrders();

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(result.items).toHaveLength(1);
  });
});
