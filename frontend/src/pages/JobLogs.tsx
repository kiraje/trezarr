/**
 * JobLogs page — per-job log trail view (SVC-03).
 *
 * Conforms to 07-UI-SPEC.md §Per-Job Logs View and 15-UI-SPEC.md §JobLogs reskin:
 * - Breadcrumb "← History" at top (Button variant="ghost" size="sm")
 * - Heading: text-xl font-semibold text-foreground
 * - Job summary strip: Card/CardContent replacing legacy bg-bg-surface border
 * - Loading state: three Skeleton rows
 * - Error state: <div role="alert"> with bg-destructive/10 text-destructive
 * - Empty state: muted paragraph when no entries
 * - LogViewer with getJobLogs(id) data
 * - Route param: /jobs/:id/logs
 */
import { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { ChevronLeft } from "lucide-react";
import { getJobLogs, getJobs, type JobLogEntry, type HistoryJob } from "../api/client";
import LogViewer from "../components/LogViewer";
import StatusBadge from "../components/StatusBadge";
import type { JobStatus } from "../components/StatusBadge";
import { Button } from "../components/ui/button";
import { Card, CardContent } from "../components/ui/card";
import { Skeleton } from "../components/ui/skeleton";

export default function JobLogs() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const jobId = parseInt(id ?? "0", 10);

  const [entries, setEntries] = useState<JobLogEntry[]>([]);
  const [job, setJob] = useState<HistoryJob | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!jobId) {
      setError("Invalid job ID");
      setLoading(false);
      return;
    }

    async function load() {
      try {
        const [logs, allJobs] = await Promise.all([
          getJobLogs(jobId),
          getJobs(),
        ]);
        setEntries(logs);
        // Find the job in history to show summary
        const found = allJobs.find((j) => j.id === jobId);
        if (found) setJob(found);
        setLoading(false);
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Failed to load logs",
        );
        setLoading(false);
      }
    }

    void load();
  }, [jobId]);

  return (
    <div className="flex flex-col gap-4">
      {/* Breadcrumb */}
      <div>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={() => navigate("/history")}
          className="text-primary"
        >
          <ChevronLeft size={14} aria-hidden="true" />
          History
        </Button>
      </div>

      <h1 className="text-xl font-semibold text-foreground">
        Job #{jobId} Logs
      </h1>

      {/* Job summary strip */}
      {job && (
        <Card>
          <CardContent className="flex items-center gap-4 h-10 px-4 text-xs text-muted-foreground py-0">
            <span className="truncate max-w-xs" title={job.source_path}>
              {job.source_path}
            </span>
            <StatusBadge status={job.status as JobStatus} />
            <span className="text-muted-foreground">trigger: {job.trigger}</span>
            {job.finished_at && (
              <span className="text-muted-foreground">
                finished:{" "}
                {new Date(job.finished_at).toLocaleString()}
              </span>
            )}
          </CardContent>
        </Card>
      )}

      {/* Log area */}
      {loading ? (
        <div className="flex flex-col gap-2">
          <Skeleton className="h-8 w-32" />
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-64 w-full" />
        </div>
      ) : error ? (
        <div
          role="alert"
          className="px-4 py-3 text-sm rounded bg-destructive/10 text-destructive"
        >
          {error}
        </div>
      ) : (
        <>
          {!loading && !error && entries.length === 0 && (
            <p className="text-sm text-muted-foreground py-8 text-center">
              No log entries for this job.
            </p>
          )}
          <LogViewer entries={entries} />
        </>
      )}
    </div>
  );
}
