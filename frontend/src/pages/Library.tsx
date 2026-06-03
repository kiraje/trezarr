/**
 * Library page — browse Sonarr series + Radarr movies, drill into episodes,
 * and trigger a single-item manual translation.
 *
 * Top-level view:
 *   - Series table (click to drill in)
 *   - Movies table with per-row Translate button (enabled when source_sub_found)
 *
 * Episode drill-in:
 *   - Back button → top-level
 *   - Episode table with status pills + Translate button (has_source only)
 *   - Translate → POST /api/translate → navigate to /queue
 */
import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Tv, Film } from "lucide-react";
import {
  getLibrary,
  getSeriesEpisodes,
  postTranslate,
  type LibraryResponse,
  type LibrarySeriesItem,
  type LibraryMovieItem,
  type EpisodeRow,
} from "../api/client";

// ── Status pill ───────────────────────────────────────────────────────────────

function StatusPill({ status }: { status: EpisodeRow["status"] }) {
  if (status === "translated") {
    return (
      <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-[#166534] text-[#4ade80]">
        Translated
      </span>
    );
  }
  if (status === "has_source") {
    return (
      <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-[#1e3a5f] text-[#60a5fa]">
        Has source
      </span>
    );
  }
  return (
    <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-[#374151] text-[#9ca3af]">
      No source
    </span>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function Library() {
  const navigate = useNavigate();

  const [libraryData, setLibraryData] = useState<LibraryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [selectedSeries, setSelectedSeries] = useState<LibrarySeriesItem | null>(null);
  const [episodes, setEpisodes] = useState<EpisodeRow[] | null>(null);
  const [episodesLoading, setEpisodesLoading] = useState(false);
  const [episodesError, setEpisodesError] = useState<string | null>(null);

  const [translatePending, setTranslatePending] = useState<string | null>(null);

  // Load top-level library
  useEffect(() => {
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const data = await getLibrary();
        setLibraryData(data);
      } catch (err) {
        setError(String(err));
      } finally {
        setLoading(false);
      }
    }
    void load();
  }, []);

  // Load episodes when a series is selected
  useEffect(() => {
    if (!selectedSeries) {
      setEpisodes(null);
      return;
    }
    async function loadEpisodes() {
      setEpisodesLoading(true);
      setEpisodesError(null);
      try {
        const rows = await getSeriesEpisodes(selectedSeries!.id);
        setEpisodes(rows);
      } catch (err) {
        setEpisodesError(String(err));
        setEpisodes([]);
      } finally {
        setEpisodesLoading(false);
      }
    }
    void loadEpisodes();
  }, [selectedSeries]);

  async function handleTranslate(
    kind: "series" | "movie",
    arrSeriesId: number | null,
    sourcePath: string,
  ) {
    setTranslatePending(sourcePath);
    try {
      await postTranslate(kind, arrSeriesId, sourcePath);
      navigate("/queue");
    } catch (err) {
      // Best-effort — still navigate so user can see queue state
      console.error("postTranslate error:", err);
      navigate("/queue");
    } finally {
      setTranslatePending(null);
    }
  }

  // ── Episode drill-in view ───────────────────────────────────────────────────
  if (selectedSeries) {
    return (
      <div>
        <div className="flex items-center gap-3 mb-6">
          <button
            type="button"
            onClick={() => setSelectedSeries(null)}
            className="text-sm text-[#60a5fa] hover:text-[#93c5fd] transition-colors"
          >
            ← Back
          </button>
          <h2 className="text-lg font-semibold text-[#e2e6f0]">
            {selectedSeries.title}
          </h2>
        </div>

        {episodesLoading && (
          <p className="text-sm text-[#6b7280]">Loading episodes…</p>
        )}

        {episodesError && (
          <div className="mb-4 px-4 py-3 text-sm rounded bg-[#451a03] text-[#fbbf24]">
            {episodesError}
          </div>
        )}

        {episodes && episodes.length === 0 && !episodesLoading && (
          <p className="text-sm text-[#6b7280]">No episode files found for this series.</p>
        )}

        {episodes && episodes.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm text-left">
              <thead>
                <tr className="border-b border-[#2d3148] text-[#6b7280] text-xs uppercase tracking-wider">
                  <th className="pb-2 pr-4">Episode</th>
                  <th className="pb-2 pr-4">Title</th>
                  <th className="pb-2 pr-4">Status</th>
                  <th className="pb-2">Action</th>
                </tr>
              </thead>
              <tbody>
                {episodes.map((row, idx) => (
                  <tr
                    key={row.episode_key + row.local_path}
                    className={[
                      "border-b border-[#2d3148]",
                      idx % 2 === 1 ? "bg-[#1e2130]" : "",
                    ].join(" ")}
                  >
                    <td className="py-2 pr-4 text-[#e2e6f0] font-mono text-xs whitespace-nowrap">
                      {row.episode_key || "—"}
                    </td>
                    <td className="py-2 pr-4 text-[#e2e6f0] max-w-xs truncate">
                      {row.title || "—"}
                    </td>
                    <td className="py-2 pr-4">
                      <StatusPill status={row.status} />
                    </td>
                    <td className="py-2">
                      <button
                        type="button"
                        disabled={
                          row.status !== "has_source" ||
                          translatePending === row.source_path
                        }
                        onClick={() => {
                          if (row.source_path) {
                            void handleTranslate("series", selectedSeries.id, row.source_path);
                          }
                        }}
                        className="px-3 py-1 text-xs rounded bg-[#3b82f6] text-white hover:bg-[#2563eb] disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                      >
                        {translatePending === row.source_path ? "Queuing…" : "Translate"}
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

  // ── Top-level library view ──────────────────────────────────────────────────
  return (
    <div>
      <h2 className="text-lg font-semibold text-[#e2e6f0] mb-6">Library</h2>

      {loading && <p className="text-sm text-[#6b7280]">Loading library…</p>}

      {error && (
        <div className="mb-4 px-4 py-3 text-sm rounded bg-[#451a03] text-[#fbbf24]">
          {error}
        </div>
      )}

      {libraryData && libraryData.errors.length > 0 && (
        <div className="mb-4 flex flex-col gap-2">
          {libraryData.errors.map((e) => (
            <div
              key={e.source}
              className="px-4 py-2 text-xs rounded bg-[#451a03] text-[#fbbf24]"
            >
              <span className="font-semibold capitalize">{e.source}</span>: {e.error}
            </div>
          ))}
        </div>
      )}

      {/* Series section */}
      {libraryData && libraryData.series.length > 0 && (
        <div className="mb-8">
          <div className="flex items-center gap-2 mb-3">
            <Tv size={16} className="text-[#6b7280]" />
            <h3 className="text-sm font-semibold text-[#e2e6f0]">Series</h3>
            <span className="text-xs text-[#6b7280]">({libraryData.series.length})</span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm text-left">
              <thead>
                <tr className="border-b border-[#2d3148] text-[#6b7280] text-xs uppercase tracking-wider">
                  <th className="pb-2 pr-4">Title</th>
                  <th className="pb-2 pr-4">Year</th>
                  <th className="pb-2">Monitored</th>
                </tr>
              </thead>
              <tbody>
                {libraryData.series.map((s, idx) => (
                  <tr
                    key={s.id}
                    className={[
                      "border-b border-[#2d3148] cursor-pointer transition-colors",
                      idx % 2 === 1 ? "bg-[#1e2130]" : "",
                      "hover:bg-[#1e2130]",
                    ].join(" ")}
                    onClick={() => setSelectedSeries(s)}
                  >
                    <td className="py-2 pr-4 text-[#e2e6f0]">{s.title}</td>
                    <td className="py-2 pr-4 text-[#6b7280]">{s.year ?? "—"}</td>
                    <td className="py-2 text-[#6b7280]">
                      {s.monitored ? "Yes" : "No"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Movies section */}
      {libraryData && libraryData.movies.length > 0 && (
        <div>
          <div className="flex items-center gap-2 mb-3">
            <Film size={16} className="text-[#6b7280]" />
            <h3 className="text-sm font-semibold text-[#e2e6f0]">Movies</h3>
            <span className="text-xs text-[#6b7280]">({libraryData.movies.length})</span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm text-left">
              <thead>
                <tr className="border-b border-[#2d3148] text-[#6b7280] text-xs uppercase tracking-wider">
                  <th className="pb-2 pr-4">Title</th>
                  <th className="pb-2 pr-4">Year</th>
                  <th className="pb-2 pr-4">Monitored</th>
                  <th className="pb-2">Action</th>
                </tr>
              </thead>
              <tbody>
                {libraryData.movies.map((m: LibraryMovieItem, idx) => (
                  <tr
                    key={m.id}
                    className={[
                      "border-b border-[#2d3148]",
                      idx % 2 === 1 ? "bg-[#1e2130]" : "",
                    ].join(" ")}
                  >
                    <td className="py-2 pr-4 text-[#e2e6f0]">{m.title}</td>
                    <td className="py-2 pr-4 text-[#6b7280]">{m.year ?? "—"}</td>
                    <td className="py-2 pr-4 text-[#6b7280]">
                      {m.monitored ? "Yes" : "No"}
                    </td>
                    <td className="py-2">
                      {/* Movies don't have a source_path resolved here — the
                          Library endpoint would need to return it. For now the
                          Translate button signals "no source" when unavailable. */}
                      <button
                        type="button"
                        disabled={!m.source_sub_found}
                        className="px-3 py-1 text-xs rounded bg-[#3b82f6] text-white hover:bg-[#2563eb] disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                        title={!m.source_sub_found ? "No source subtitle found" : undefined}
                      >
                        Translate
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {libraryData &&
        libraryData.series.length === 0 &&
        libraryData.movies.length === 0 &&
        !loading && (
          <p className="text-sm text-[#6b7280]">
            No items found. Check that Sonarr and/or Radarr are enabled and connected in Settings.
          </p>
        )}
    </div>
  );
}
