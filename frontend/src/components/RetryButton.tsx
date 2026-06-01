/**
 * RetryButton + ConfirmationInline — retry a failed/quarantined job.
 *
 * Conforms to 07-UI-SPEC.md §RetryButton + ConfirmationInline:
 * - Ghost button with RefreshCw icon + "Retry" label
 * - On click: inline confirmation "Re-queue this item? [Re-queue] [Cancel]" — no modal
 * - On confirm: spinner; success/error Toast shown via callback
 * - Copywriting contract: "Re-queue this item?", "Re-queue", "Cancel"
 */
import { useState } from "react";
import { RefreshCw } from "lucide-react";
import { retryJob } from "../api/client";
import type { ToastState } from "./Toast";

interface RetryButtonProps {
  jobId: number;
  onToast: (toast: Omit<ToastState, "id">) => void;
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
      <button
        type="button"
        onClick={() => setState("confirming")}
        className="inline-flex items-center gap-1 text-sm text-accent hover:text-[#2563eb] focus:outline-[#3b82f6] focus:outline-2 focus:outline-offset-2 transition-colors duration-150"
        aria-label="Retry this job"
      >
        <RefreshCw size={14} aria-hidden="true" />
        Retry
      </button>
    );
  }

  if (state === "confirming") {
    return (
      <span className="inline-flex items-center gap-2 text-xs text-[#e2e6f0]">
        <span className="text-[#6b7280]">Re-queue this item?</span>
        <button
          type="button"
          onClick={handleConfirm}
          className="text-accent hover:text-[#2563eb] focus:outline-[#3b82f6] focus:outline-2 focus:outline-offset-2"
        >
          Re-queue
        </button>
        <button
          type="button"
          onClick={() => setState("idle")}
          className="text-[#6b7280] hover:text-[#e2e6f0] focus:outline-[#3b82f6] focus:outline-2 focus:outline-offset-2"
        >
          Cancel
        </button>
      </span>
    );
  }

  // pending
  return (
    <span className="inline-flex items-center gap-1 text-sm text-[#6b7280]">
      <RefreshCw size={14} className="animate-spin" aria-hidden="true" />
      Re-queuing…
    </span>
  );
}
