/**
 * SeriesDetail page — per-series episode browser with season Accordion, audio/subtitle
 * badges, and Translate actions.
 *
 * Implements: LIB-03 (season Accordion + states), LIB-04 (audio+subtitle badges),
 * LIB-05 (Translate episode + season → POST /api/translate → navigate('/queue')).
 *
 * Design decisions:
 *  - D-05: seasons sorted ascending, Season 0 last; latest non-zero season auto-expanded
 *  - D-05: bazarr_available=false → subtitle column completely removed (no header, no cells)
 *  - D-08: Translate episode + season handlers call postTranslate then navigate('/queue')
 *  - IN-01 carry-forward: useParams typed; guard runs AFTER all hooks (React hooks rules)
 *  - T-14-05-01: seriesId validated with parseInt+isNaN before any API call; never injected
 *    into innerHTML
 */
import { useState, useEffect, useRef } from "react";
import { useParams, useNavigate } from "react-router-dom";

import {
  getSeriesEpisodes,
  postTranslate,
  type SeriesEpisodesResponse,
  type SeasonGroup,
  type EpisodeEnrichedRow,
} from "../api/client";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "../components/ui/accordion";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Skeleton } from "../components/ui/skeleton";
import { SubtitleBadge } from "../components/SubtitleBadge";

// ---------------------------------------------------------------------------
// EpisodeTable — inline component; keeps SeriesDetail file self-contained.
// ---------------------------------------------------------------------------

interface EpisodeTableProps {
  episodes: EpisodeEnrichedRow[];
  bazarrAvailable: boolean;
  translateErrors: Record<string, string>;
  onTranslate: (episode: EpisodeEnrichedRow) => void;
}

