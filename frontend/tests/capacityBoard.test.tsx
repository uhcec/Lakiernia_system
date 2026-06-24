import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

// The board fetches the multi-day plan on mount; mock it with a populated plan covering the flag paths
// (below-floor day, an at-risk-deadline order, a paint-blocked order).
vi.mock("../src/api/managerApi", () => ({
  fetchMultiDayPlan: vi.fn(() =>
    Promise.resolve({
      production_type: "AUTOMATIC",
      shift_length: "LONG",
      shift_advised: true,
      horizon_working_days: 10,
      changeover_minutes: 20,
      changeover_is_measured: false,
      infeasible_order_ids: [2],
      days: [
        {
          day_index: 0,
          scheduled_date: "2026-06-25",
          shift_length: "LONG",
          floor_m2: 800,
          gross_ceiling_m2: 1120,
          net_ceiling_m2: 1000,
          changeover_count: 1,
          changeover_minutes: 20,
          placed_order_count: 2,
          placed_m2: 300,
          below_floor: true,
          over_ceiling: false,
          placements: [
            {
              work_order_id: 1,
              order_number: "WO-1",
              customer_name: "Alpha",
              ral_code: "RAL 9010",
              total_area_m2: 150,
              day_index: 0,
              sequence_position: 0,
              scheduled_date: "2026-06-25",
              planned_pickup_date: "2026-06-30",
              meets_deadline: true,
              days_late: 0,
              suggested_production_type: "AUTOMATIC",
              suggested_line_is_colour_orphan: false,
              suggested_line_is_small: false,
              paint_status: "BLOCKED",
              paint_remaining_kg: -5,
            },
            {
              work_order_id: 2,
              order_number: "WO-2",
              customer_name: "Beta",
              ral_code: "RAL 7016",
              total_area_m2: 150,
              day_index: 0,
              sequence_position: 1,
              scheduled_date: "2026-06-25",
              planned_pickup_date: "2026-06-24",
              meets_deadline: false,
              days_late: 1,
              suggested_production_type: "AUTOMATIC",
              suggested_line_is_colour_orphan: true,
              suggested_line_is_small: true,
              paint_status: "OK",
              paint_remaining_kg: 20,
            },
          ],
        },
      ],
    }),
  ),
}));

import { CapacityBoard } from "../src/components/CapacityBoard";

describe("CapacityBoard (N49-9)", () => {
  it("renders the day column with below-floor, at-risk-deadline, paint-blocked and infeasible flags", async () => {
    render(<CapacityBoard />);

    expect(await screen.findByText("Plan wielodniowy")).toBeTruthy();
    // Both orders show in the day column, in sweep order.
    expect(screen.getByText("WO-1")).toBeTruthy();
    expect(screen.getByText("WO-2")).toBeTruthy();
    // Flags derived from the backend plan (board never infers these locally).
    expect(screen.getByText("poniżej progu")).toBeTruthy();
    expect(screen.getByText("brak farby")).toBeTruthy();
    expect(screen.getByText("po terminie +1 dn.")).toBeTruthy();
    // The "won't make it" set drives the warning banner.
    expect(screen.getByText(/nie zdąży na termin/)).toBeTruthy();
  });
});
