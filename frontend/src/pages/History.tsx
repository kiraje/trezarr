/**
 * History page — completed/failed job history (SVC-03).
 *
 * Conforms to 07-UI-SPEC.md §History View:
 * - JobTable with history columns (Series, Episode, File, Status, Finished, Reason, Actions)
 * - Polls GET /api/jobs every 30 seconds
 * - RetryButton on failed/quarantined rows
 * - API unreachable: amber banner
 * - Count badge next to heading
 *
 * Reskinned Phase 15 plan 03: shadcn tokens + Sonner toast migration (D-03 step 1).
 */
import { useState, useEffect, useCallback } from "react";
import { toast } from "sonner";
import { getJobs, type HistoryJob } from "../api/client";
import { HistoryTable } from "../components/JobTable";

function UnreachableBanner() {
  return (
    <div
      className="w-full mb-4 px-4 py-3 text-sm rounded bg-amber-900/30 border border-amber-800 text-amber-400"
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
  const [hasLoaded, setHasLoaded] = useState(false);

  const load = useCallback(async () => {
    try {
      const data = await getJobs();
      setJobs(data);
      setUnreachable(false);
      setHasLoaded(true);
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
        <h1 className="text-xl font-semibold text-foreground">History</h1>
        <span className="text-xs text-muted-foreground">
          {jobs.length} {jobs.length === 1 ? "item" : "items"}
        </span>
      </div>

      {unreachable && <UnreachableBanner />}

      {jobs.length === 0 && hasLoaded && !unreachable ? (
        <div className="py-12 text-center">
          <p className="text-sm text-muted-foreground">No job history yet.</p>
        </div>
      ) : (
        <HistoryTable
          jobs={jobs}
          lastUpdated={lastUpdated}
          onToast={(t) => {
            if (t.variant === "success") {
              toast.success(t.message);
            } else {
              toast.error(t.message);
            }
          }}
          onRefresh={() => void load()}
        />
      )}
    </div>
  );
}