function EpisodeTable({
  episodes,
  bazarrAvailable,
  translateErrors,
  onTranslate,
}: EpisodeTableProps) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b text-muted-foreground">
            <th className="py-2 px-4 text-left font-normal w-[60px]">#</th>
            <th className="py-2 px-4 text-left font-normal">Title</th>
            <th className="py-2 px-4 text-left font-normal">Audio</th>
            {/* D-05 / bazarr_available suppression: Subtitles column header absent when false */}
            {bazarrAvailable && (
              <th className="py-2 px-4 text-left font-normal">Subtitles</th>
            )}
            <th className="py-2 px-4 text-left font-normal w-[110px]">Action</th>
          </tr>
        </thead>
        <tbody>
          {episodes.map((episode) => {
            const isFileMissing = !episode.has_file;

            return (
              <tr
                key={episode.episode_key}
                className={`border-b last:border-0 ${isFileMissing ? "opacity-50" : "hover:bg-accent/50"}`}
              >
                {/* # column */}
                <td className="py-2 px-4 font-mono text-xs text-muted-foreground">
                  {episode.episode_key}
                </td>

                {/* Title column */}
                <td className="py-2 px-4">{episode.title}</td>

                {/* Audio badges column — absent when no file */}
                <td className="py-2 px-4">
                  {!isFileMissing && (
                    <div className="flex flex-wrap gap-1">
                      {episode.audio_languages.map((lang, idx) => (
                        <SubtitleBadge key={`${lang}-${idx}`} code2={lang} type="audio" />
                      ))}
                    </div>
                  )}
                </td>

                {/* Subtitles column — completely absent when bazarrAvailable === false (D-05) */}
                {bazarrAvailable && (
                  <td className="py-2 px-4">
                    {!isFileMissing && (
                      <div className="flex flex-wrap gap-1">
                        {episode.subtitles.map((sub, idx) => {
                          const subType =
                            sub.code2.toLowerCase() === "vi" ? "vi" : "source";
                          return (
                            <SubtitleBadge
                              key={`${sub.code2}-${idx}`}
                              code2={sub.code2}
                              hi={sub.hi}
                              forced={sub.forced}
                              type={subType}
                            />
                          );
                        })}
                      </div>
                    )}
                  </td>
                )}

                {/* Action column */}
                <td className="py-2 px-4">
                  {!isFileMissing && (
                    <>
                      {episode.status === "translated" ? (
                        <Badge className="bg-emerald-600/80 text-white border-transparent text-xs">
                          Translated
                        </Badge>
                      ) : episode.source_path !== null ? (
                        <div>
                          <Button
                            size="sm"
                            onClick={() => onTranslate(episode)}
                            className="min-h-[44px]"
                          >
                            Translate
                          </Button>
                          {translateErrors[episode.episode_key] && (
                            <span className="text-destructive text-xs block mt-1">
                              {translateErrors[episode.episode_key]}
                            </span>
                          )}
                        </div>
                      ) : null}
                    </>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// ---------------------------------------------------------------------------
// SeriesDetail — main page component
// ---------------------------------------------------------------------------

export default function SeriesDetail() {
  // --- All hooks called unconditionally first (React hooks rules / IN-01) ---
  const { seriesId } = useParams<{ seriesId: string }>();
  const navigate = useNavigate();

  // Derive numericId from param (NaN when absent or non-numeric)
  const numericId = seriesId ? parseInt(seriesId, 10) : NaN;

  const [data, setData] = useState<SeriesEpisodesResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [errorStatus, setErrorStatus] = useState<number | null>(null);
  const [translateErrors, setTranslateErrors] = useState<
    Record<string, string>
  >({});

  // WR-02: mount flag so the inline Retry handler has a consistent guard.
  const mountedRef = useRef(true);
  useEffect(() => () => { mountedRef.current = false; }, []);

  useEffect(() => {
    // Guard: skip fetch if ID is invalid (guard rendered below after hooks)
    if (isNaN(numericId)) {
      setLoading(false);
      return;
    }

    let cancelled = false;

    async function load() {
      setLoading(true);
      setError(null);
      setErrorStatus(null);

      try {
        const result = await getSeriesEpisodes(numericId);
        if (!cancelled) setData(result);
      } catch (err) {
        if (cancelled) return;
        const msg = String(err);
        // Detect HTTP status from error message text thrown by getSeriesEpisodes
        if (msg.includes(" 400")) setErrorStatus(400);
        // WR-04: 502 was tracked but never rendered; dropped — falls through to generic error UI
        setError(msg);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void load();

    return () => {
      cancelled = true;
    };
  }, [numericId]);

  // --- Guard AFTER all hooks (IN-01 pattern) ---
  if (!seriesId || isNaN(numericId)) {
    return (
      <div className="p-4 text-muted-foreground">Invalid series ID</div>
    );
  }

  // --- Season ordering (D-05) ---
  // Sorted ascending; Season 0 always last
  const sortedSeasons = [...(data?.seasons ?? [])].sort((a, b) => {
    if (a.season_number === 0) return 1;
    if (b.season_number === 0) return -1;
    return a.season_number - b.season_number;
  });

  // Latest non-zero season auto-expanded
  const latestSeason = sortedSeasons.filter((s) => s.season_number > 0).at(-1);
  const defaultValue: string[] = latestSeason
    ? [`season-${latestSeason.season_number}`]
    : sortedSeasons.length > 0
      ? [`season-${sortedSeasons[0].season_number}`]
      : [];

  // --- Translate handlers ---
  async function handleTranslateEpisode(episode: EpisodeEnrichedRow) {
    if (!episode.source_path) return;
    const key = episode.episode_key;
    // Clear previous error for this episode
    setTranslateErrors((prev) => {
      const next = { ...prev };
      delete next[key];
      return next;
    });
    try {
      await postTranslate("series", numericId, episode.source_path);
      navigate("/queue");
    } catch {
      setTranslateErrors((prev) => ({
        ...prev,
        [key]: "Could not enqueue. Check source file exists.",
      }));
    }
  }

  async function handleTranslateSeason(season: SeasonGroup) {
    const eligible = season.episodes.filter(
      (e) => e.has_file && e.source_path !== null && e.status !== "translated",
    );
    let enqueued = 0;
    const failures: string[] = [];
    for (const ep of eligible) {
      if (!ep.source_path) continue;
      try {
        await postTranslate("series", numericId, ep.source_path);
        enqueued = enqueued + 1;
      } catch {
        failures.push(ep.episode_key);
      }
    }
    // WR-05: only navigate when at least one enqueue succeeded; otherwise
    // surface failures inline so the user is not silently redirected to an
    // empty Queue page.
    if (enqueued > 0) {
      navigate("/queue");
    } else {
      setTranslateErrors(
        Object.fromEntries(failures.map((k) => [k, "Could not enqueue."])),
      );
    }
  }

  // --- Render: loading state ---
  if (loading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-48 mb-4" />
        <Skeleton className="h-12 w-full mb-2" />
        <Skeleton className="h-12 w-full mb-2" />
        <Skeleton className="h-12 w-full mb-2" />
      </div>
    );
  }

  // --- Render: error states ---
  if (error) {
    if (errorStatus === 400) {
      return (
        <div className="space-y-3">
          <h1 className="text-xl font-semibold">Sonarr is disabled</h1>
          <p className="text-muted-foreground">
            Enable Sonarr in Settings to view episode detail.
          </p>
          <Button variant="outline" onClick={() => navigate("/settings")}>
            Go to Settings
          </Button>
        </div>
      );
    }

    return (
      <div className="space-y-3">
        <h1 className="text-xl font-semibold">Could not load episodes</h1>
        <p className="text-muted-foreground">
          Sonarr returned an error. The series may still be loading.
        </p>
        <div className="flex gap-2">
          <Button
            onClick={async () => {
              // WR-02: use mountedRef so state updates are guarded after unmount
              setError(null);
              setErrorStatus(null);
              setLoading(true);
              try {
                const result = await getSeriesEpisodes(numericId);
                if (!mountedRef.current) return;
                setData(result);
                setLoading(false);
              } catch (err: unknown) {
                if (!mountedRef.current) return;
                const msg = String(err);
                if (msg.includes(" 400")) setErrorStatus(400);
                // WR-04: 502 dropped — falls through to generic error UI
                setError(msg);
                setLoading(false);
              }
            }}
          >
            Retry
          </Button>
          <Button variant="ghost" onClick={() => navigate("/series")}>
            Back to Series
          </Button>
        </div>
      </div>
    );
  }

  // --- Render: normal state ---
  return (
    <div className="space-y-4">
      {/* Page header */}
      <div>
        <h1 className="text-xl font-semibold">
          {data?.series_title ?? `Series #${numericId}`}
        </h1>
        {data?.bazarr_available === false && (
          <p className="text-sm text-amber-500 mt-1">
            Bazarr unavailable — subtitle data suppressed
          </p>
        )}
        {(data?.errors ?? []).map((e) => (
          <p key={e.source} className="text-xs text-muted-foreground mt-0.5">
            Bazarr error: {e.error}
          </p>
        ))}
      </div>

      {/* Empty state */}
      {sortedSeasons.length === 0 && (
        <div className="space-y-1">
          <p className="font-medium">No episodes found</p>
          <p className="text-muted-foreground text-sm">
            This series has no episode files in Sonarr.
          </p>
        </div>
      )}

      {/* Season Accordion (D-05) */}
      {sortedSeasons.length > 0 && (
        <Accordion type="multiple" defaultValue={defaultValue}>
          {sortedSeasons.map((season) => {
            const seasonLabel =
              season.season_number === 0
                ? "Specials"
                : `Season ${season.season_number}`;

            // "Translate season" button present only when eligible episodes exist
            const hasEligible = season.episodes.some(
              (e) =>
                e.has_file &&
                e.source_path !== null &&
                e.status !== "translated",
            );

            return (
              <AccordionItem
                key={season.season_number}
                value={`season-${season.season_number}`}
              >
                <AccordionTrigger className="px-4">
                  <span className="flex-1 text-left">
                    <span className="font-medium">{seasonLabel}</span>
                    <span className="text-muted-foreground text-xs ml-2">
                      {season.episodes.length} episodes
                    </span>
                  </span>
                  {hasEligible && (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={(e) => {
                        // Prevent accordion toggle when clicking the season translate button
                        e.stopPropagation();
                        void handleTranslateSeason(season);
                      }}
                      className="mr-2"
                    >
                      Translate season
                    </Button>
                  )}
                </AccordionTrigger>
                <AccordionContent>
                  <EpisodeTable
                    episodes={season.episodes}
                    bazarrAvailable={data?.bazarr_available ?? false}
                    translateErrors={translateErrors}
                    onTranslate={handleTranslateEpisode}
                  />
                </AccordionContent>
              </AccordionItem>
            );
          })}
        </Accordion>
      )}
    </div>
  );
}
