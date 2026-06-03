// Plain HTML table per D-01 (jolly-ui Table beta avoided; sort implemented in component state).
/**
 * Movies list page — real implementation (LIB-02, LIB-06, LIB-07, NAV-03).
 *
 * Fetches GET /api/library via getLibrary(), renders all Radarr movies in a
 * dense table, and calls setLibraryData() to populate LibraryContext so the
 * sidebar count + LIVE badges update without a second fetch (D-09 / NAV-03).
 *
 * Client-side controls:
 *  - Title search (case-insensitive substring, debounced 250ms)
 *  - Filter by status: All / Needs VI / Translated / No source
 *  - Sort: Title A-Z (default) / Title Z-A / Progress high-to-low / Progress low-to-high
 *
 * NOTE on source_path: Per 14-UI-SPEC.md §Movies List Page, the current GET /api/library
 * response does NOT return source_path for movies. MovieItem has no source_path field.
 * The Translate button is disabled with tooltip "Source path unavailable" per spec.
 *
 * Error/loading/empty states per 14-UI-SPEC.md §Loading, Empty, and Error States.
 */
import { useState, useEffect, useRef, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { getLibrary, postTranslate, type MovieItem, type LibraryResponse } from "../api/client";
import { useLibraryContext } from "../contexts/LibraryContext";
import { Input } from "../components/ui/input";
import { Button } from "../components/ui/button";
import { Badge } from "../components/ui/badge";
import { Skeleton } from "../components/ui/skeleton";
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
} from "../components/ui/dropdown-menu";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "../components/ui/tooltip";

// ── Types ─────────────────────────────────────────────────────────────────────

type FilterStatus = "all" | "needs_vi" | "translated" | "no_source";
type SortField = "title" | "progress";
type SortDir = "asc" | "desc";

// ── Progress bar (inline helper) ──────────────────────────────────────────────

