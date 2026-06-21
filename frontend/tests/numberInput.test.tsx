import { useState } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { NumberInput } from "../src/components/NumberInput";

function ControlledNumberInput({ initial = "20", step = "0.01" }: { initial?: string; step?: string }) {
  const [value, setValue] = useState(initial);
  return <NumberInput value={value} step={step} min="0" onValueChange={setValue} />;
}

describe("NumberInput (NA35 — wheel never yields fractions)", () => {
  it("moves the value by whole units on wheel even when step allows decimals", () => {
    render(<ControlledNumberInput initial="20" step="0.01" />);
    const input = screen.getByRole("spinbutton") as HTMLInputElement;
    input.focus();

    // Scroll up: 20 -> 21 (a whole kg), never 20.01.
    fireEvent.wheel(input, { deltaY: -1 });
    expect(input.value).toBe("21");

    // Scroll down twice: 21 -> 20 -> 19.
    fireEvent.wheel(input, { deltaY: 1 });
    fireEvent.wheel(input, { deltaY: 1 });
    expect(input.value).toBe("19");
  });

  it("does not change the value when the field is not focused", () => {
    render(<ControlledNumberInput initial="20" step="0.01" />);
    const input = screen.getByRole("spinbutton") as HTMLInputElement;

    fireEvent.wheel(input, { deltaY: -1 });
    expect(input.value).toBe("20");
  });

  it("still allows typing fractional values (keyboard entry unaffected)", () => {
    render(<ControlledNumberInput initial="20" step="0.01" />);
    const input = screen.getByRole("spinbutton") as HTMLInputElement;

    fireEvent.change(input, { target: { value: "20.5" } });
    expect(input.value).toBe("20.5");
  });

  it("clamps to min on wheel-down", () => {
    render(<ControlledNumberInput initial="0" step="1" />);
    const input = screen.getByRole("spinbutton") as HTMLInputElement;
    input.focus();

    fireEvent.wheel(input, { deltaY: 1 });
    expect(input.value).toBe("0");
  });
});
