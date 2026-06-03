/**
 * SeriesDetail page — stub placeholder for the per-series detail view.
 *
 * Conforms to 12-UI-SPEC.md Interaction Contract 8 and D-04 (series/:seriesId route):
 * - Reads :seriesId route param via useParams (required by noUnusedLocals strict mode)
 * - Renders seriesId ONLY as a JSX text node (auto-escaped) — never dangerouslySetInnerHTML
 *   (T-12-01 reflected-XSS mitigation: React auto-escapes JSX text; no sink)
 * - Heading placeholder (Heading role: text-xl / font-semibold / 600)
 * - Optional muted subline echoing seriesId (Body role: text-muted-foreground)
 *
 * Real content (season accordions, episode table) arrives in Phase 14.
 */
import { useParams } from "react-router-dom";

export default function SeriesDetail() {
  const { seriesId } = useParams();
  return (
    <div>
      <h1 className="text-xl font-semibold">Series Detail</h1>
      <p className="text-muted-foreground">Series #{seriesId} — coming in Phase 14</p>
    </div>
  );
}
