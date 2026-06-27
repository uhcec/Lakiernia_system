import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ConfirmProvider, useConfirm } from "./ConfirmDialog";

// Pins the app-styled confirm modal (FRONTEND_TRIAGE D2): it must resolve true on confirm, false on
// cancel/backdrop/Escape, and render the danger tone + multi-line message.

function Harness({ onResult, options }: { onResult: (v: boolean) => void; options?: Parameters<ReturnType<typeof useConfirm>>[0] }) {
  const confirm = useConfirm();
  return (
    <button
      type="button"
      onClick={() => {
        void confirm(options ?? { message: "Na pewno?" }).then(onResult);
      }}
    >
      ask
    </button>
  );
}

function renderHarness(options?: Parameters<ReturnType<typeof useConfirm>>[0]) {
  const results: boolean[] = [];
  render(
    <ConfirmProvider>
      <Harness onResult={(v) => results.push(v)} options={options} />
    </ConfirmProvider>,
  );
  return results;
}

describe("ConfirmDialog / useConfirm", () => {
  it("resolves true when the confirm button is pressed", async () => {
    const results = renderHarness({ message: "Usunąć?", confirmLabel: "Usuń" });
    fireEvent.click(screen.getByRole("button", { name: "ask" }));
    fireEvent.click(await screen.findByRole("button", { name: "Usuń" }));
    await waitFor(() => expect(results).toEqual([true]));
    expect(screen.queryByRole("alertdialog")).toBeNull();
  });

  it("resolves false when cancelled", async () => {
    const results = renderHarness();
    fireEvent.click(screen.getByRole("button", { name: "ask" }));
    await screen.findByRole("alertdialog");
    fireEvent.click(screen.getByRole("button", { name: "Anuluj" }));
    await waitFor(() => expect(results).toEqual([false]));
  });

  it("resolves false on Escape", async () => {
    const results = renderHarness();
    fireEvent.click(screen.getByRole("button", { name: "ask" }));
    await screen.findByRole("alertdialog");
    fireEvent.keyDown(window, { key: "Escape" });
    await waitFor(() => expect(results).toEqual([false]));
  });

  it("renders a multi-line message and a danger-tone confirm button", async () => {
    renderHarness({ message: "Linia 1\nLinia 2", tone: "danger", confirmLabel: "Usuń" });
    fireEvent.click(screen.getByRole("button", { name: "ask" }));
    const dialog = await screen.findByRole("alertdialog");
    expect(dialog.textContent).toContain("Linia 1");
    expect(dialog.textContent).toContain("Linia 2");
    expect(screen.getByRole("button", { name: "Usuń" }).className).toContain("bg-rose-600");
  });
});
