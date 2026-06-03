/**
 * LockBadge — colored dot + text label for Bible field provenance.
 *
 * Reskinned (Phase 15) onto shadcn CSS-variable token classes.
 * locked/human_override: bg-primary/20 text-primary border border-primary/40
 * inferred/llm: bg-card text-muted-foreground border border-border
 *
 * Conforms to 08-UI-SPEC.md §LockBadge:
 * - Never color-only (accessibility requirement — always includes text label)
 * - Screen readers read "Locked" or "Inference"
 * - 4px dot + 12px regular text, height 20px
 */

export type LockState = "locked" | "inference";

interface LockBadgeProps {
  state: LockState;
}

export default function LockBadge({ state }: LockBadgeProps) {
  const isLocked = state === "locked";
  return (
    <span
      className={[
        "inline-flex items-center gap-1 h-5 px-1.5 rounded text-xs font-normal border",
        isLocked
          ? "bg-primary/20 text-primary border-primary/40"
          : "bg-card text-muted-foreground border-border",
      ].join(" ")}
    >
      {/* 4px colored dot — accessibility: color is supplementary, not sole indicator */}
      <span
        className={[
          "inline-block w-1 h-1 rounded-full flex-shrink-0",
          isLocked ? "bg-primary" : "bg-muted-foreground",
        ].join(" ")}
        aria-hidden="true"
      />
      {isLocked ? "Locked" : "Inference"}
    </span>
  );
}
