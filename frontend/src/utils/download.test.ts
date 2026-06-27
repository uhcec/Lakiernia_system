import { afterEach, describe, expect, it, vi } from "vitest";

import { downloadAuthedFile } from "./download";
import { ApiError } from "../api/apiError";

// Pins the shared authed-download helper (FRONTEND_TRIAGE B7): it must fetch the URL (so the global
// interceptor can attach the Bearer token — a plain <a href> can't), then save the returned blob.

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("downloadAuthedFile", () => {
  it("fetches the URL and triggers a blob download", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      blob: async () => new Blob(["a,b,c"], { type: "text/csv" }),
    });
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("URL", { createObjectURL: vi.fn(() => "blob:x"), revokeObjectURL: vi.fn() });
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});

    await downloadAuthedFile("/manager/corrections/reason-report/export.csv", "report.csv");

    expect(fetchMock).toHaveBeenCalledWith("/manager/corrections/reason-report/export.csv");
    expect(clickSpy).toHaveBeenCalledTimes(1);
  });

  it("throws an ApiError carrying the status when the response is not ok", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: false, status: 401, json: async () => ({ detail: "Nie jesteś zalogowany" }) }),
    );

    await expect(downloadAuthedFile("/audit/events/export.csv", "audit.csv")).rejects.toMatchObject({
      name: "ApiError",
      status: 401,
    } satisfies Partial<ApiError>);
  });
});
