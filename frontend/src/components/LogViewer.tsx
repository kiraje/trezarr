/**
 * LogViewer — monochrome terminal aesthetic for per-job log display.
 *
 * Conforms to 07-UI-SPEC.md §LogViewer and 15-UI-SPEC.md §LogViewer reskin:
 * - 13px monospace text, dark terminal aesthetic
 * - Colored per log level: INFO=#4ade80, ERROR=#f87171, WARNING=#fb923c, DEBUG=#94a3b8
 * - Lines are <div> elements (NOT pre/innerHTML — renders as textContent to prevent XSS, T-07-05-05)
 * - Scroll-to-bottom button (ChevronsDown) — shadcn Button variant="ghost" size="icon"
 * - max-height calc(100vh - 200px), overflow-y auto
 * - No word-wrap; overflow hidden with horizontal scroll
 * - Timestamp HH:MM:SS prefix per line in text-muted-foreground
 * - Level prefix [INFO] etc. 5-char fixed width with space padding
 */
import { useRef, useEffect, useState, useCallback } from "react";
import { ChevronsDown } from "lucide-react";
import type { JobLogEntry } from "../api/client";
import { Button } from "./ui/button";

const LEVEL_COLORS: Record<string, string> = {
  INFO: "#4ade80",
  ERROR: "#f87171",
  WARNING: "#fb923c",
  WARN: "#fb923c",
  DEBUG: "#94a3b8",
};

const LEVEL_LABELS: Record<string, string> = {
  INFO: "[INFO ]",
  ERROR: "[ERROR]",
  WARNING: "[WARN ]",
  WARN: "[WARN ]",
  DEBUG: "[DEBUG]",
};

function formatTimestamp(iso: string | null | undefined): string {
  if (!iso) return "??:??:??";
  const d = new Date(iso);
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  const ss = String(d.getSeconds()).padStart(2, "0");
  return `${hh}:${mm}:${ss}`;
}

interface LogViewerProps {
  entries: JobLogEntry[];
}

export default function LogViewer({ entries }: LogViewerProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const [showScrollBtn, setShowScrollBtn] = useState(false);

  const scrollToBottom = useCallback(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, []);

  // Scroll to bottom when new entries arrive (if already near bottom)
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const isNearBottom =
      el.scrollHeight - el.scrollTop - el.clientHeight < 80;
    if (isNearBottom) scrollToBottom();
  }, [entries, scrollToBottom]);

  function handleScroll() {
    const el = scrollRef.current;
    if (!el) return;
    const atBottom =
      el.scrollHeight - el.scrollTop - el.clientHeight < 80;
    setShowScrollBtn(!atBottom);
  }

  if (entries.length === 0) {
    return (
      <div className="flex items-center justify-center py-12 text-xs text-muted-foreground">
        No log entries recorded for this job.
      </div>
    );
  }

  return (
    <div className="relative">
      <div
        ref={scrollRef}
        onScroll={handleScroll}
        className="bg-background border border-border rounded overflow-y-auto overflow-x-auto"
        style={{ maxHeight: "calc(100vh - 200px)" }}
        role="log"
        aria-label="Job execution log"
        aria-live="polite"
      >
        {entries.map((entry) => {
          const levelColor =
            LEVEL_COLORS[entry.level?.toUpperCase()] ?? "#94a3b8";
          const levelLabel =
            LEVEL_LABELS[entry.level?.toUpperCase()] ?? `[${(entry.level ?? "?????").padEnd(5)}]`;
          const ts = formatTimestamp(entry.created_at);

          return (
            <div
              key={entry.id}
              className="whitespace-nowrap py-px"
              style={{
                fontFamily:
                  'ui-monospace, "Cascadia Code", "Fira Code", Menlo, monospace',
                fontSize: "13px",
                lineHeight: "1.6",
                color: levelColor,
              }}
            >
              {/* Timestamp in muted color */}
              <span className="text-muted-foreground">{ts} </span>
              {/* Level prefix 7-char fixed width */}
              <span>{levelLabel} </span>
              {/* Message rendered as text content — never innerHTML (T-07-05-05 XSS prevention) */}
              <span>{entry.message}</span>
            </div>
          );
        })}
      </div>

      {/* Scroll-to-bottom button — appears when user has scrolled up */}
      {showScrollBtn && (
        <Button
          type="button"
          variant="ghost"
          size="icon"
          onClick={scrollToBottom}
          className="absolute bottom-4 right-4"
          aria-label="Scroll to bottom"
        >
          <ChevronsDown size={16} aria-hidden="true" />
        </Button>
      )}
    </div>
  );
}
