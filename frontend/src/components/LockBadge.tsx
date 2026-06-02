/**
 * LockBadge — colored dot + text label for Bible field provenance.
 *
 * Mirrors StatusBadge exactly — same 4px dot + text label structure, same h-5/px-1.5/text-xs.
 * Colors: locked uses StatusBadge "done" palette; inference uses "queued" palette.
 *
 * Conforms to 08-UI-SPEC.md §LockBadge:
 * - Never color-only (accessibility requirement — always includes text label)
 * - Screen readers read "Locked" or "Inference"
 * - 4px dot + 12px regular text, height 20px
 */

export type LockState = "locked" | "inference";

interface LockConfig {
  bg: string;
  text: string;
  dot: string;
  label: string;
}

const LOCK_CONFIG: Record<LockState, LockConfig> = {
  locked: {
    bg: "#14291e",
    text: "#4ade80",
    dot: "#22c55e",
    label: "Locked",
  },
  inference: {
    bg: "#1e293b",
    text: "#94a3b8",
    dot: "#64748b",
    label: "Inference",
  },
};

interface LockBadgeProps {
  state: LockState;
}

export default function LockBadge({ state }: LockBadgeProps) {
  const config = LOCK_CONFIG[state];
  return (
    <span
      className="inline-flex items-center gap-1 h-5 px-1.5 rounded text-xs font-normal"
      style={{ backgroundColor: config.bg, color: config.text }}
    >
      {/* 4px colored dot — accessibility: color is supplementary, not sole indicator */}
      <span
        className="inline-block w-1 h-1 rounded-full flex-shrink-0"
        style={{ backgroundColor: config.dot }}
        aria-hidden="true"
      />
      {config.label}
    </span>
  );
}
