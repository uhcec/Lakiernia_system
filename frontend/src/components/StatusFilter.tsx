import type { WorkOrderStatusValue } from "../types/workOrders";

export interface StatusFilterOption {
  value: WorkOrderStatusValue | "ALL";
  label: string;
}

interface StatusFilterProps {
  options: StatusFilterOption[];
  selectedValue: WorkOrderStatusValue | "ALL";
  onChange: (value: WorkOrderStatusValue | "ALL") => void;
}

export function StatusFilter({ options, selectedValue, onChange }: StatusFilterProps) {
  return (
    <div className="flex flex-wrap gap-2">
      {options.map((option) => {
        const isActive = option.value === selectedValue;

        return (
          <button
            key={option.value}
            type="button"
            onClick={() => onChange(option.value)}
            className={[
              "rounded-full border px-4 py-2 text-sm font-medium transition-colors",
              isActive
                ? "border-accent bg-accent text-white"
                : "border-line bg-white text-steel hover:border-accent hover:text-accent",
            ].join(" ")}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}