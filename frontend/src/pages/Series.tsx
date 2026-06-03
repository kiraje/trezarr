/**
 * Series page — stub placeholder for the Series library view.
 *
 * Conforms to 12-UI-SPEC.md Interaction Contract 8:
 * - Heading placeholder (Heading role: text-xl / font-semibold / 600)
 * - Optional muted subline (Body role: text-muted-foreground)
 * - No data fetching, no useState/useEffect, no console errors
 * - Zero imports required (noUnusedLocals strict mode)
 *
 * Real content (series table, season accordions) arrives in Phase 14.
 */
export default function Series() {
  return (
    <div>
      <h1 className="text-xl font-semibold">Series</h1>
      <p className="text-muted-foreground">Coming in Phase 14</p>
    </div>
  );
}
