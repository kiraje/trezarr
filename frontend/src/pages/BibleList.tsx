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

function UnreachableBanner() {
  return (
    <div
      className="w-full mb-4 px-4 py-3 text-sm rounded"
      style={{ backgroundColor: "#451a03", color: "#fbbf24" }}
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
        <h1 className="text-lg font-semibold text-text-primary">
          Series Bible
        </h1>
      </div>

      {unreachable && <UnreachableBanner />}

      {loading ? (
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-[#2d3148]">
                <th
                  scope="col"
                  className="px-3 py-2 text-left text-xs text-text-muted font-normal w-1/2"
                >
                  Series
                </th>
                <th
                  scope="col"
                  className="px-3 py-2 text-left text-xs text-text-muted font-normal"
                  style={{ width: "15%" }}
                >
                  Characters
                </th>
                <th
                  scope="col"
                  className="px-3 py-2 text-left text-xs text-text-muted font-normal"
                  style={{ width: "15%" }}
                >
                  Terms
                </th>
                <th
                  scope="col"
                  className="px-3 py-2 text-left text-xs text-text-muted font-normal"
                  style={{ width: "20%" }}
                >
                  Register
                </th>
              </tr>
            </thead>
            <tbody>
              {[0, 1, 2].map((i) => (
                <tr key={i} className="h-10 border-b border-[#2d3148]">
                  <td className="px-3">
                    <div className="h-4 bg-bg-surface rounded w-48" />
                  </td>
                  <td className="px-3">
                    <div className="h-4 bg-bg-surface rounded w-8" />
                  </td>
                  <td className="px-3">
                    <div className="h-4 bg-bg-surface rounded w-8" />
                  </td>
                  <td className="px-3">
                    <div className="h-4 bg-bg-surface rounded w-16" />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : series.length === 0 && !unreachable ? (
        <div className="py-12 flex flex-col items-center gap-2">
          <p className="text-sm font-semibold text-text-primary">
            No series in Bible
          </p>
          <p className="text-xs text-text-muted text-center max-w-sm">
            Series Bibles are created automatically when Trezarr processes an
            episode. Run a translation to get started.
          </p>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-[#2d3148]">
                <th
                  scope="col"
                  className="px-3 py-2 text-left text-xs text-text-muted font-normal w-1/2"
                >
                  Series
                </th>
                <th
                  scope="col"
                  className="px-3 py-2 text-left text-xs text-text-muted font-normal"
                  style={{ width: "15%" }}
                >
                  Characters
                </th>
                <th
                  scope="col"
                  className="px-3 py-2 text-left text-xs text-text-muted font-normal"
                  style={{ width: "15%" }}
                >
                  Terms
                </th>
                <th
                  scope="col"
                  className="px-3 py-2 text-left text-xs text-text-muted font-normal"
                  style={{ width: "20%" }}
                >
                  Register
                </th>
              </tr>
            </thead>
            <tbody>
              {series.map((s, idx) => (
                <tr
                  key={s.id}
                  className={[
                    "h-10 border-b border-[#2d3148] cursor-pointer hover:bg-[#22263a]",
                    idx % 2 === 1 ? "bg-bg-stripe" : "",
                  ]
                    .filter(Boolean)
                    .join(" ")}
                  onClick={() => navigate(`/bible/${s.id}`)}
                >
                  <td className="px-3 text-sm text-text-primary">
                    {s.arr_kind}/{s.arr_series_id}
                  </td>
                  <td className="px-3 text-xs text-text-muted">—</td>
                  <td className="px-3 text-xs text-text-muted">—</td>
                  <td className="px-3 text-xs text-text-primary">
                    {s.register ?? (
                      <span className="text-text-muted">—</span>
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
