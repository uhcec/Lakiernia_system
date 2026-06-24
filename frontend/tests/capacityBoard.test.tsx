import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { MultiDayPlan } from "../src/types/manager";

// A populated plan covering the flag paths (below-floor day, an at-risk-deadline order, a paint-blocked
// order). ``queuePositions`` lets a test make the live queue order match or differ from the suggested
// (day→sweep) order — the NA51 blend. By default it matches (queue 1,2 == sweep slots 0,1).
function makePlan(productionType: "MANUAL" | "AUTOMATIC", queuePositions: [number, number]): MultiDayPlan {
  return {
    production_type: productionType,
    shift_length: "LONG",
    shift_advised: true,
    horizon_working_days: 3,
    changeover_minutes: 20,
    changeover_is_measured: false,
    infeasible_order_ids: [2],
    queue_revision: "2026-06-25T07:00:00",
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
            queue_position: queuePositions[0],
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
            planning_priority: null,
          },
          {
            work_order_id: 2,
            order_number: "WO-2",
            customer_name: "Beta",
            ral_code: "RAL 7016",
            total_area_m2: 150,
            queue_position: queuePositions[1],
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
            planning_priority: null,
          },
        ],
      },
    ],
  };
}

// The board fetches the plan on mount; default mock = the live queue already matches the suggested order.
vi.mock("../src/api/managerApi", () => ({
  fetchMultiDayPlan: vi.fn((productionType: "MANUAL" | "AUTOMATIC") =>
    Promise.resolve(makePlan(productionType, [1, 2])),
  ),
  reorderWorkOrderQueue: vi.fn(() => Promise.resolve([])),
}));

import { fetchMultiDayPlan, reorderWorkOrderQueue } from "../src/api/managerApi";
import { CapacityBoard } from "../src/components/CapacityBoard";

describe("CapacityBoard (N49-9 / NA51)", () => {
  it("renders the day column with below-floor, at-risk-deadline, paint-blocked and infeasible flags", async () => {
    render(<CapacityBoard />);

    expect(await screen.findByText("Plan wielodniowy")).toBeTruthy();
    // Defaults to the AUTOMATIC line.
    expect(fetchMultiDayPlan).toHaveBeenCalledWith("AUTOMATIC", 3);
    // Both orders show in the day column, in sweep order.
    expect(screen.getByText("WO-1")).toBeTruthy();
    expect(screen.getByText("WO-2")).toBeTruthy();
    // Flags derived from the backend plan (board never infers these locally).
    expect(screen.getByText("poniżej progu")).toBeTruthy();
    expect(screen.getByText("brak farby")).toBeTruthy();
    expect(screen.getByText("po terminie +1 dn.")).toBeTruthy();
    // The "won't make it" set drives the warning banner.
    expect(screen.getByText(/nie zdąży na termin/)).toBeTruthy();
    // The live queue matches the suggestion → no apply action, a reassuring note instead.
    expect(screen.getByText(/zgodna z planem/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Zastosuj plan" })).toBeNull();
  });

  it("switches the line and refetches when the MANUAL toggle is pressed (NA55)", async () => {
    render(<CapacityBoard />);
    await screen.findByText("Plan wielodniowy");

    fireEvent.click(screen.getByRole("button", { name: "Ręczna" }));

    await waitFor(() => expect(fetchMultiDayPlan).toHaveBeenCalledWith("MANUAL", 3));
    expect(screen.getByRole("button", { name: "Ręczna" }).getAttribute("aria-pressed")).toBe("true");
  });

  it("shows a closed 'today' and hides dateless overflow days (NA56 / 3-day plan)", async () => {
    const base = makePlan("AUTOMATIC", [1, 2]);
    const work = base.days[0];
    const closedToday = {
      ...work,
      day_index: 0,
      scheduled_date: "2026-06-24",
      net_ceiling_m2: 0,
      gross_ceiling_m2: 0,
      floor_m2: 0,
      placed_m2: 0,
      placed_order_count: 0,
      placements: [],
    };
    const overflow = {
      ...work,
      day_index: 2,
      scheduled_date: null, // beyond the 3-day horizon → must NOT render as a column
      placements: [{ ...work.placements[0], work_order_id: 9, order_number: "WO-OVERFLOW" }],
    };
    const plan = { ...base, days: [closedToday, { ...work, day_index: 1 }, overflow] };
    vi.mocked(fetchMultiDayPlan).mockResolvedValueOnce(plan);

    render(<CapacityBoard />);
    await screen.findByText("Plan wielodniowy");

    expect(screen.getByText(/Po godzinach/)).toBeTruthy(); // today is closed, shown but not broken
    expect(screen.getByText("WO-1")).toBeTruthy(); // the dated working day renders
    expect(screen.queryByText("WO-OVERFLOW")).toBeNull(); // the dateless overflow day is not a column
  });

  it("applies the suggested order back to the queue when it differs from the live order (NA51)", async () => {
    // Live queue is WO-2 then WO-1 (positions 2,1), but the suggested sweep is WO-1 then WO-2.
    vi.mocked(fetchMultiDayPlan).mockResolvedValueOnce(makePlan("AUTOMATIC", [2, 1]));
    render(<CapacityBoard />);

    const apply = await screen.findByRole("button", { name: "Zastosuj plan" });
    fireEvent.click(apply);

    await waitFor(() =>
      expect(reorderWorkOrderQueue).toHaveBeenCalledWith({
        production_type: "AUTOMATIC",
        queue_revision: "2026-06-25T07:00:00",
        items: [
          { work_order_id: 1, queue_position: 1 },
          { work_order_id: 2, queue_position: 2 },
        ],
      }),
    );
  });
});
