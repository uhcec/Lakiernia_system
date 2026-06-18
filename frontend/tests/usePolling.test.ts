import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { usePolling } from "../src/hooks/usePolling";

function setHidden(hidden: boolean) {
  Object.defineProperty(document, "hidden", { configurable: true, value: hidden });
  document.dispatchEvent(new Event("visibilitychange"));
}

describe("usePolling", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    setHidden(false);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("invokes the callback on each interval while enabled", () => {
    const callback = vi.fn();
    renderHook(() => usePolling(callback, 5_000));

    expect(callback).not.toHaveBeenCalled();
    act(() => void vi.advanceTimersByTime(5_000));
    expect(callback).toHaveBeenCalledTimes(1);
    act(() => void vi.advanceTimersByTime(10_000));
    expect(callback).toHaveBeenCalledTimes(3);
  });

  it("does not poll while disabled", () => {
    const callback = vi.fn();
    renderHook(() => usePolling(callback, 5_000, false));

    act(() => void vi.advanceTimersByTime(20_000));
    expect(callback).not.toHaveBeenCalled();
  });

  it("pauses while the tab is hidden and refreshes immediately on return", () => {
    const callback = vi.fn();
    renderHook(() => usePolling(callback, 5_000));

    act(() => setHidden(true));
    act(() => void vi.advanceTimersByTime(20_000));
    expect(callback).not.toHaveBeenCalled();

    act(() => setHidden(false));
    // Returning to the tab triggers one immediate refresh...
    expect(callback).toHaveBeenCalledTimes(1);
    // ...and resumes the interval.
    act(() => void vi.advanceTimersByTime(5_000));
    expect(callback).toHaveBeenCalledTimes(2);
  });

  it("stops polling after unmount", () => {
    const callback = vi.fn();
    const { unmount } = renderHook(() => usePolling(callback, 5_000));

    act(() => void vi.advanceTimersByTime(5_000));
    expect(callback).toHaveBeenCalledTimes(1);

    unmount();
    act(() => void vi.advanceTimersByTime(20_000));
    expect(callback).toHaveBeenCalledTimes(1);
  });
});
