/**
 * Root React application with client-side routing (D-73, D-04).
 *
 * Layout route: <Route path="/" element={<AppShell/>}> hosts all pages via <Outlet/>.
 * Child paths are RELATIVE (no leading slash); index redirects to /series (NAV-02).
 *
 * Routes:
 *   /                   → redirect to /series (default, NAV-02)
 *   /series             → Series page (stub, Phase 14 real content)
 *   /series/:seriesId   → SeriesDetail page (stub, Phase 14 real content)
 *   /movies             → Movies page (stub, Phase 14 real content)
 *   /queue              → Queue page (SVC-03)
 *   /history            → History page (SVC-03)
 *   /jobs/:id/logs      → Per-job Logs page (SVC-03)
 *   /settings           → Settings page (SVC-02)
 *   /bible              → Bible List page
 *   /bible/:seriesId    → Bible Editor page
 *   /library            → Library page (transitional route, D-03 — not in nav; removed Phase 14)
 *
 * SPAStaticFiles(html=True) on the FastAPI side handles SPA routing fallback
 * (returns index.html for any unknown extensionless path not under /api or /webhook).
 * No backend change needed for the new /series, /series/:id, /movies deep links (D-04).
 *
 * T-12-02: Navigate target is the hardcoded literal /series (not user-controlled — no open redirect).
 */
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import AppShell from "./components/AppShell";
import Series from "./pages/Series";
import SeriesDetail from "./pages/SeriesDetail";
import Movies from "./pages/Movies";
import Queue from "./pages/Queue";
import History from "./pages/History";
import JobLogs from "./pages/JobLogs";
import Settings from "./pages/Settings";
import BibleList from "./pages/BibleList";
import BibleEditor from "./pages/BibleEditor";
import Library from "./pages/Library"; // transitional (D-03) — removed Phase 14
import LibraryProvider from "./contexts/LibraryContext";

export default function App() {
  return (
    <LibraryProvider>
    <BrowserRouter>
      <Routes>
        {/* Layout route: AppShell hosts all pages via <Outlet/> (D-04) */}
        <Route path="/" element={<AppShell />}>
          {/* Default: redirect / → /series (NAV-02; T-12-02: hardcoded literal, not user-controlled) */}
          <Route index element={<Navigate to="/series" replace />} />
          <Route path="series" element={<Series />} />
          <Route path="series/:seriesId" element={<SeriesDetail />} />
          <Route path="movies" element={<Movies />} />
          <Route path="queue" element={<Queue />} />
          <Route path="history" element={<History />} />
          <Route path="jobs/:id/logs" element={<JobLogs />} />
          <Route path="settings" element={<Settings />} />
          <Route path="bible" element={<BibleList />} />
          <Route path="bible/:seriesId" element={<BibleEditor />} />
          <Route path="library" element={<Library />} /> {/* transitional, not in nav (D-03) */}
        </Route>
      </Routes>
    </BrowserRouter>
    </LibraryProvider>
  );
}
