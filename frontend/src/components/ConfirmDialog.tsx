import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";

// App-styled replacement for native window.confirm (FRONTEND_TRIAGE D2). Exposed as a promise so call
// sites stay almost unchanged: `if (!(await confirm({ message }))) return;`. Native confirm is blocking
// and unstyleable on the shop's kiosk browsers; this matches the app's modal look and supports a danger
// tone for destructive actions and multi-line messages (the packing override lists occupants).

type ConfirmTone = "default" | "danger";

interface ConfirmOptions {
  message: string;
  title?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  tone?: ConfirmTone;
}

type ConfirmFn = (options: ConfirmOptions) => Promise<boolean>;

const ConfirmContext = createContext<ConfirmFn | null>(null);

export function ConfirmProvider({ children }: { children: React.ReactNode }) {
  const [options, setOptions] = useState<ConfirmOptions | null>(null);
  const resolverRef = useRef<((value: boolean) => void) | null>(null);

  const confirm = useCallback<ConfirmFn>((opts) => {
    return new Promise<boolean>((resolve) => {
      resolverRef.current = resolve;
      setOptions(opts);
    });
  }, []);

  const settle = useCallback((value: boolean) => {
    resolverRef.current?.(value);
    resolverRef.current = null;
    setOptions(null);
  }, []);

  return (
    <ConfirmContext.Provider value={confirm}>
      {children}
      {options ? <ConfirmDialog options={options} onConfirm={() => settle(true)} onCancel={() => settle(false)} /> : null}
    </ConfirmContext.Provider>
  );
}

export function useConfirm(): ConfirmFn {
  const ctx = useContext(ConfirmContext);
  if (!ctx) {
    throw new Error("useConfirm must be used inside ConfirmProvider");
  }
  return ctx;
}

function ConfirmDialog({
  options,
  onConfirm,
  onCancel,
}: {
  options: ConfirmOptions;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const confirmButtonRef = useRef<HTMLButtonElement>(null);
  const { message, title, confirmLabel, cancelLabel, tone = "default" } = options;

  // Escape cancels; the confirm button is auto-focused so Enter confirms — parity with native confirm.
  useEffect(() => {
    confirmButtonRef.current?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onCancel();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onCancel]);

  const confirmClasses =
    tone === "danger"
      ? "bg-rose-600 text-white hover:bg-rose-700"
      : "bg-accent text-white hover:bg-teal-700";

  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center overflow-y-auto bg-black/40 px-4 py-8 backdrop-blur-sm"
      onClick={(event) => {
        if (event.target === event.currentTarget) {
          onCancel();
        }
      }}
    >
      <div role="alertdialog" aria-modal="true" className="w-full max-w-md rounded-[2rem] border border-white/70 bg-white shadow-panel">
        <div className="px-8 py-6">
          <h2 className="text-xl font-semibold text-ink">{title ?? "Potwierdź"}</h2>
          <p className="mt-3 whitespace-pre-line text-base text-steel">{message}</p>
        </div>
        <div className="flex justify-end gap-3 border-t border-line/80 px-8 py-5">
          <button
            type="button"
            onClick={onCancel}
            className="inline-flex items-center justify-center rounded-full border border-line bg-white px-5 py-2.5 text-sm font-medium text-steel transition hover:border-accent hover:text-accent"
          >
            {cancelLabel ?? "Anuluj"}
          </button>
          <button
            ref={confirmButtonRef}
            type="button"
            onClick={onConfirm}
            className={`inline-flex items-center justify-center rounded-full px-5 py-2.5 text-sm font-medium transition ${confirmClasses}`}
          >
            {confirmLabel ?? "Potwierdź"}
          </button>
        </div>
      </div>
    </div>
  );
}
