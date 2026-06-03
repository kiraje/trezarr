/**
 * NotFound — minimal 404 page rendered for unmatched routes (WR-03, Phase 14 plan 02).
 *
 * T-14-02-01: renders only static copy; no URL/pathname reflected into DOM (no XSS surface).
 * T-14-02-02: navigate target is the hardcoded literal '/series' (no open redirect).
 */
import { useNavigate } from "react-router-dom";
import { Button } from "../components/ui/button";

export default function NotFound() {
  const navigate = useNavigate();
  return (
    <div className="flex flex-col items-center justify-center h-64 gap-4">
      <h1 className="text-xl font-semibold">Page not found</h1>
      <p className="text-muted-foreground">
        The page you&apos;re looking for doesn&apos;t exist.
      </p>
      <Button variant="outline" onClick={() => navigate("/series")}>
        Go to Series
      </Button>
    </div>
  );
}
