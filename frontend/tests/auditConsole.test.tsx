import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AuditEventsPage } from "../src/pages/AuditEventsPage";

vi.mock("../src/api/auditApi", () => ({
  fetchAuditEvents: vi.fn(),
  getAuditEventsExportUrl: vi.fn(),
}));

const auditApi = await import("../src/api/auditApi");
const fetchAuditEventsMock = vi.mocked(auditApi.fetchAuditEvents);
const getAuditEventsExportUrlMock = vi.mocked(auditApi.getAuditEventsExportUrl);

describe("audit console", () => {
  beforeEach(() => {
    fetchAuditEventsMock.mockReset();
    getAuditEventsExportUrlMock.mockReset();
    getAuditEventsExportUrlMock.mockReturnValue("/audit/events/export.csv?limit=100");
    fetchAuditEventsMock.mockResolvedValue({
      limit: 100,
      offset: 0,
      items: [
        {
          id: 1,
          event_type: "work_order.created",
          station_id: "OFFICE",
          work_order_id: 12,
          target_type: "work_order",
          target_id: 12,
          request_id: "trace-audit-1",
          summary: "Created work order WO-AUDIT.",
          details: { order_number: "WO-AUDIT" },
          created_at: "2026-05-29T10:00:00Z",
        },
      ],
    });
  });

  it("renders audit events and export link", async () => {
    render(<AuditEventsPage />);

    await screen.findByText("Created work order WO-AUDIT.");
    expect(screen.getByText("work_order.created")).toBeTruthy();
    expect(screen.getAllByText("Biuro").length).toBeGreaterThan(0);
    expect(screen.getByText("trace-audit-1")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Eksport CSV" }).getAttribute("href")).toBe("/audit/events/export.csv?limit=100");
  });

  it("submits filters to audit search", async () => {
    render(<AuditEventsPage />);

    await screen.findByText("Created work order WO-AUDIT.");
    fireEvent.change(screen.getByLabelText("Request ID"), { target: { value: "trace-audit-1" } });
    fireEvent.change(screen.getByLabelText("Stacja"), { target: { value: "OFFICE" } });
    fireEvent.change(screen.getByLabelText("Typ zdarzenia"), { target: { value: "work_order.created" } });
    fireEvent.click(screen.getByRole("button", { name: "Szukaj" }));

    await waitFor(() => expect(fetchAuditEventsMock).toHaveBeenCalledTimes(2));
    expect(fetchAuditEventsMock).toHaveBeenLastCalledWith({
      workOrderId: "",
      eventType: "work_order.created",
      stationId: "OFFICE",
      requestId: "trace-audit-1",
      targetType: "",
      targetId: "",
      createdFrom: "",
      createdTo: "",
      limit: 100,
    });
  });
});
