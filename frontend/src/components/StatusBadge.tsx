/**
 * StatusBadge — colored dot + text label for job status.
 *
 * Conforms to 07-UI-SPEC.md §StatusBadge and §Semantic status palette:
 * - Never color-only (accessibility requirement — always includes text label)
 * - Screen readers read the text label
 * - 4px dot + 12px regular text, height 20px
 */

export type JobStatus =
  | "queued"
  | "running"
  | "done"
  | "failed"
  | "quarantined";

interface StatusConfig {
  bg: string;
  text: string;
  dot: string;
  label: string;
}

const STATUS_CONFIG: Record<JobStatus, StatusConfig> = {
  queued: {
    bg: "#1e293b",
    text: "#94a3b8",
    dot: "#64748b",
    label: "Queued",
  },
  running: {
    bg: "#1e3a5f",
    text: "#60a5fa",
    dot: "#3b82f6",
    label: "Running",
  },
  done: {
    bg: "#14291e",
    text: "#4ade80",
    dot: "#22c55e",
    label: "Done",
  },
  failed: {
    bg: "#2d1515",
    text: "#f87171",
    dot: "#ef4444",
    label: "Failed",
  },
  quarantined: {
    bg: "#2d1f0a",
    text: "#fb923c",
    dot: "#f97316",
    label: "Quarantined",
  },
};

interface StatusBadgeProps {
  status: JobStatus;
}

export default function StatusBadge({ status }: StatusBadgeProps) {
  const config = STATUS_CONFIG[status] ?? STATUS_CONFIG.failed;

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