function ProgressBar({ item }: { item: MovieItem }) {
  if (item.total_count === 0) {
    return <span className="text-muted-foreground">—</span>;
  }
  const pct = Math.round((item.translated_count / item.total_count) * 100);
  return (
    <div className="flex items-center gap-2">
      <div className="bg-muted h-1.5 rounded-full flex-1">
        <div
          className="bg-primary h-1.5 rounded-full"
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-xs text-muted-foreground whitespace-nowrap">
        {item.translated_count}/{item.total_count} translated
      </span>
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export default function Movies() {
  const navigate = useNavigate();
  const { setLibraryData } = useLibraryContext();

  const [data, setData] = useState<LibraryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchInput, setSearchInput] = useState("");
  const [query, setQuery] = useState("");
  const [filterStatus, setFilterStatus] = useState<FilterStatus>("all");
  const [sortField, setSortField] = useState<SortField>("title");
  const [sortDir, setSortDir] = useState<SortDir>("asc");
  const [translatePending, setTranslatePending] = useState<string | null>(null);
  const [translateErrors, setTranslateErrors] = useState<Record<number, string>>({});

  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // ── Fetch ──────────────────────────────────────────────────────────────────

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await getLibrary();
      setData(result);
      setLibraryData(result); // D-09 / NAV-03: populate context for sidebar badges
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  }, [setLibraryData]);

  useEffect(() => {
    void load();
  }, [load]);

  // ── Debounce search ────────────────────────────────────────────────────────

  useEffect(() => {
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => setQuery(searchInput), 250);
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [searchInput]);

  // ── Translate handler ──────────────────────────────────────────────────────

  async function handleTranslate(movie: MovieItem) {
    // source_path not in API response — disabled with tooltip per 14-UI-SPEC.md.
    // This handler only fires if the API is updated to return source_path in the future.
    setTranslatePending(String(movie.id));
    setTranslateErrors((prev) => {
      const next = { ...prev };
      delete next[movie.id];
      return next;
    });
    try {
      await postTranslate("movie", null, "");
      navigate("/queue");
    } catch {
      setTranslateErrors((prev) => ({
        ...prev,
        [movie.id]: "Could not enqueue. Check source file exists.",
      }));
    } finally {
      setTranslatePending(null);
    }
  }

  // ── Loading state ──────────────────────────────────────────────────────────

  if (loading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-32 mb-4" />
        <Skeleton className="h-9 w-64 mb-4" />
        {Array.from({ length: 6 }).map((_, i) => (
          <Skeleton key={i} className="h-12 w-full mb-1" />
        ))}
      </div>
    );
  }

  // ── Error state ────────────────────────────────────────────────────────────

  if (error !== null) {
    return (
      <div className="space-y-3">
        <h1 className="text-xl font-semibold">Failed to load Movies</h1>
        <p className="text-muted-foreground">
          An error occurred while fetching the library. Try reloading.
        </p>
        <Button onClick={() => void load()}>Retry</Button>
      </div>
    );
  }

  // ── Radarr down state ──────────────────────────────────────────────────────

  const isRadarrDown =
    data !== null &&
    data.movies.length === 0 &&
    data.errors.some((e) => e.source === "radarr");

  if (isRadarrDown) {
    return (
      <div className="space-y-3">
        <h1 className="text-xl font-semibold">Radarr unavailable</h1>
        <p className="text-muted-foreground">
          Could not load the movie library. Check your Radarr connection in
          Settings.
        </p>
        <Button variant="outline" onClick={() => navigate("/settings")}>
          Go to Settings
        </Button>
      </div>
    );
  }

  // ── Derived data: filter + sort ────────────────────────────────────────────

  let filtered: MovieItem[] = data?.movies ?? [];

  if (query) {
    filtered = filtered.filter((m) =>
      m.title.toLowerCase().includes(query.toLowerCase()),
    );
  }
  if (filterStatus === "needs_vi") {
    filtered = filtered.filter((m) => m.translated_count < m.total_count);
  } else if (filterStatus === "translated") {
    filtered = filtered.filter(
      (m) => m.translated_count >= m.total_count && m.total_count > 0,
    );
  } else if (filterStatus === "no_source") {
    filtered = filtered.filter((m) => m.total_count === 0);
  }

  if (sortField === "title") {
    filtered = [...filtered].sort((a, b) =>
      sortDir === "asc"
        ? a.title.localeCompare(b.title)
        : b.title.localeCompare(a.title),
    );
  } else {
    filtered = [...filtered].sort((a, b) => {
      const ra = a.total_count > 0 ? a.translated_count / a.total_count : 0;
      const rb = b.total_count > 0 ? b.translated_count / b.total_count : 0;
      return sortDir === "asc" ? ra - rb : rb - ra;
    });
  }

  const filterLabel: Record<FilterStatus, string> = {
    all: "All",
    needs_vi: "Needs VI",
    translated: "Translated",
    no_source: "No source",
  };

  // ── Normal state ───────────────────────────────────────────────────────────

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Movies</h1>

      {/* Controls bar */}
      <div className="flex items-center gap-3 mb-4">
        <Input
          placeholder="Search movies..."
          className="max-w-xs"
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value)}
        />
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="outline" size="sm">
              Filter: {filterLabel[filterStatus]}
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent>
            <DropdownMenuItem onSelect={() => setFilterStatus("all")}>
              All
            </DropdownMenuItem>
            <DropdownMenuItem onSelect={() => setFilterStatus("needs_vi")}>
              Needs VI
            </DropdownMenuItem>
            <DropdownMenuItem onSelect={() => setFilterStatus("translated")}>
              Translated
            </DropdownMenuItem>
            <DropdownMenuItem onSelect={() => setFilterStatus("no_source")}>
              No source
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
        <Button
          variant="outline"
          size="sm"
          onClick={() => {
            if (sortField === "title") {
              setSortDir((d) => (d === "asc" ? "desc" : "asc"));
            } else {
              setSortField("title");
              setSortDir("asc");
            }
          }}
        >
          Sort by Title{" "}
          {sortField === "title" ? (sortDir === "asc" ? "↑" : "↓") : ""}
        </Button>
        <Button
          variant="outline"
          size="sm"
          onClick={() => {
            if (sortField === "progress") {
              setSortDir((d) => (d === "asc" ? "desc" : "asc"));
            } else {
              setSortField("progress");
              setSortDir("desc");
            }
          }}
        >
          Sort by Progress{" "}
          {sortField === "progress" ? (sortDir === "asc" ? "↑" : "↓") : ""}
        </Button>
      </div>

      {/* Empty after filter */}
      {filtered.length === 0 && !isRadarrDown ? (
        <div className="space-y-3">
          <h2 className="text-base font-medium text-muted-foreground">
            No movies found
          </h2>
          <p className="text-muted-foreground">
            No movies match your search or filter. Try clearing the filter.
          </p>
          <Button
            variant="outline"
            onClick={() => {
              setSearchInput("");
              setQuery("");
              setFilterStatus("all");
            }}
          >
            Clear filters
          </Button>
        </div>
      ) : (
        // Plain HTML table per D-01
        // (jolly-ui Table beta stability risk avoided; sort implemented in component state)
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-muted-foreground">
                <th className="text-left py-2 px-4">Title</th>
                <th className="text-left py-2 px-4 w-[100px]">Source sub</th>
                <th className="text-left py-2 px-4 w-[220px]">Status</th>
                <th className="text-left py-2 px-4 w-[100px]">Action</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((m) => {
                const canTranslate =
                  m.source_sub_found && m.translated_count === 0;
                const isFullyTranslated =
                  m.translated_count >= m.total_count && m.total_count > 0;

                return (
                  <tr
                    key={m.id}
                    className="border-b border-border hover:bg-accent/50 transition-colors"
                  >
                    {/* Title + year */}
                    <td className="py-2 px-4">
                      <span className="font-medium">{m.title}</span>
                      {m.year !== null && (
                        <span className="text-muted-foreground text-xs ml-1.5">
                          ({m.year})
                        </span>
                      )}
                    </td>

                    {/* Source sub badge */}
                    <td className="py-2 px-4">
                      {m.source_sub_found ? (
                        <Badge className="bg-amber-600/80 text-white border-transparent text-xs">
                          SOURCE
                        </Badge>
                      ) : (
                        <span className="text-muted-foreground">—</span>
                      )}
                    </td>

                    {/* Progress bar + fraction */}
                    <td className="py-2 px-4">
                      <ProgressBar item={m} />
                    </td>

                    {/* Action column */}
                    <td className="py-2 px-4">
                      {isFullyTranslated ? (
                        <Badge className="bg-emerald-600/80 text-white border-transparent text-xs">
                          Translated
                        </Badge>
                      ) : canTranslate ? (
                        // source_path not in API response — disabled with tooltip per 14-UI-SPEC.md
                        <div>
                          <TooltipProvider>
                            <Tooltip>
                              <TooltipTrigger asChild>
                                {/* wrapper span needed: disabled button doesn't fire events for tooltip */}
                                <span>
                                  <Button
                                    size="sm"
                                    disabled={true}
                                    className="min-h-[44px]"
                                    onClick={() => void handleTranslate(m)}
                                  >
                                    {translatePending === String(m.id)
                                      ? "Queuing…"
                                      : "Translate"}
                                  </Button>
                                </span>
                              </TooltipTrigger>
                              <TooltipContent>
                                Source path unavailable
                              </TooltipContent>
                            </Tooltip>
                          </TooltipProvider>
                          {translateErrors[m.id] && (
                            <span className="text-destructive text-xs block mt-1">
                              {translateErrors[m.id]}
                            </span>
                          )}
                        </div>
                      ) : null}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
