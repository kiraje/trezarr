/**
 * Toast — fixed bottom-right notification strip.
 *
 * Conforms to 07-UI-SPEC.md §Toast / Notification:
 * - Fixed position, 280px wide, bottom-right
 * - Success: green left-border (#22c55e), secondary background
 * - Error: red left-border (#ef4444), secondary background
 * - Auto-dismisses after 4 seconds
 * - No animation (functional-first)
 * - Single toast at a time; new toast replaces previous
 */
import { useEffect, useCallback } from "react";

export type ToastVariant = "success" | "error";

export interface ToastState {
  message: string;
  variant: ToastVariant;
  id: number;
}

interface ToastProps {
  toast: ToastState | null;
  onDismiss: () => void;
}

export default function Toast({ toast, onDismiss }: ToastProps) {
  const dismiss = useCallback(() => onDismiss(), [onDismiss]);

  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(dismiss, 4000);
    return () => clearTimeout(timer);
  }, [toast, dismiss]);

  if (!toast) return null;

  const borderColor =
    toast.variant === "success" ? "#22c55e" : "#ef4444";

  return (
    <div
      className="fixed bottom-4 right-4 w-[280px] bg-bg-surface text-[#e2e6f0] text-sm px-4 py-3 rounded shadow-lg border border-[#2d3148]"
      style={{ borderLeft: `3px solid ${borderColor}` }}
      role="status"
      aria-live="polite"
    >
      {toast.message}
    </div>
  );
}
