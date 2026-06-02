/**
 * FieldHistoryPanel — inline expansion panel below a table row.
 *
 * Conforms to 08-UI-SPEC.md §FieldHistoryPanel:
 * - Triggers via Clock icon click (controlled externally; this component is always rendered when open)
 * - max-height 320px, overflow-y scroll
 * - Each event: timestamp + source badge + old → new values
 * - Most-recent first (ordered by API response)
 * - Empty state: "No history for this field." (12px muted)
 * - Not a modal — inline expansion below the triggering row
 */
import { useEffect, useState } from "react";
import { getFieldHistory, type BibleEventDTO } from "../api/client";

interface FieldHistoryPanelProps {
  seriesId: number;
  entityType: string;
  entityId: number;
  field?: string;
  onClose: () => void;
}

function formatTimestamp(iso: string | null): string {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    const hh = String(d.getHours()).padStart(2, "0");
    const mm = String(d.getMinutes()).padStart(2, "0");
    const ss = String(d.getSeconds()).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    const month = d.toLocaleString("en", { month: "short" });
    return `${hh}:${mm}:${ss} ${day} ${month}`;
  } catch {
    return iso;
  }
}

function SourceBadge({ source }: { source: string }) {
  return (
    <span
      className="inline-flex items-center px-1.5 py-0.5 rounded text-xs font-normal"
      style={{ backgroundColor: "#1e293b", color: "#94a3b8" }}
    >
      {source}
    </span>
  );
}

export default function FieldHistoryPanel({
  seriesId,
  entityType,
  entityId,
  field,
}: FieldHistoryPanelProps) {
  const [events, setEvents] = useState<BibleEventDTO[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const data = await getFieldHistory(seriesId, entityType, entityId, field);
        if (!cancelled) {
          setEvents(data);
          setLoading(false);
        }
      } catch {
        if (!cancelled) setLoading(false);
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [seriesId, entityType, entityId, field]);

  return (
    <div className="bg-bg-surface border border-[#2d3148] rounded p-4 max-h-80 overflow-y-auto">
      {loading ? (
        <p className="text-xs text-text-muted">Loading…</p>
      ) : events.length === 0 ? (
        <p className="text-xs text-text-muted">No history for this field.</p>
      ) : (
        <div className="flex flex-col gap-1">
          {events.map((evt) => (
            <div key={evt.id} className="flex gap-2 text-xs py-1 items-start">
              <span className="text-text-muted whitespace-nowrap flex-shrink-0">
                {formatTimestamp(evt.created_at)}
              </span>
              <SourceBadge source={evt.source} />
              <span className="text-text-primary">
                {String(evt.old_value ?? "—")}
                {" → "}
                {String(evt.new_value ?? "—")}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
