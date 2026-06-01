/**
 * History page — completed/failed job history (SVC-03).
 *
 * Conforms to 07-UI-SPEC.md §History View:
 * - JobTable with history columns (Series, Episode, File, Status, Finished, Reason, Actions)
 * - Polls GET /api/jobs every 30 seconds
 * - RetryButton on failed/quarantined rows
 * - API unreachable: amber banner
 * - Count badge next to heading
 */
import { useState, useEffect, useCallback } from "react";
import { getJobs, type HistoryJob } from "../api/client";
import { HistoryTable } from "../components/JobTable";
import Toast from "../components/Toast";
import type { ToastState } from "../components/Toast";

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

export default function History() {
  const [jobs, setJobs] = useState<HistoryJob[]>([]);
  const [unreachable, setUnreachable] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<string>("");
  const [toast, setToast] = useState<ToastState | null>(null);

  const load = useCallback(async () => {
    try {
      const data = await getJobs();
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
    // Poll every 30 seconds (07-UI-SPEC §History View)
    const interval = setInterval(() => void load(), 30_000);
    return () => clearInterval(interval);
  }, [load]);

  return (
    <div>
      <div className="flex items-center gap-3 mb-4">
        <h1 className="text-lg font-semibold text-[#e2e6f0]">History</h1>
        <span className="text-xs text-[#6b7280]">
          {jobs.length} {jobs.length === 1 ? "item" : "items"}
        </span>
      </div>

      {unreachable && <UnreachableBanner />}

      <HistoryTable
        jobs={jobs}
        lastUpdated={lastUpdated}
        onToast={(t) => setToast({ ...t, id: Date.now() })}
        onRefresh={() => void load()}
      />

      <Toast toast={toast} onDismiss={() => setToast(null)} />
    </div>
  );
}
