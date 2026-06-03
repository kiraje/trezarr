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
import { Input } from "./ui/input";
import { Button } from "./ui/button";

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

  if (envLocked) {
    return (
      <div className="flex flex-col gap-1">
        <label
          htmlFor={id}
          className="text-xs text-muted-foreground flex items-center gap-1"
        >
          {label}
          <Lock size={12} aria-hidden="true" />
        </label>
        <Input
          id={id}
          type="text"
          disabled
          value=""
          placeholder="set via environment variable"
          className="italic cursor-not-allowed"
          readOnly
        />
        <span className="text-xs text-muted-foreground">
          (set via environment variable)
        </span>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="text-xs text-muted-foreground">
        {label}
      </label>
      <div className="flex items-center gap-2">
        <div className="relative flex-1">
          <Input
            id={id}
            type={showTyped ? "text" : "password"}
            value={value}
            onChange={(e) => onChange(e.target.value)}
            placeholder={isSet && !value ? "••••••••" : placeholder}
            className="pr-8"
            autoComplete="new-password"
          />
          {/* Eye toggle — only shows for typed (not stored) value */}
          {value && (
            <Button
              type="button"
              variant="ghost"
              size="icon"
              onClick={() => setShowTyped((v) => !v)}
              className="absolute right-0 top-0 h-full w-8"
              aria-label={showTyped ? "Hide value" : "Show value"}
            >
              {showTyped ? <EyeOff size={14} /> : <Eye size={14} />}
            </Button>
          )}
        </div>
        {/* "set" chip if field has a stored value and user hasn't typed a new one */}
        {isSet && !value && (
          <span className="text-xs text-muted-foreground flex-shrink-0">set</span>
        )}
      </div>
    </div>
  );
}
