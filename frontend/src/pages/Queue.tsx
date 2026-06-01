/**
 * Queue page — in-flight job monitor (SVC-03).
 *
 * Conforms to 07-UI-SPEC.md §Queue View:
 * - JobTable with queue columns (Series, Episode, File, Status, Queued, Logs)
 * - Polls GET /api/queue every 10 seconds
 * - No loading spinner on re-polls — silent refresh
 * - Last-updated timestamp displayed (12px regular muted)
 * - API unreachable: amber banner (not blocking modal)
 * - Count badge next to heading
 */
import { useState, useEffect, useCallback } from "react";
import { getQueue, type QueueJob } from "../api/client";
import { QueueTable } from "../components/JobTable";

function UnreachableBanner() {
  return (
    <div
      className="w-full mb-4 px-4 py-3 text-sm rounded"
      style={{ backgroundColor: "#451a03", color: "#fbbf24" }}
      role="alert"
    >
      Cannot reach the Trezarr service. Check that the server is running.
    </div>
  );
}

export default function Queue() {
  const [jobs, setJobs] = useState<QueueJob[]>([]);
  const [unreachable, setUnreachable] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<string>("");

  const load = useCallback(async () => {
    try {
      const data = await getQueue();
      setJobs(data);
      setUnreachable(false);
      const now = new Date();
      const hh = String(now.getHours()).padStart(2, "0");
      const mm = String(now.getMinutes()).padStart(2, "0");
      const ss = String(now.getSeconds()).padStart(2, "0");
      setLastUpdated(`${hh}:${mm}:${ss}`);
    } catch {
      setUnreachable(true);
    }
  }, []);

  useEffect(() => {
    void load();
    // Poll every 10 seconds (07-UI-SPEC §Queue View)
    const interval = setInterval(() => void load(), 10_000);
    return () => clearInterval(interval);
  }, [load]);

  return (
    <div>
      <div className="flex items-center gap-3 mb-4">
        <h1 className="text-lg font-semibold text-[#e2e6f0]">Queue</h1>
        <span className="text-xs text-[#6b7280]">
          {jobs.length} {jobs.length === 1 ? "item" : "items"}
        </span>
      </div>

      {unreachable && <UnreachableBanner />}

      <QueueTable jobs={jobs} lastUpdated={lastUpdated} />
    </div>
  );
}
