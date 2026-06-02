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

// ── Bible ─────────────────────────────────────────────────────────────────────

export interface SeriesListItem {
  id: number;
  arr_kind: string;
  arr_instance: string;
  arr_series_id: number;
  register: string | null; // alias="register" — NOT register_value
  locked_fields: string[];
}

export interface CharacterDTO {
  id: number;
  series_id: number;
  original_latin_name: string;
  gender: string | null;
  rough_age: string | null;
  role: string | null;
  locked_fields: string[];
}

export interface AddressMapDTO {
  id: number;
  series_id: number;
  speaker_character_id: number;
  addressee_character_id: number;
  self_term: string | null;
  address_term: string | null;
  valid_from_episode: string | null;
  locked_fields: string[];
}

export interface TermDTO {
  id: number;
  series_id: number;
  source_term: string;
  vietnamese_rendering: string;
  category: string | null;
  locked_fields: string[];
}

export interface BibleEventDTO {
  id: number;
  series_id: number;
  episode_key: string | null;
  entity_type: string;
  entity_id: number;
  field: string;
  old_value: unknown;
  new_value: unknown;
  source: "inference" | "lock" | "import" | "system";
  created_at: string | null;
}

export interface RelationshipEventDTO {
  id: number;
  series_id: number;
  character_a_id: number;
  character_b_id: number;
  episode_marker: string | null;
  description: string | null;
}

export interface SeriesBibleDTO {
  id: number;
  arr_kind: string;
  arr_instance: string;
  arr_series_id: number;
  register: string | null; // alias="register"
  arr_metadata: Record<string, unknown>;
  characters: CharacterDTO[];
  terms: TermDTO[];
  address_map: AddressMapDTO[];
  relationship_events: RelationshipEventDTO[];
  locked_fields: string[];
}

export interface PronounsResponse {
  self_terms: string[];
  address_terms: string[];
  kinship_reciprocal: Record<string, { self_term: string; address_term: string }>;
}

/** GET /api/series — list all series in the Bible. */
export async function getSeriesList(): Promise<SeriesListItem[]> {
  const resp = await fetchWithTimeout("/api/series");
  if (!resp.ok) throw new Error(`GET /api/series: ${resp.status}`);
  return resp.json();
}

/** GET /api/series/{id}/bible — load the full Bible for a series. */
export async function getSeriesBible(seriesId: number): Promise<SeriesBibleDTO> {
  const resp = await fetchWithTimeout(`/api/series/${seriesId}/bible`);
  if (!resp.ok) throw new Error(`GET /api/series/${seriesId}/bible: ${resp.status}`);
  return resp.json();
}

/** PATCH /api/series/{id}/characters/{cid} — edit/lock a character field. */
export async function patchCharacter(
  seriesId: number,
  charId: number,
  payload: { field: string; value: unknown; lock?: boolean },
): Promise<CharacterDTO> {
  const resp = await fetchWithTimeout(
    `/api/series/${seriesId}/characters/${charId}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
  if (!resp.ok) throw new Error(`PATCH character: ${resp.status}`);
  return resp.json();
}

/** PATCH /api/series/{id}/address-map/{aid} — edit/lock an address map pair. */
export async function patchAddressMapPair(
  seriesId: number,
  addressMapId: number,
  payload: { self_term?: string; address_term?: string; lock?: boolean },
): Promise<AddressMapDTO> {
  const resp = await fetchWithTimeout(
    `/api/series/${seriesId}/address-map/${addressMapId}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
  if (!resp.ok) throw new Error(`PATCH address-map pair: ${resp.status}`);
  return resp.json();
}

/** PATCH /api/series/{id}/register — edit/lock the series register. */
export async function patchRegister(
  seriesId: number,
  payload: { value: string; lock?: boolean },
): Promise<SeriesListItem> {
  const resp = await fetchWithTimeout(`/api/series/${seriesId}/register`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!resp.ok) throw new Error(`PATCH register: ${resp.status}`);
  return resp.json();
}

/** POST /api/series/{id}/characters — add a new character. */
export async function addCharacter(
  seriesId: number,
  payload: {
    original_latin_name: string;
    gender?: string;
    rough_age?: string;
    role?: string;
  },
): Promise<CharacterDTO> {
  const resp = await fetchWithTimeout(`/api/series/${seriesId}/characters`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!resp.ok) throw new Error(`POST character: ${resp.status}`);
  return resp.json();
}

/** POST /api/series/{id}/terms — add a new term. */
export async function addTerm(
  seriesId: number,
  payload: {
    source_term: string;
    vietnamese_rendering: string;
    category?: string;
  },
): Promise<TermDTO> {
  const resp = await fetchWithTimeout(`/api/series/${seriesId}/terms`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!resp.ok) throw new Error(`POST term: ${resp.status}`);
  return resp.json();
}

/** POST /api/series/{id}/address-map — add a new address map pair. */
export async function addAddressMapPair(
  seriesId: number,
  payload: {
    speaker_character_id: number;
    addressee_character_id: number;
    self_term: string;
    address_term: string;
  },
): Promise<AddressMapDTO> {
  const resp = await fetchWithTimeout(`/api/series/${seriesId}/address-map`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!resp.ok) throw new Error(`POST address-map pair: ${resp.status}`);
  return resp.json();
}

/** DELETE /api/series/{id}/terms/{tid} — delete a term by id. */
export async function deleteTerm(
  seriesId: number,
  termId: number,
): Promise<void> {
  const resp = await fetchWithTimeout(
    `/api/series/${seriesId}/terms/${termId}`,
    { method: "DELETE" },
  );
  if (!resp.ok) throw new Error(`DELETE term: ${resp.status}`);
}

/** DELETE /api/series/{id}/address-map/{aid} — delete an address map pair. */
export async function deleteAddressMapPair(
  seriesId: number,
  addressMapId: number,
): Promise<void> {
  const resp = await fetchWithTimeout(
    `/api/series/${seriesId}/address-map/${addressMapId}`,
    { method: "DELETE" },
  );
  if (!resp.ok) throw new Error(`DELETE address-map pair: ${resp.status}`);
}

/** GET /api/series/{id}/bible/{entityType}/{entityId}/history */
export async function getFieldHistory(
  seriesId: number,
  entityType: string,
  entityId: number,
  field?: string,
): Promise<BibleEventDTO[]> {
  const url =
    `/api/series/${seriesId}/bible/${entityType}/${entityId}/history` +
    (field ? `?field=${encodeURIComponent(field)}` : "");
  const resp = await fetchWithTimeout(url);
  if (!resp.ok) throw new Error(`GET field history: ${resp.status}`);
  return resp.json();
}

/** GET /api/pronouns — fetch KNOWN_PRONOUN_TERMS + KINSHIP_RECIPROCAL. */
export async function getPronouns(): Promise<PronounsResponse> {
  const resp = await fetchWithTimeout("/api/pronouns");
  if (!resp.ok) throw new Error(`GET /api/pronouns: ${resp.status}`);
  return resp.json();
}
