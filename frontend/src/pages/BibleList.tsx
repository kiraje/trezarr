/**
 * BibleList page — Series Bible entry point (/bible).
 *
 * Conforms to 08-UI-SPEC.md §BibleList Page:
 * - Lists all series from GET /api/series
 * - Columns: Series (50%) / Characters (15%) / Terms (15%) / Register (20%)
 * - Entire row clickable → /bible/:id
 * - Loading state: heading + 3 skeleton rows
 * - Empty state: "No series in Bible" + helper body text
 * - Error state: amber unreachable banner
 *
 * Analog: Queue.tsx (fetch-on-mount pattern, unreachable banner, table rendering)
 */
import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { getSeriesList, type SeriesListItem } from "../api/client";
import { Skeleton } from "../components/ui/skeleton";

function UnreachableBanner() {
  return (
    <div
      className="w-full mb-4 px-4 py-3 text-sm rounded bg-amber-900/30 border border-amber-800 text-amber-400"
      role="alert"
    >
      Could not load series list. Check the server logs.
    </div>
  );
}

export default function BibleList() {
  const [series, setSeries] = useState<SeriesListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [unreachable, setUnreachable] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const data = await getSeriesList();
        if (!cancelled) {
          setSeries(data);
          setUnreachable(false);
          setLoading(false);
        }
      } catch {
        if (!cancelled) {
          setUnreachable(true);
          setLoading(false);
        }
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div>
      <div className="flex items-center gap-3 mb-4">
        <h1 className="text-xl font-semibold text-foreground">
          Series Bible
        </h1>
      </div>

      {unreachable && <UnreachableBanner />}

      {loading ? (
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-border">
                <th
                  scope="col"
                  className="px-3 py-2 text-left text-xs text-muted-foreground font-normal w-1/2"
                >
                  Series
                </th>
                <th
                  scope="col"
                  className="px-3 py-2 text-left text-xs text-muted-foreground font-normal"
                  style={{ width: "15%" }}
                >
                  Characters
                </th>
                <th
                  scope="col"
                  className="px-3 py-2 text-left text-xs text-muted-foreground font-normal"
                  style={{ width: "15%" }}
                >
                  Terms
                </th>
                <th
                  scope="col"
                  className="px-3 py-2 text-left text-xs text-muted-foreground font-normal"
                  style={{ width: "20%" }}
                >
                  Register
                </th>
              </tr>
            </thead>
            <tbody>
              {[0, 1, 2].map((i) => (
                <tr key={i} className="h-10 border-b border-border">
                  <td className="px-3">
                    <Skeleton className="h-4 w-48" />
                  </td>
                  <td className="px-3">
                    <Skeleton className="h-4 w-8" />
                  </td>
                  <td className="px-3">
                    <Skeleton className="h-4 w-8" />
                  </td>
                  <td className="px-3">
                    <Skeleton className="h-4 w-16" />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : series.length === 0 && !unreachable ? (
        <div className="py-12 flex flex-col items-center gap-2">
          <p className="text-sm font-semibold text-foreground">
            No series in Bible
          </p>
          <p className="text-xs text-muted-foreground text-center max-w-sm">
            Series Bibles are created automatically when Trezarr processes an
            episode. Run a translation to get started.
          </p>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-border">
                <th
                  scope="col"
                  className="px-3 py-2 text-left text-xs text-muted-foreground font-normal w-1/2"
                >
                  Series
                </th>
                <th
                  scope="col"
                  className="px-3 py-2 text-left text-xs text-muted-foreground font-normal"
                  style={{ width: "15%" }}
                >
                  Characters
                </th>
                <th
                  scope="col"
                  className="px-3 py-2 text-left text-xs text-muted-foreground font-normal"
                  style={{ width: "15%" }}
                >
                  Terms
                </th>
                <th
                  scope="col"
                  className="px-3 py-2 text-left text-xs text-muted-foreground font-normal"
                  style={{ width: "20%" }}
                >
                  Register
                </th>
              </tr>
            </thead>
            <tbody>
              {series.map((s) => (
                <tr
                  key={s.id}
                  className="h-10 border-b border-border cursor-pointer hover:bg-accent/50"
                  onClick={() => navigate(`/bible/${s.id}`)}
                >
                  <td className="px-3 text-sm text-foreground">
                    {s.arr_kind}/{s.arr_series_id}
                  </td>
                  <td className="px-3 text-xs text-muted-foreground">—</td>
                  <td className="px-3 text-xs text-muted-foreground">—</td>
                  <td className="px-3 text-xs text-foreground">
                    {s.register ?? (
                      <span className="text-muted-foreground">—</span>
                    )}
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
