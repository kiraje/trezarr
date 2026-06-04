/**
 * LibraryContext — shared GET /api/library data for series/movies pages + sidebar.
 *
 * Design decisions (14-CONTEXT.md D-09, D-10):
 *
 * D-09 Count badge derivation:
 *   Series count = series.filter(s => s.translated_count < s.total_count).length
 *   Movies count = movies.filter(m => m.translated_count < m.total_count).length
 *   Uses translated_count < total_count as a proxy for "needs VI translation".
 *   This is a documented approximation (not per-episode source-sub check) — intentional.
 *
 * D-10 LIVE badge derivation (W1 — uses the positive services.* enabled flag):
 *   Sonarr LIVE = data.services?.sonarr === true && no "sonarr" error in errors[]
 *   Radarr LIVE = data.services?.radarr === true && no "radarr" error in errors[]
 *   A DISABLED service (services.<svc> !== true) is NOT live — this fixes the
 *   prior false-positive where a disabled service (empty list + no error) showed
 *   a green LIVE badge. An ENABLED-but-erroring service is also not live.
 *
 * Data sharing strategy: Series/Movies pages call setLibraryData after their fetch.
 * The sidebar reads counts + LIVE state from context without making its own request.
 * When no library page has loaded yet, libraryData is null → badges hidden (correct).
 */
import React from "react";
import type { LibraryResponse } from "../api/client";

// ── Context value type ────────────────────────────────────────────────────────

export interface LibraryContextValue {
  libraryData: LibraryResponse | null;
  setLibraryData: (data: LibraryResponse) => void;
}

// ── Context creation ──────────────────────────────────────────────────────────

const LibraryContext = React.createContext<LibraryContextValue | null>(null);

// ── Provider ──────────────────────────────────────────────────────────────────

export function LibraryProvider({ children }: { children: React.ReactNode }) {
  const [libraryData, setLibraryData] = React.useState<LibraryResponse | null>(null);

  const value = React.useMemo<LibraryContextValue>(
    () => ({ libraryData, setLibraryData }),
    [libraryData],
  );

  return (
    <LibraryContext.Provider value={value}>{children}</LibraryContext.Provider>
  );
}

export default LibraryProvider;

// ── Hook ──────────────────────────────────────────────────────────────────────

/**
 * Access the shared library context.
 * Throws if called outside a LibraryProvider — catches missing provider early.
 */
export function useLibraryContext(): LibraryContextValue {
  const ctx = React.useContext(LibraryContext);
  if (ctx === null) {
    throw new Error("useLibraryContext must be used inside LibraryProvider");
  }
  return ctx;
}

// ── Derived helpers (used by app-sidebar.tsx for badge data) ──────────────────

/**
 * Returns true when Sonarr is live (W1 rule).
 * Concrete rule: Sonarr is enabled (services.sonarr === true) AND has no error.
 * A disabled service is not live (was a false-positive under the old rule).
 */
export function getSeriesLiveBadge(data: LibraryResponse | null): boolean {
  if (data === null) return false;
  return data.services?.sonarr === true && !data.errors.some((e) => e.source === "sonarr");
}

/**
 * Returns true when Radarr is live (W1 rule).
 * Concrete rule: Radarr is enabled (services.radarr === true) AND has no error.
 */
export function getMoviesLiveBadge(data: LibraryResponse | null): boolean {
  if (data === null) return false;
  return data.services?.radarr === true && !data.errors.some((e) => e.source === "radarr");
}

/**
 * Number of series that need Vietnamese translation (D-09 proxy count).
 * Auto-hides at zero in the sidebar (render nothing, not a "0" badge).
 */
export function getSeriesNeedsViCount(data: LibraryResponse | null): number {
  return data?.series.filter((s) => s.translated_count < s.total_count).length ?? 0;
}

/**
 * Number of movies that need Vietnamese translation (D-09 proxy count).
 * Auto-hides at zero in the sidebar.
 */
export function getMoviesNeedsViCount(data: LibraryResponse | null): number {
  return data?.movies.filter((m) => m.translated_count < m.total_count).length ?? 0;
}
