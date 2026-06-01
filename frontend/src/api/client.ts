/**
 * Typed fetch wrappers for all Trezarr REST endpoints.
 *
 * All wrappers use a 5-second AbortController timeout. On network error or
 * timeout, they throw — callers should catch and render the API-unreachable
 * banner per 07-UI-SPEC §Interaction & State Contracts.
 *
 * No axios — native fetch ships with every browser React 19 targets.
 */

const TIMEOUT_MS = 5000;

/** Execute a fetch with a 5-second timeout. Throws on timeout or network error. */
async function fetchWithTimeout(
  url: string,
  options?: RequestInit,
): Promise<Response> {
  const controller = new AbortController();
  const id = setTimeout(() => controller.abort(), TIMEOUT_MS);
  try {
    const resp = await fetch(url, { ...options, signal: controller.signal });
    return resp;
  } finally {
    clearTimeout(id);
  }
}

// ── Settings ─────────────────────────────────────────────────────────────────

export interface SettingsResponse {
  [key: string]: unknown;
}

export interface EnvLockedResponse {
  env_locked: string[];
}

/** GET /api/settings — returns all settings; secret fields are masked. */
export async function getSettings(): Promise<SettingsResponse> {
  const resp = await fetchWithTimeout("/api/settings");
  if (!resp.ok) throw new Error(`GET /api/settings: ${resp.status}`);
  return resp.json();
}

/** PUT /api/settings — persist a patch of settings values. */
export async function putSettings(
  patch: Record<string, unknown>,
): Promise<{ ok: boolean; restart_required: string[]; persisted: boolean }> {
  const resp = await fetchWithTimeout("/api/settings", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
  if (!resp.ok) throw new Error(`PUT /api/settings: ${resp.status}`);
  return resp.json();
}

/** GET /api/settings/env-locked — returns field names set via environment variables. */
export async function getEnvLocked(): Promise<EnvLockedResponse> {
  const resp = await fetchWithTimeout("/api/settings/env-locked");
  if (!resp.ok) throw new Error(`GET /api/settings/env-locked: ${resp.status}`);
  return resp.json();
}

/** POST /api/test/{svc} — run a connection test for a service. */
export async function testConnection(
  svc: string,
  params: Record<string, unknown>,
): Promise<{ ok: boolean; error?: string; version?: string }> {
  const resp = await fetchWithTimeout(`/api/test/${svc}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
  if (!resp.ok) throw new Error(`POST /api/test/${svc}: ${resp.status}`);
  return resp.json();
}

// ── Queue & History ───────────────────────────────────────────────────────────

export interface QueueJob {
  id: number;
  source_path: string;
  series_id: number | null;
  status: "queued" | "running";
  enqueued_at: string | null;
  started_at: string | null;
  episode_key: string;
}

export interface HistoryJob {
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

/** GET /api/queue — returns in-flight jobs (status=queued or running). */
export async function getQueue(): Promise<QueueJob[]> {
  const resp = await fetchWithTimeout("/api/queue");
  if (!resp.ok) throw new Error(`GET /api/queue: ${resp.status}`);
  return resp.json();
}

/** GET /api/jobs — returns historical jobs (status=done, failed, quarantined). */
export async function getJobs(): Promise<HistoryJob[]> {
  const resp = await fetchWithTimeout("/api/jobs");
  if (!resp.ok) throw new Error(`GET /api/jobs: ${resp.status}`);
  return resp.json();
}

// ── Per-job Logs ──────────────────────────────────────────────────────────────

export interface JobLogEntry {
  id: number;
  level: string;
  message: string;
  created_at: string | null;
}

/** GET /api/jobs/{id}/logs — returns per-job log entries. */
export async function getJobLogs(id: number): Promise<JobLogEntry[]> {
  const resp = await fetchWithTimeout(`/api/jobs/${id}/logs`);
  if (!resp.ok) throw new Error(`GET /api/jobs/${id}/logs: ${resp.status}`);
  return resp.json();
}

// ── Retry ─────────────────────────────────────────────────────────────────────

export interface RetryResponse {
  ok: boolean;
  job_id: number;
}

/** POST /api/jobs/{id}/retry — re-enqueue a failed or quarantined job. */
export async function retryJob(id: number): Promise<RetryResponse> {
  const resp = await fetchWithTimeout(`/api/jobs/${id}/retry`, {
    method: "POST",
  });
  if (!resp.ok) throw new Error(`POST /api/jobs/${id}/retry: ${resp.status}`);
  return resp.json();
}
