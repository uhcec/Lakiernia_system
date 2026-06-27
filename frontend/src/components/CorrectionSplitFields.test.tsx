import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { CorrectionSplitFields } from "./CorrectionSplitFields";

function renderFields(overrides: Partial<Parameters<typeof CorrectionSplitFields>[0]> = {}) {
  const onFieldChange = vi.fn();
  render(
    <CorrectionSplitFields
      correctionProfilesQuantity="2"
      correctionAccessoriesQuantity="1"
      correctionReasonCategory=""
      correctionReasonNote=""
      splitBalance={{ text: "Suma zgodna", tone: "success" }}
      onFieldChange={onFieldChange}
      {...overrides}
    />,
  );
  return onFieldChange;
}

describe("CorrectionSplitFields", () => {
  it("shows the split balance text", () => {
    renderFields();
    expect(screen.getByText("Podział poprawki: Suma zgodna")).toBeTruthy();
  });

  it("hides the note field unless the reason is 'inne'", () => {
    renderFields({ correctionReasonCategory: "za grubo" });
    expect(screen.queryByText("Notatka")).toBeNull();
  });

  it("shows the note field when the reason is 'inne'", () => {
    renderFields({ correctionReasonCategory: "inne" });
    expect(screen.getByText("Notatka")).toBeTruthy();
  });

  it("reports a profiles edit under its draft field key", () => {
    const onFieldChange = renderFields();
    const profiles = screen.getByLabelText("Profile do poprawki");
    fireEvent.change(profiles, { target: { value: "3" } });
    expect(onFieldChange).toHaveBeenCalledWith("correctionProfilesQuantity", "3");
  });

  it("reports a reason selection under its draft field key", () => {
    const onFieldChange = renderFields();
    fireEvent.change(screen.getByLabelText("Powód poprawki"), { target: { value: "wtrącenia" } });
    expect(onFieldChange).toHaveBeenCalledWith("correctionReasonCategory", "wtrącenia");
  });
});
