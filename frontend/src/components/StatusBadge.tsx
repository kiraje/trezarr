/**
 * StatusBadge — shadcn Badge-based status renderer for job status.
 *
 * Conforms to 15-UI-SPEC.md §StatusBadge reskin:
 * - Never color-only (accessibility requirement — always includes text label)
 * - Maps each status to a shadcn Badge variant or semantic className
 * - Screen readers read the text label
 */
import { Badge } from "./ui/badge";

export type JobStatus =
  | "queued"
  | "in_progress"
  | "running"
  | "done"
  | "translated"
  | "failed"
  | "quarantined";

interface StatusBadgeProps {
  status: JobStatus;
}

export default function StatusBadge({ status }: StatusBadgeProps) {
  switch (status) {
    case "done":
    case "translated":
      return (
        <Badge className="bg-emerald-600/80 text-white border-transparent">
          {status === "translated" ? "Translated" : "Done"}
        </Badge>
      );
    case "failed":
      return <Badge variant="destructive">Failed</Badge>;
    case "queued":
    case "in_progress":
    case "running":
      return (
        <Badge variant="secondary">
          {status === "in_progress"
            ? "In Progress"
            : status.charAt(0).toUpperCase() + status.slice(1)}
        </Badge>
      );
    case "quarantined":
      return (
        <Badge className="bg-amber-600/80 text-white border-transparent">
          Quarantined
        </Badge>
      );
    default:
      return <Badge variant="outline">{status}</Badge>;
  }
}
