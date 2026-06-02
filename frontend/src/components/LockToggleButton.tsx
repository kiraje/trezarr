/**
 * LockToggleButton — icon-only 32×32 button for locking/unlocking Bible fields.
 *
 * Conforms to 08-UI-SPEC.md §LockToggleButton:
 * - State "locked": Unlock icon, aria-label "Unlock this field"
 * - State "inference": Lock icon, aria-label "Lock this field"
 * - Hover: text-accent
 * - Focus ring: outline 2px solid #3b82f6, offset 2px
 * - disabled: opacity-50 cursor-not-allowed
 */
import { Lock, Unlock } from "lucide-react";
import type { LockState } from "./LockBadge";

interface LockToggleButtonProps {
  state: LockState;
  onToggle: () => void;
  disabled?: boolean;
}

export default function LockToggleButton({
  state,
  onToggle,
  disabled = false,
}: LockToggleButtonProps) {
  const ariaLabel =
    state === "locked" ? "Unlock this field" : "Lock this field";

  return (
    <button
      type="button"
      aria-label={ariaLabel}
      onClick={() => {
        if (!disabled) onToggle();
      }}
      disabled={disabled}
      className={[
        "w-8 h-8 flex items-center justify-center rounded",
        "text-text-muted hover:text-accent",
        "focus:outline-none focus:ring-2 focus:ring-[#3b82f6] focus:ring-offset-2",
        disabled ? "opacity-50 cursor-not-allowed" : "",
      ]
        .filter(Boolean)
        .join(" ")}
    >
      {state === "locked" ? (
        <Unlock size={14} aria-hidden="true" />
      ) : (
        <Lock size={14} aria-hidden="true" />
      )}
    </button>
  );
}
