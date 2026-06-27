import { NumberInput } from "./NumberInput";
import { balanceClasses, type BalanceTone } from "../utils/workOrderDisplay";

export const CORRECTION_REASON_OPTIONS = [
  { value: "niedomalowanie", label: "Niedomalowanie" },
  { value: "za grubo", label: "Za grubo" },
  { value: "wtrącenia", label: "Wtrącenia" },
  { value: "inne", label: "Inne" },
];

export type CorrectionSplitField =
  | "correctionProfilesQuantity"
  | "correctionAccessoriesQuantity"
  | "correctionReasonCategory"
  | "correctionReasonNote";

interface CorrectionSplitFieldsProps {
  correctionProfilesQuantity: string;
  correctionAccessoriesQuantity: string;
  correctionReasonCategory: string;
  correctionReasonNote: string;
  splitBalance: { text: string; tone: BalanceTone };
  onFieldChange: (field: CorrectionSplitField, value: string) => void;
}

/**
 * The "podział poprawki" sub-form shared by the packing and Decoral completion cards (FRONTEND_TRIAGE C3b):
 * split the correction quantity into profiles + accessories, with a required reason and an optional note.
 * Field keys match the pages' draft field names so the caller can pipe `onFieldChange` straight into its
 * `updateDraft`. The packing-only "Rodzaj poprawki" disposition stays in the packing card (it has no
 * equivalent on Decoral).
 */
export function CorrectionSplitFields({
  correctionProfilesQuantity,
  correctionAccessoriesQuantity,
  correctionReasonCategory,
  correctionReasonNote,
  splitBalance,
  onFieldChange,
}: CorrectionSplitFieldsProps) {
  return (
    <>
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="space-y-1 text-sm font-medium text-steel">
          <span>Profile do poprawki</span>
          <NumberInput
            min="0"
            step="1"
            value={correctionProfilesQuantity}
            onValueChange={(value) => onFieldChange("correctionProfilesQuantity", value)}
            className="w-full rounded-lg border border-line bg-white px-3 py-2 text-base font-semibold text-ink outline-none transition focus:border-accent"
          />
        </label>
        <label className="space-y-1 text-sm font-medium text-steel">
          <span>Akcesoria do poprawki</span>
          <NumberInput
            min="0"
            step="1"
            value={correctionAccessoriesQuantity}
            onValueChange={(value) => onFieldChange("correctionAccessoriesQuantity", value)}
            className="w-full rounded-lg border border-line bg-white px-3 py-2 text-base font-semibold text-ink outline-none transition focus:border-accent"
          />
        </label>
      </div>

      <div className={["rounded-lg border px-3 py-2 text-sm font-semibold", balanceClasses(splitBalance.tone)].join(" ")}>
        Podział poprawki: {splitBalance.text}
      </div>

      <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <label className="space-y-1 text-sm font-medium text-steel">
          <span>Powód poprawki</span>
          <select
            value={correctionReasonCategory}
            onChange={(event) => onFieldChange("correctionReasonCategory", event.target.value)}
            className="w-full rounded-lg border border-line bg-white px-3 py-2 text-sm text-ink outline-none transition focus:border-accent"
          >
            <option value="">Wybierz</option>
            {CORRECTION_REASON_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        {correctionReasonCategory === "inne" ? (
          <label className="space-y-1 text-sm font-medium text-steel">
            <span>Notatka</span>
            <input
              type="text"
              maxLength={500}
              value={correctionReasonNote}
              onChange={(event) => onFieldChange("correctionReasonNote", event.target.value)}
              placeholder="Notatka"
              className="w-full rounded-lg border border-line bg-white px-3 py-2 text-sm text-ink outline-none transition focus:border-accent"
            />
          </label>
        ) : null}
      </div>
    </>
  );
}
