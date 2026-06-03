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
const LONG_TIMEOUT_MS = 30000;

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

/** Execute a fetch with a 30-second timeout. Used for library endpoints that
 * may need to query live *arr APIs. */
async function fetchWithLongTimeout(
  url: string,
  options?: RequestInit,
): Promise<Response> {
  const controller = new AbortController();
  const id = setTimeout(() => controller.abort(), LONG_TIMEOUT_MS);
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

/**
 * Strip the `${svc}_` prefix from connection-test param keys.
 *
 * The Settings UI stores each section's form state under UI-prefixed keys
 * (e.g. `llm_base_url`, `sonarr_host`, `bazarr_api_key`) so the section hooks
 * stay distinct. The backend `/api/test/{svc}` Pydantic models, however, expect
 * UNPREFIXED field names (`base_url`/`model`/`api_key` for llm;
 * `host`/`port`/`api_key` for the *arr services).
 *
 * Posting the raw prefixed object produced HTTP 422 (every field "missing")
 * before any connection was attempted — see debug session
 * `llm-test-connection-422`. This mapping bridges the two naming schemes for all
 * four service test buttons in one place.
 */
export function stripSvcPrefix(
  svc: string,
  params: Record<string, unknown>,
): Record<string, unknown> {
  const prefix = `${svc}_`;
  const out: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(params)) {
    const mapped = key.startsWith(prefix) ? key.slice(prefix.length) : key;
    out[mapped] = value;
  }
  return out;
}

/** POST /api/test/{svc} — run a connection test for a service. */
export async function testConnection(
  svc: string,
  params: Record<string, unknown>,
): Promise<{ ok: boolean; error?: string; version?: string }> {
  const resp = await fetchWithTimeout(`/api/test/${svc}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(stripSvcPrefix(svc, params)),
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
  source_lang_override: string[] | null;
  model_override: string | null;
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
  source_lang_override: string[] | null;
  model_override: string | null;
}

export interface SeriesOverridesRequest {
  source_lang_override: string[] | null; // null = clear / inherit global
  model_override: string | null; // null = clear / inherit global
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

/** PATCH /api/bible/series/{id}/overrides — set source-priority and model overrides. */
export async function patchSeriesOverrides(
  seriesId: number,
  payload: SeriesOverridesRequest,
): Promise<SeriesBibleDTO> {
  const resp = await fetchWithTimeout(
    `/api/bible/series/${seriesId}/overrides`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
  if (!resp.ok) throw new Error(`PATCH overrides: ${resp.status}`);
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

// ── Library ───────────────────────────────────────────────────────────────────

// ── Phase-13 API types (D-01/D-02/D-03 per 14-01-PLAN.md) ───────────────────

/** Series row from GET /api/library — mirrors library.py SeriesItem shape exactly. */
export interface SeriesItem {
  kind: "series";
  id: number;
  title: string;
  year: number | null;
  monitored: boolean;
  poster_url: string | null;
  /** Episodes with a VI sidecar file (ledger count, D-05 bulk query). */
  translated_count: number;
  /** episodeFileCount from Sonarr statistics (D-04). */
  total_count: number;
}

/** Movie row from GET /api/library — mirrors library.py MovieItem shape exactly. */
export interface MovieItem {
  kind: "movie";
  id: number;
  title: string;
  year: number | null;
  monitored: boolean;
  poster_url: string | null;
  source_sub_found: boolean;
  /** 1 if vi sidecar exists, 0 otherwise. */
  translated_count: number;
  /** 1 if hasFile, 0 otherwise. */
  total_count: number;
}

/** Response from GET /api/library. */
export interface LibraryResponse {
  series: SeriesItem[];
  movies: MovieItem[];
  errors: Array<{ source: string; error: string }>;
}

/** One subtitle track entry from Bazarr (D-02 — path field intentionally absent). */
export interface SubtitleEntry {
  code2: string;
  code3: string;
  hi: boolean;
  forced: boolean;
}

/** One episode row from GET /api/library/series/:id/episodes — Phase-13 shape. */
export interface EpisodeEnrichedRow {
  episode_id: number | null;
  episode_file_id: number | null;
  season_number: number;
  episode_number: number;
  /** "S01E01" format, built from authoritative Sonarr episode-record ints (D-03). */
  episode_key: string;
  title: string;
  monitored: boolean;
  has_file: boolean;
  local_path: string | null;
  source_path: string | null;
  source_lang: string | null;
  status: "nothing" | "has_source" | "translated";
  /** ISO-639-1 code2 list, e.g. ["ko", "en"] (D-07). */
  audio_languages: string[];
  subtitles: SubtitleEntry[];
}

/** Season group within a SeriesEpisodesResponse. */
export interface SeasonGroup {
  season_number: number;
  episodes: EpisodeEnrichedRow[];
}

/** Response envelope from GET /api/library/series/:id/episodes (Phase-13). */
export interface SeriesEpisodesResponse {
  series_id: number;
  /** False when Bazarr is disabled or errored — subtitle column suppressed (D-05/D-08). */
  bazarr_available: boolean;
  seasons: SeasonGroup[];
  errors: Array<{ source: string; error: string }>;
}

/** Request body for POST /api/translate. */
export interface TranslateRequest {
  kind: "series" | "movie";
  source_path: string;
  arr_series_id?: number;
}

export interface TranslateResponse {
  enqueued: boolean;
  source_path: string;
}

// ── Fetch wrappers ────────────────────────────────────────────────────────────

/** GET /api/library — list Sonarr series and Radarr movies. */
export async function getLibrary(): Promise<LibraryResponse> {
  const resp = await fetchWithLongTimeout("/api/library");
  if (!resp.ok) throw new Error(`GET /api/library: ${resp.status}`);
  return resp.json();
}

/** GET /api/library/series/{id}/episodes — season-grouped episode records for one series. */
export async function getSeriesEpisodes(id: number): Promise<SeriesEpisodesResponse> {
  const resp = await fetchWithLongTimeout(`/api/library/series/${id}/episodes`);
  if (!resp.ok) throw new Error(`GET /api/library/series/${id}/episodes: ${resp.status}`);
  return resp.json();
}

/** POST /api/translate — enqueue a single item for manual translation. */
export async function postTranslate(
  kind: "series" | "movie",
  arrSeriesId: number | null,
  sourcePath: string,
): Promise<TranslateResponse> {
  const resp = await fetchWithLongTimeout("/api/translate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ kind, arr_series_id: arrSeriesId, source_path: sourcePath }),
  });
  if (!resp.ok) throw new Error(`POST /api/translate: ${resp.status}`);
  return resp.json();
}
