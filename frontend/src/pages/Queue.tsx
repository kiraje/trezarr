/**
 * Queue page — in-flight job monitor (SVC-03).
 *
 * Reskinned Phase 15 plan 02: shadcn tokens, Skeleton loading state,
 * muted empty state, amber banner via className only.
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
import { Skeleton } from "../components/ui/skeleton";

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

export default function Queue() {
  const [jobs, setJobs] = useState<QueueJob[]>([]);
  const [unreachable, setUnreachable] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<string>("");
  const [hasLoaded, setHasLoaded] = useState(false);

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
      setHasLoaded(true);
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
        <h1 className="text-xl font-semibold text-foreground">Queue</h1>
        <span className="text-xs text-muted-foreground">
          {jobs.length} {jobs.length === 1 ? "item" : "items"}
        </span>
      </div>

      {unreachable && <UnreachableBanner />}

      {jobs.length === 0 && !hasLoaded && !unreachable ? (
        <div className="flex flex-col gap-1">
          <Skeleton className="h-8 w-32 mb-4" />
          <Skeleton className="h-10 w-full mb-1" />
          <Skeleton className="h-10 w-full mb-1" />
          <Skeleton className="h-10 w-full mb-1" />
          <Skeleton className="h-10 w-full" />
        </div>
      ) : jobs.length === 0 && hasLoaded && !unreachable ? (
        <div className="py-12 text-center">
          <p className="text-sm text-muted-foreground">
            Queue is empty. No jobs are currently running.
          </p>
        </div>
      ) : (
        <QueueTable jobs={jobs} lastUpdated={lastUpdated} />
      )}
    </div>
  );
}
