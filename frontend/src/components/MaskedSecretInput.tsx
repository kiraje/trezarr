/**
 * MaskedSecretInput — password input for API keys and SecretStr fields.
 *
 * Conforms to 07-UI-SPEC.md §MaskedSecretInput:
 * - type="password" by default (browser bullet masking)
 * - is_set=true: shows placeholder "••••••••" + "set" chip; stored secret not revealed
 * - Eye toggle for typed (not stored) value visibility
 * - env-locked: disabled input with "(set via environment variable)" in muted italic
 * - New value only sent when user explicitly types; clearing and re-typing = new value
 */
import { useState } from "react";
import { Eye, EyeOff, Lock } from "lucide-react";

interface MaskedSecretInputProps {
  id: string;
  label: string;
  isSet?: boolean;
  envLocked?: boolean;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
}

export default function MaskedSecretInput({
  id,
  label,
  isSet = false,
  envLocked = false,
  value,
  onChange,
  placeholder = "Enter API key",
}: MaskedSecretInputProps) {
  const [showTyped, setShowTyped] = useState(false);

  const inputClasses =
    "h-9 w-full bg-bg-surface border border-[#2d3148] rounded px-2 text-sm text-[#e2e6f0] focus:outline-[#3b82f6] focus:outline-2 focus:outline-offset-2";

  if (envLocked) {
    return (
      <div className="flex flex-col gap-1">
        <label
          htmlFor={id}
          className="text-xs text-[#6b7280] flex items-center gap-1"
        >
          {label}
          <Lock size={12} aria-hidden="true" />
        </label>
        <input
          id={id}
          type="text"
          disabled
          value=""
          placeholder="set via environment variable"
          className={`${inputClasses} italic text-[#6b7280] cursor-not-allowed opacity-60`}
          readOnly
        />
        <span className="text-xs text-[#6b7280]">
          (set via environment variable)
        </span>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="text-xs text-[#6b7280]">
        {label}
      </label>
      <div className="flex items-center gap-2">
        <div className="relative flex-1">
          <input
            id={id}
            type={showTyped ? "text" : "password"}
            value={value}
            onChange={(e) => onChange(e.target.value)}
            placeholder={isSet && !value ? "••••••••" : placeholder}
            className={`${inputClasses} pr-8`}
            autoComplete="new-password"
          />
          {/* Eye toggle — only shows for typed (not stored) value */}
          {value && (
            <button
              type="button"
              onClick={() => setShowTyped((v) => !v)}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-[#6b7280] hover:text-[#e2e6f0] focus:outline-[#3b82f6] focus:outline-2 focus:outline-offset-2"
              aria-label={showTyped ? "Hide value" : "Show value"}
            >
              {showTyped ? <EyeOff size={14} /> : <Eye size={14} />}
            </button>
          )}
        </div>
        {/* "set" chip if field has a stored value and user hasn't typed a new one */}
        {isSet && !value && (
          <span className="text-xs text-[#6b7280] flex-shrink-0">set</span>
        )}
      </div>
    </div>
  );
}
