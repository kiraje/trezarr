/**
 * JobLogs page — per-job log trail view (SVC-03).
 *
 * Conforms to 07-UI-SPEC.md §Per-Job Logs View:
 * - Breadcrumb "← History" at top
 * - Job summary strip: source_path, status, trigger
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
        <button
          type="button"
          onClick={() => navigate("/history")}
          className="inline-flex items-center gap-1 text-xs text-accent hover:text-[#2563eb] focus:outline-[#3b82f6] focus:outline-2 focus:outline-offset-2 transition-colors duration-150"
        >
          <ChevronLeft size={14} aria-hidden="true" />
          History
        </button>
      </div>

      <h1 className="text-lg font-semibold text-[#e2e6f0]">
        Job #{jobId} Logs
      </h1>

      {/* Job summary strip */}
      {job && (
        <div
          className="flex items-center gap-4 h-10 bg-bg-surface border border-[#2d3148] rounded px-4 text-xs text-[#6b7280]"
        >
          <span className="truncate max-w-xs" title={job.source_path}>
            {job.source_path}
          </span>
          <StatusBadge status={job.status as JobStatus} />
          <span className="text-[#6b7280]">trigger: {job.trigger}</span>
          {job.finished_at && (
            <span className="text-[#6b7280]">
              finished:{" "}
              {new Date(job.finished_at).toLocaleString()}
            </span>
          )}
        </div>
      )}

      {/* Log area */}
      {loading ? (
        <div className="text-xs text-[#6b7280] py-4">Loading…</div>
      ) : error ? (
        <div
          className="px-4 py-3 text-sm rounded"
          style={{ backgroundColor: "#2d1515", color: "#f87171" }}
          role="alert"
        >
          {error}
        </div>
      ) : (
        <LogViewer entries={entries} />
      )}
    </div>
  );
}
