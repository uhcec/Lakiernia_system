import { useEffect, useRef } from "react";

type NativeInputProps = Omit<
  React.InputHTMLAttributes<HTMLInputElement>,
  "type" | "value" | "onChange"
>;

export type NumberInputProps = NativeInputProps & {
  value: string | number;
  onValueChange: (value: string) => void;
  /**
   * Whole-unit amount the mouse wheel adds/removes per notch. Defaults to 1 so
   * scrolling a number field never produces a fractional value (NA35), even on
   * fields whose `step` allows decimals when typed (e.g. m² / paint kg).
   */
  wheelStep?: number;
};

/**
 * Shared number input. Keyboard entry is the native behaviour (so decimals can
 * still be typed where `step` permits), but the mouse wheel always moves the
 * value by whole units — never tenths — and only while the field is focused, so
 * scrolling the page over it cannot silently change the value.
 */
export function NumberInput({
  value,
  onValueChange,
  wheelStep = 1,
  step = 1,
  min,
  max,
  ...rest
}: NumberInputProps) {
  const inputRef = useRef<HTMLInputElement | null>(null);

  // Keep the latest props available to the stable native wheel listener.
  const stateRef = useRef({ value, onValueChange, wheelStep, min, max });
  stateRef.current = { value, onValueChange, wheelStep, min, max };

  useEffect(() => {
    const node = inputRef.current;
    if (!node) {
      return;
    }
    const handleWheel = (event: WheelEvent) => {
      // Mirror native inputs: only react when the field is actually focused.
      if (document.activeElement !== node) {
        return;
      }
      event.preventDefault();
      const { value, onValueChange, wheelStep, min, max } = stateRef.current;
      const current = Number.parseFloat(String(value));
      const base = Number.isFinite(current) ? current : 0;
      const direction = event.deltaY < 0 ? 1 : -1;
      let next = Math.round(base + direction * wheelStep);
      if (min !== undefined && min !== "" && next < Number(min)) {
        next = Number(min);
      }
      if (max !== undefined && max !== "" && next > Number(max)) {
        next = Number(max);
      }
      onValueChange(String(next));
    };
    // React registers onWheel as a passive listener at the root, so preventDefault
    // would be ignored there; attach a non-passive native listener instead.
    node.addEventListener("wheel", handleWheel, { passive: false });
    return () => node.removeEventListener("wheel", handleWheel);
  }, []);

  return (
    <input
      ref={inputRef}
      type="number"
      step={step}
      min={min}
      max={max}
      value={value}
      onChange={(event) => onValueChange(event.target.value)}
      {...rest}
    />
  );
}
