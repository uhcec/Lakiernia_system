import { afterEach, describe, expect, it, vi } from "vitest";

import { createWorkOrder, deleteWorkOrderAttachment, uploadWorkOrderAttachment } from "../src/api/workOrdersApi";
import {
  buildWorkOrderDetailHref,
  getStationIdForLocation,
  getStationIdForPath,
  getStationPanelPath,
} from "../src/api/stationContext";
import type { CreateWorkOrderRequest } from "../src/types/workOrders";

describe("station context", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it.each([
    ["/zlecenia", "OFFICE"],
    ["/zlecenia/nowe", "OFFICE"],
    ["/farby", "OFFICE"],
    ["/kierownik", "MANAGER"],
    ["/przygotowanie", "SURFACE_PREPARATION"],
    ["/zawieszanie", "HANGING"],
    ["/produkcja-automat", "AUTOMATIC_PRODUCTION"],
    ["/produkcja-reczna", "MANUAL_PRODUCTION"],
    ["/produkcja-decoral", "DECORAL_PRODUCTION"],
    ["/pakowanie", "PACKING"],
    ["/nieznany-panel", "UNKNOWN"],
  ])("maps %s to %s", (pathname, stationId) => {
    expect(getStationIdForPath(pathname)).toBe(stationId);
  });

  it("preserves explicit station identity on work order detail routes", () => {
    expect(getStationIdForLocation("/zlecenia/12", "?station_context=PACKING")).toBe("PACKING");
    expect(getStationIdForLocation("/zlecenia/12", "?station_context=MANAGER")).toBe("MANAGER");
    expect(getStationIdForLocation("/zlecenia/12", "?station_context=NOT_A_STATION")).toBe("OFFICE");
    expect(buildWorkOrderDetailHref(12, "PACKING")).toBe("/zlecenia/12?station_context=PACKING");
    expect(buildWorkOrderDetailHref(12, "OFFICE")).toBe("/zlecenia/12");
    expect(getStationPanelPath("PACKING")).toBe("/pakowanie");
  });

  it("sends current station identity when creating a work order", async () => {
    window.history.pushState({}, "", "/zlecenia/nowe");
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ id: 1 }), {
        status: 201,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await createWorkOrder(buildCreateWorkOrderRequest());

    const requestInit = fetchMock.mock.calls[0][1] as RequestInit;
    expect(requestInit.headers).toMatchObject({
      "X-Station-Id": "OFFICE",
      "Content-Type": "application/json",
    });
  });

  it("sends current station identity when uploading an attachment", async () => {
    window.history.pushState({}, "", "/zlecenia/12");
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ id: 7 }), {
        status: 201,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await uploadWorkOrderAttachment(12, {
      file: new File(["%PDF-1.4"], "audyt.pdf", { type: "application/pdf" }),
    });

    const requestInit = fetchMock.mock.calls[0][1] as RequestInit;
    expect(requestInit.headers).toMatchObject({
      "X-Station-Id": "OFFICE",
    });
  });

  it("sends preserved station identity from station-origin detail routes", async () => {
    window.history.pushState({}, "", "/zlecenia/12?station_context=PACKING");
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ id: 7 }), {
        status: 201,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await uploadWorkOrderAttachment(12, {
      file: new File(["%PDF-1.4"], "audyt.pdf", { type: "application/pdf" }),
    });

    const requestInit = fetchMock.mock.calls[0][1] as RequestInit;
    expect(requestInit.headers).toMatchObject({
      "X-Station-Id": "PACKING",
    });
  });

  it("sends current station identity when deleting an attachment", async () => {
    window.history.pushState({}, "", "/zlecenia/12");
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);

    await deleteWorkOrderAttachment(12, 7);

    const requestInit = fetchMock.mock.calls[0][1] as RequestInit;
    expect(requestInit.headers).toMatchObject({
      "X-Station-Id": "OFFICE",
    });
  });
});

function buildCreateWorkOrderRequest(): CreateWorkOrderRequest {
  return {
    title: "Test",
    coating_type: "RAL",
    total_quantity: 10,
    customer_name: "ACME",
    ral_code: "RAL 7016",
    paint_code: "P-7016",
    paint_producer: "AkzoNobel",
    received_date: "2026-05-29",
    total_area_m2: 24,
    profiles_to_count: true,
    accessories_to_count: true,
  };
}
