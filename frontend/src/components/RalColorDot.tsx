import { RAL } from "ral-colors";

function normalizeKey(ralCode: string): string {
  const stripped = ralCode.trim().replace(/\s+/g, "").toUpperCase();
  return stripped.startsWith("RAL") ? stripped : `RAL${stripped}`;
}

function getRalColor(ralCode: string | null | undefined): string | null {
  if (!ralCode) return null;
  const key = normalizeKey(ralCode);

  const classic = RAL.classic[key];
  if (classic?.HEX) return classic.HEX;

  const effect = RAL.effect[key];
  if (effect?.groups?.[0]) {
    const { r, g, b } = effect.groups[0].rgb;
    return `rgb(${r},${g},${b})`;
  }

  return null;
}

export function RalColorDot({ ralCode }: { ralCode: string | null | undefined }) {
  const color = getRalColor(ralCode);

  if (!color) {
    return (
      <span
        className="inline-flex h-4 w-4 flex-none items-center justify-center rounded-full border border-brand-line bg-brand-surface"
        title={ralCode ? `Nieznany RAL: ${ralCode}` : "Brak kodu RAL"}
      >
        <span className="text-[8px] font-bold leading-none text-brand-muted">?</span>
      </span>
    );
  }

  return (
    <span
      className="inline-block h-4 w-4 flex-none rounded-full border border-black/10"
      style={{ backgroundColor: color }}
      title={ralCode ?? undefined}
    />
  );
}
