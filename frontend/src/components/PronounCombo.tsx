/**
 * PronounCombo — combobox for selecting Vietnamese pronoun terms.
 *
 * Conforms to 08-UI-SPEC.md §PronounCombo:
 * - Renders as <select> with terms from API (D-86 typo guard — not free-text by default)
 * - "custom…" escape hatch switches to <input type="text"> (autoFocus)
 * - "Done" text link exits custom mode (trims whitespace)
 * - If current value is not in terms list, starts in custom (text) mode
 *
 * Analog: MaskedSecretInput.tsx (controlled input with two display modes).
 */
import { useState } from "react";

interface PronounComboProps {
  value: string;
  onChange: (v: string) => void;
  terms: string[];
  placeholder?: string;
}

const inputClass =
  "h-9 w-full bg-bg-surface border border-[#2d3148] rounded px-2 text-sm text-[#e2e6f0] focus:outline-[#3b82f6] focus:outline-2 focus:outline-offset-2";

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
        <input
          type="text"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          autoFocus
          className={inputClass}
          placeholder={placeholder}
        />
        <button
          type="button"
          className="text-xs text-accent whitespace-nowrap"
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
      className={inputClass}
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
