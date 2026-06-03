/**
 * PronounCombo — combobox for selecting Vietnamese pronoun terms.
 *
 * Reskinned (Phase 15) onto shadcn Input primitive.
 *
 * Conforms to 08-UI-SPEC.md §PronounCombo:
 * - Renders as <select> with terms from API (D-86 typo guard — not free-text by default)
 * - "custom…" escape hatch switches to shadcn <Input> (autoFocus)
 * - "Done" text link exits custom mode (trims whitespace)
 * - If current value is not in terms list, starts in custom (text) mode
 * - Combo logic (filtering, selection, kinship_reciprocal) UNCHANGED.
 *
 * Analog: MaskedSecretInput.tsx (controlled input with two display modes).
 */
import { useState } from "react";
import { Input } from "./ui/input";

interface PronounComboProps {
  value: string;
  onChange: (v: string) => void;
  terms: string[];
  placeholder?: string;
}

const selectClass =
  "h-9 w-full rounded-md border border-border bg-background px-3 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

export default function PronounCombo({
  value,
  onChange,
  terms,
  placeholder = "Select…",
}: PronounComboProps) {
  // Start in custom mode if current value isn't in the terms list (and is non-empty)
  const [customMode, setCustomMode] = useState(
    !terms.includes(value) && value !== "",
  );

  if (customMode) {
    return (
      <div className="flex items-center gap-2">
        <Input
          type="text"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          autoFocus
          placeholder={placeholder}
        />
        <button
          type="button"
          className="text-xs text-primary whitespace-nowrap"
          onClick={() => {
            onChange(value.trim());
            setCustomMode(false);
          }}
        >
          Done
        </button>
      </div>
    );
  }

  return (
    <select
      value={value}
      onChange={(e) => {
        if (e.target.value === "__custom__") {
          setCustomMode(true);
        } else {
          onChange(e.target.value);
        }
      }}
      className={selectClass}
    >
      <option value="" disabled>
        {placeholder}
      </option>
      {terms.map((t) => (
        <option key={t} value={t}>
          {t}
        </option>
      ))}
      <option value="__custom__">custom…</option>
    </select>
  );
}
