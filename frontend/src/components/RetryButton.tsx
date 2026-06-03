/**
 * RetryButton + ConfirmationInline — retry a failed/quarantined job.
 *
 * Conforms to 07-UI-SPEC.md §RetryButton + ConfirmationInline:
 * - Ghost button with RefreshCw icon + "Retry" label
 * - On click: inline confirmation "Re-queue this item? [Re-queue] [Cancel]" — no modal
 * - On confirm: spinner; success/error Toast shown via callback
 * - Copywriting contract: "Re-queue this item?", "Re-queue", "Cancel"
 *
 * Reskinned Phase 15 plan 03: Button primitive + shadcn tokens.
 */
import { useState } from "react";
import { RefreshCw } from "lucide-react";
import { retryJob } from "../api/client";
import { Button } from "./ui/button";

interface ToastPayload {
  message: string;
  variant: "success" | "error";
}

interface RetryButtonProps {
  jobId: number;
  onToast: (toast: ToastPayload) => void;
  onRetried?: () => void;
}

type State = "idle" | "confirming" | "pending";

export default function RetryButton({
  jobId,
  onToast,
  onRetried,
}: RetryButtonProps) {
  const [state, setState] = useState<State>("idle");

  async function handleConfirm() {
    setState("pending");
    try {
      await retryJob(jobId);
      setState("idle");
      onToast({ message: "Job re-queued.", variant: "success" });
      onRetried?.();
    } catch (err) {
      setState("idle");
      onToast({
        message:
          err instanceof Error ? err.message : "Failed to retry job.",
        variant: "error",
      });
    }
  }

  if (state === "idle") {
    return (
      <Button
        type="button"
        variant="ghost"
        size="sm"
        onClick={() => setState("confirming")}
        className="text-primary"
        aria-label="Retry this job"
      >
        <RefreshCw size={14} aria-hidden="true" />
        Retry
      </Button>
    );
  }

  if (state === "confirming") {
    return (
      <span className="inline-flex items-center gap-2 text-xs text-foreground">
        <span className="text-muted-foreground">Re-queue this item?</span>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={handleConfirm}
          className="text-primary"
        >
          Re-queue
        </Button>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={() => setState("idle")}
          className="text-muted-foreground"
        >
          Cancel
        </Button>
      </span>
    );
  }

  // pending
  return (
    <span className="inline-flex items-center gap-1 text-sm text-muted-foreground">
      <RefreshCw size={14} className="animate-spin" aria-hidden="true" />
      Re-queuing…
    </span>
  );
}
