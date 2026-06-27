import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { OfficeWorkOrdersTable } from "./OfficeWorkOrdersTable";
import type { WorkOrder } from "../types/workOrders";

// FRONTEND_TRIAGE B6: "overdue" in the office list must come from the backend `is_overdue`
// (pickup past AND not yet READY), never a client clock compare — so a completed order picked up
// late is not falsely flagged "Po terminie".

function buildOrder(overrides: Partial<WorkOrder>): WorkOrder {
  return {
    id: 1,
    order_number: "0001",
    customer_name: "ACME",
    ral_code: "RAL 9010",
    total_area_m2: 10,
    completed_quantity: 0,
    total_quantity: 10,
    current_active_quantity: 0,
    is_released_to_client: false,
    is_decoral_incomplete: false,
    is_overdue: false,
    planned_pickup_date: "2020-01-01", // safely in the past
    process_status: { value: "TO_BE_PLANNED", label: "Do zaplanowania" },
    production_type: null,
    ...overrides,
  } as unknown as WorkOrder;
}

function renderTable(order: WorkOrder) {
  render(
    <MemoryRouter>
      <OfficeWorkOrdersTable workOrders={[order]} />
    </MemoryRouter>,
  );
}

describe("OfficeWorkOrdersTable overdue framing", () => {
  it("flags 'Po terminie' when the backend marks the order overdue", () => {
    renderTable(buildOrder({ is_overdue: true }));
    expect(screen.getByText("Po terminie")).toBeTruthy();
  });

  it("does NOT flag a completed (READY) order picked up after its date (is_overdue=false)", () => {
    renderTable(
      buildOrder({
        is_overdue: false,
        completed_quantity: 10,
        process_status: { value: "READY", label: "Gotowe" },
        is_released_to_client: true,
      }),
    );
    expect(screen.queryByText("Po terminie")).toBeNull();
  });
});
