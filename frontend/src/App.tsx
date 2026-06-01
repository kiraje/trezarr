/**
 * Root React application with client-side routing (D-73).
 *
 * Routes:
 *   /           → redirect to /queue (default)
 *   /settings   → Settings page (SVC-02)
 *   /queue      → Queue page (SVC-03)
 *   /history    → History page (SVC-03)
 *   /jobs/:id/logs → Per-job Logs page (SVC-03)
 *
 * All routes are wrapped in AppShell (TopBar + Sidebar + Content area).
 * StaticFiles(html=True) on the FastAPI side handles SPA routing fallback
 * (Pattern 6 — returns index.html for any unknown path).
 */
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import AppShell from "./components/AppShell";
import Settings from "./pages/Settings";
import Queue from "./pages/Queue";
import History from "./pages/History";
import JobLogs from "./pages/JobLogs";

export default function App() {
  return (
    <BrowserRouter>
      <AppShell>
        <Routes>
          {/* Default: redirect / → /queue */}
          <Route path="/" element={<Navigate to="/queue" replace />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="/queue" element={<Queue />} />
          <Route path="/history" element={<History />} />
          <Route path="/jobs/:id/logs" element={<JobLogs />} />
          {/* Phase 8 placeholder */}
          <Route
            path="/bible"
            element={
              <div className="text-[#6b7280] text-sm">
                Series Bible editing will be available in a future release.
              </div>
            }
          />
        </Routes>
      </AppShell>
    </BrowserRouter>
  );
}
