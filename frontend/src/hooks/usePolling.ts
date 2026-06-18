import { useEffect, useRef } from "react";

/**
 * Periodically invokes `callback` every `intervalMs` so a view reflects state
 * changed on other devices without a manual browser refresh (variant A polling).
 *
 * Behaviour:
 * - Pauses while the browser tab is hidden (no wasted requests in the background).
 * - Fires `callback` immediately when the tab becomes visible again, so returning
 *   to a station board shows fresh state at once.
 * - Set `enabled` to `false` to suspend polling while the user has an unsaved edit
 *   or an action in flight, so a background refresh never clobbers their input.
 *
 * The callback is expected to fetch in the background (no spinner, preserve local
 * drafts, silent on failure); see the `background` option on each loader.
 */
export function usePolling(callback: () => void, intervalMs: number, enabled = true): void {
  const savedCallback = useRef(callback);

  useEffect(() => {
    savedCallback.current = callback;
  }, [callback]);

  useEffect(() => {
    if (!enabled) {
      return;
    }

    let intervalId: number | undefined;

    const start = () => {
      if (intervalId === undefined) {
        intervalId = window.setInterval(() => savedCallback.current(), intervalMs);
      }
    };

    const stop = () => {
      if (intervalId !== undefined) {
        window.clearInterval(intervalId);
        intervalId = undefined;
      }
    };

    const handleVisibilityChange = () => {
      if (document.hidden) {
        stop();
      } else {
        savedCallback.current();
        start();
      }
    };

    document.addEventListener("visibilitychange", handleVisibilityChange);
    if (!document.hidden) {
      start();
    }

    return () => {
      stop();
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, [intervalMs, enabled]);
}

/** Default cadence for operator-facing boards (5 s). */
export const STATION_POLL_INTERVAL_MS = 5_000;
