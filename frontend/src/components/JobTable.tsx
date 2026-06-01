/**
 * JobTable — parameterized table for Queue and History views.
 *
 * Conforms to 07-UI-SPEC.md §JobTable:
 * - <table> element with <thead> + <tbody> (semantic HTML, accessible)
 * - th scope="col" on all column headers
 * - 40px row height, alternating stripe (bg-stripe on odd rows)
 * - Row hover: bg-[#22263a]
 * - StatusBadge in status column
 * - Truncate file paths with title tooltip
 * - Icon-only action buttons with aria-label
 * - Empty state: full-width centered block
 */
import { useNavigate } from "react-router-dom";
import { FileText } from "lucide-react";
import StatusBadge from "./StatusBadge";
import type { JobStatus } from "./StatusBadge";
import type { ToastState } from "./Toast";
import RetryButton from "./RetryButton";

// ── Shared helpers ────────────────────────────────────────────────────────────

/** Extract filename from a path (cross-platform). */
function basename(path: string): string {
  return path.split(/[\\/]/).pop() ?? path;
}

/** Format an ISO date string as relative time ("2 min ago", "3 hours ago"). */
function relativeTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const diff = Date.now() - new Date(iso).getTime();
  const secs = Math.floor(diff / 1000);
  if (secs < 60) return `${secs}s ago`;
  const mins = Math.floor(secs / 60);
  if (mins < 60) return `${mins} min ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours} hr ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

// ── Queue row type ────────────────────────────────────────────────────────────

export interface QueueRow {
  id: number;
  source_path: string;
  series_id: number | null;
  status: "queued" | "running";
  enqueued_at: string | null;
  started_at: string | null;
  episode_key: string;
}

// ── History row type ──────────────────────────────────────────────────────────

export interface HistoryRow {
  id: number;
  source_path: string;
  series_id: number | null;
  status: "done" | "failed" | "quarantined";
  error_reason: string | null;
  trigger: string;
  enqueued_at: string | null;
  finished_at: string | null;
  episode_key: string;
}

// ── Queue table ───────────────────────────────────────────────────────────────

interface QueueTableProps {
  jobs: QueueRow[];
  lastUpdated?: string;
}

export function QueueTable({ jobs, lastUpdated }: QueueTableProps) {
  const navigate = useNavigate();

  return (
    <div>
      {lastUpdated && (
        <p className="text-xs text-[#6b7280] mb-2">
          Last updated {lastUpdated}
        </p>
      )}
      {jobs.length === 0 ? (
        <EmptyState
          heading="No jobs in queue"
          body="Trezarr will enqueue episodes automatically when a source subtitle is found with no Vietnamese output."
        />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full border-collapse">
            <thead>
              <tr className="h-10 border-b border-[#2d3148]">
                <th
                  scope="col"
                  className="text-left text-xs font-normal text-[#6b7280] uppercase px-3"
                  style={{ width: "25%" }}
                >
                  Series
                </th>
                <th
                  scope="col"
                  className="text-left text-xs font-normal text-[#6b7280] uppercase px-3"
                  style={{ width: "10%" }}
                >
                  Episode
                </th>
                <th
                  scope="col"
                  className="text-left text-xs font-normal text-[#6b7280] uppercase px-3"
                  style={{ width: "35%" }}
                >
                  File
                </th>
                <th
                  scope="col"
                  className="text-left text-xs font-normal text-[#6b7280] uppercase px-3"
                  style={{ width: "12%" }}
                >
                  Status
                </th>
                <th
                  scope="col"
                  className="text-left text-xs font-normal text-[#6b7280] uppercase px-3"
                  style={{ width: "10%" }}
                >
                  Queued
                </th>
                <th
                  scope="col"
                  className="text-right text-xs font-normal text-[#6b7280] uppercase px-3"
                  style={{ width: "8%" }}
                >
                  Logs
                </th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((job, idx) => (
                <tr
                  key={job.id}
                  className="h-10 hover:bg-[#22263a] transition-colors duration-150"
                  style={{
                    backgroundColor: idx % 2 === 1 ? "#1e2130" : undefined,
                  }}
                >
                  <td
                    className="px-3 text-sm text-[#e2e6f0] max-w-0 truncate"
                    title={job.source_path}
                  >
                    {/* Use series_id as series identifier until series title is available */}
                    {job.series_id != null ? `Series ${job.series_id}` : "—"}
                  </td>
                  <td className="px-3 text-sm text-[#e2e6f0]">
                    {job.episode_key || "—"}
                  </td>
                  <td
                    className="px-3 text-sm text-[#e2e6f0] max-w-0 truncate"
                    title={job.source_path}
                  >
                    {basename(job.source_path)}
                  </td>
                  <td className="px-3">
                    <StatusBadge status={job.status as JobStatus} />
                  </td>
                  <td className="px-3 text-sm text-[#6b7280]">
                    {relativeTime(job.enqueued_at)}
                  </td>
                  <td className="px-3 text-right">
                    <button
                      type="button"
                      onClick={() => navigate(`/jobs/${job.id}/logs`)}
                      className="inline-flex items-center justify-center w-8 h-8 text-[#6b7280] hover:text-accent focus:outline-[#3b82f6] focus:outline-2 focus:outline-offset-2 rounded transition-colors duration-150"
                      aria-label={`View logs for job ${job.id}`}
                    >
                      <FileText size={15} aria-hidden="true" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ── History table ─────────────────────────────────────────────────────────────

interface HistoryTableProps {
  jobs: HistoryRow[];
  lastUpdated?: string;
  onToast: (toast: Omit<ToastState, "id">) => void;
  onRefresh?: () => void;
}

export function HistoryTable({
  jobs,
  lastUpdated,
  onToast,
  onRefresh,
}: HistoryTableProps) {
  const navigate = useNavigate();

  return (
    <div>
      {lastUpdated && (
        <p className="text-xs text-[#6b7280] mb-2">
          Last updated {lastUpdated}
        </p>
      )}
      {jobs.length === 0 ? (
        <EmptyState
          heading="No history yet"
          body="Completed and failed jobs will appear here."
        />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full border-collapse">
            <thead>
              <tr className="h-10 border-b border-[#2d3148]">
                <th
                  scope="col"
                  className="text-left text-xs font-normal text-[#6b7280] uppercase px-3"
                  style={{ width: "22%" }}
                >
                  Series
                </th>
                <th
                  scope="col"
                  className="text-left text-xs font-normal text-[#6b7280] uppercase px-3"
                  style={{ width: "10%" }}
                >
                  Episode
                </th>
                <th
                  scope="col"
                  className="text-left text-xs font-normal text-[#6b7280] uppercase px-3"
                  style={{ width: "28%" }}
                >
                  File
                </th>
                <th
                  scope="col"
                  className="text-left text-xs font-normal text-[#6b7280] uppercase px-3"
                  style={{ width: "12%" }}
                >
                  Status
                </th>
                <th
                  scope="col"
                  className="text-left text-xs font-normal text-[#6b7280] uppercase px-3"
                  style={{ width: "10%" }}
                >
                  Finished
                </th>
                <th
                  scope="col"
                  className="text-left text-xs font-normal text-[#6b7280] uppercase px-3"
                  style={{ width: "10%" }}
                >
                  Reason
                </th>
                <th
                  scope="col"
                  className="text-right text-xs font-normal text-[#6b7280] uppercase px-3"
                  style={{ width: "8%" }}
                >
                  Actions
                </th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((job, idx) => (
                <tr
                  key={job.id}
                  className="h-10 hover:bg-[#22263a] transition-colors duration-150"
                  style={{
                    backgroundColor: idx % 2 === 1 ? "#1e2130" : undefined,
                  }}
                >
                  <td
                    className="px-3 text-sm text-[#e2e6f0] max-w-0 truncate"
                    title={job.source_path}
                  >
                    {job.series_id != null ? `Series ${job.series_id}` : "—"}
                  </td>
                  <td className="px-3 text-sm text-[#e2e6f0]">
                    {job.episode_key || "—"}
                  </td>
                  <td
                    className="px-3 text-sm text-[#e2e6f0] max-w-0 truncate"
                    title={job.source_path}
                  >
                    {basename(job.source_path)}
                  </td>
                  <td className="px-3">
                    <StatusBadge status={job.status as JobStatus} />
                  </td>
                  <td
                    className="px-3 text-sm text-[#6b7280]"
                    title={
                      job.finished_at
                        ? new Date(job.finished_at).toLocaleString()
                        : undefined
                    }
                  >
                    {relativeTime(job.finished_at)}
                  </td>
                  <td
                    className="px-3 text-xs text-[#6b7280] max-w-0 truncate"
                    title={job.error_reason ?? undefined}
                  >
                    {job.error_reason
                      ? job.error_reason.slice(0, 60)
                      : ""}
                  </td>
                  <td className="px-3 text-right">
                    <div className="inline-flex items-center gap-1 justify-end">
                      {(job.status === "failed" ||
                        job.status === "quarantined") && (
                        <RetryButton
                          jobId={job.id}
                          onToast={onToast}
                          onRetried={onRefresh}
                        />
                      )}
                      <button
                        type="button"
                        onClick={() => navigate(`/jobs/${job.id}/logs`)}
                        className="inline-flex items-center justify-center w-8 h-8 text-[#6b7280] hover:text-accent focus:outline-[#3b82f6] focus:outline-2 focus:outline-offset-2 rounded transition-colors duration-150"
                        aria-label={`View logs for job ${job.id}`}
                      >
                        <FileText size={15} aria-hidden="true" />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ── Empty state ───────────────────────────────────────────────────────────────

function EmptyState({ heading, body }: { heading: string; body: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-12 text-center">
      <p className="text-sm font-semibold text-[#6b7280]">{heading}</p>
      <p className="text-xs text-[#6b7280] mt-1 max-w-md">{body}</p>
    </div>
  );
}
