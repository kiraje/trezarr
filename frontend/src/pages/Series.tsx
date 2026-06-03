/**
 * Series list page — real implementation (LIB-01, LIB-06, LIB-07, NAV-03).
 *
 * Fetches GET /api/library via getLibrary(), renders all Sonarr series in a
 * dense table, and calls setLibraryData() to populate LibraryContext so the
 * sidebar count + LIVE badges update without a second fetch (D-09 / NAV-03).
 *
 * Client-side controls:
 *  - Title search (case-insensitive substring, debounced 250ms)
 *  - Filter by status: All / Needs VI / Translated / No source
 *  - Sort: Title A-Z (default) / Title Z-A / Progress high-to-low / Progress low-to-high
 *
 * Error/loading/empty states per 14-UI-SPEC.md §Loading, Empty, and Error States.
 */
import { useState, useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { getLibrary, type SeriesItem, type LibraryResponse } from "../api/client";
import { useLibraryContext } from "../contexts/LibraryContext";
import { Input } from "../components/ui/input";
import { Button } from "../components/ui/button";
import { Skeleton } from "../components/ui/skeleton";
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
} from "../components/ui/dropdown-menu";

// ── Types ─────────────────────────────────────────────────────────────────────

type FilterStatus = "all" | "needs_vi" | "translated" | "no_files";
type SortField = "title" | "progress";
type SortDir = "asc" | "desc";

// ── Progress bar (inline helper) ──────────────────────────────────────────────

function ProgressBar({ item }: { item: SeriesItem }) {
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

export default function Series() {
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
  const [fetchTick, setFetchTick] = useState(0);

  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // ── Fetch ──────────────────────────────────────────────────────────────────
  // Cancelled flag prevents stale setState / setLibraryData (context setter) from
  // firing after navigation. setLibraryData is stable so it needs no dep entry.
  // fetchTick is incremented by the Retry button to force a re-run.

  useEffect(() => {
    let cancelled = false;
    async function run() {
      setLoading(true);
      setError(null);
      try {
        const result = await getLibrary();
        if (cancelled) return;
        setData(result);
        setLibraryData(result); // D-09 / NAV-03: populate context for sidebar badges
      } catch (err) {
        if (cancelled) return;
        setError(String(err));
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void run();
    return () => { cancelled = true; };
  }, [setLibraryData, fetchTick]);

  // ── Debounce search ────────────────────────────────────────────────────────

  useEffect(() => {
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => setQuery(searchInput), 250);
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [searchInput]);

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
        <h1 className="text-xl font-semibold">Failed to load Series</h1>
        <p className="text-muted-foreground">
          An error occurred while fetching the library. Try reloading.
        </p>
        <Button onClick={() => setFetchTick((t) => t + 1)}>Retry</Button>
      </div>
    );
  }

  // ── Sonarr down state ──────────────────────────────────────────────────────

  const isSonarrDown =
    data !== null &&
    data.series.length === 0 &&
    data.errors.some((e) => e.source === "sonarr");

  if (isSonarrDown) {
    return (
      <div className="space-y-3">
        <h1 className="text-xl font-semibold">Sonarr unavailable</h1>
        <p className="text-muted-foreground">
          Could not load the series library. Check your Sonarr connection in
          Settings.
        </p>
        <Button variant="outline" onClick={() => navigate("/settings")}>
          Go to Settings
        </Button>
      </div>
    );
  }

  // ── Derived data: filter + sort ────────────────────────────────────────────

  let filtered: SeriesItem[] = data?.series ?? [];

  if (query) {
    filtered = filtered.filter((s) =>
      s.title.toLowerCase().includes(query.toLowerCase()),
    );
  }
  if (filterStatus === "needs_vi") {
    filtered = filtered.filter((s) => s.translated_count < s.total_count);
  } else if (filterStatus === "translated") {
    filtered = filtered.filter(
      (s) => s.translated_count >= s.total_count && s.total_count > 0,
    );
  } else if (filterStatus === "no_files") {
    filtered = filtered.filter((s) => s.total_count === 0);
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
    no_files: "No files",
  };

  // ── Normal state ───────────────────────────────────────────────────────────

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Series</h1>

      {/* Controls bar */}
      <div className="flex items-center gap-3 mb-4">
        <Input
          placeholder="Search series..."
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
            <DropdownMenuItem onSelect={() => setFilterStatus("no_files")}>
              No files
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
      {filtered.length === 0 && !isSonarrDown ? (
        <div className="space-y-3">
          <h2 className="text-base font-medium text-muted-foreground">
            No series found
          </h2>
          <p className="text-muted-foreground">
            No series match your search or filter. Try clearing the filter.
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
                <th className="text-left py-2 px-4 w-[80px]">Year</th>
                <th className="text-left py-2 px-4 w-[220px]">Progress</th>
                <th className="text-right py-2 px-4 w-[120px]">Translated</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((s) => (
                <tr
                  key={s.id}
                  className="border-b border-border cursor-pointer hover:bg-accent/50 transition-colors"
                  onClick={() => navigate("/series/" + s.id)}
                >
                  <td className="py-2 px-4">
                    <span className="font-medium">{s.title}</span>
                  </td>
                  <td className="py-2 px-4 text-muted-foreground">
                    {s.year ?? "—"}
                  </td>
                  <td className="py-2 px-4">
                    <ProgressBar item={s} />
                  </td>
                  <td className="py-2 px-4 text-right text-muted-foreground">
                    {s.total_count === 0
                      ? "—"
                      : `${s.translated_count}/${s.total_count}`}
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
