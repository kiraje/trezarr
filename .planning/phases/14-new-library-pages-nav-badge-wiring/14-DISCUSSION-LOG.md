# Phase 14: New Library Pages + Nav Badge Wiring - Discussion Log

> **Audit trail only.** Decisions captured in CONTEXT.md. This was an `--auto` run:
> Claude auto-selected the recommended option for each gray area from the locked
> research (ARCHITECTURE.md §3/§5/§7), REQUIREMENTS (LIB-01..07, NAV-03), the
> Phase-11 UI-SPEC badge contract, and the P12/P13 CONTEXTs. No AskUserQuestion.

**Date:** 2026-06-04
**Phase:** 14-new-library-pages-nav-badge-wiring
**Mode:** auto (no user prompts)
**Areas auto-decided:** Table choice, Data fetching, Search/filter/sort, Series detail, Badges + a11y, Translate actions, Nav count/LIVE badges, Library.tsx removal

| Area | Auto-selected decision | Rationale / alternative rejected |
|------|------------------------|----------------------------------|
| Table choice (D-01) | shadcn plain `<Table>` + component-state sort | jolly-ui Table is beta (React Aria) — Phase-11 deferred the stability eval here; default to stable, adopt jolly-ui only if a concrete affordance wins. Quality bar favors stability. |
| Data fetching (D-03) | Raw fetch + useState/useEffect | ARCHITECTURE.md §5 explicitly rejects React Query/SWR for v1.1. |
| Search/filter/sort (D-04) | Client-side in-memory on the lists | Consistent with no-query-lib; lists are small; debounced title search + status filter + progress sort. |
| Series detail (D-05) | shadcn Accordion by season, latest auto-expanded, Specials last, bazarr-unavailable suppresses sub column | Matches LIB-03 + P13 `bazarr_available` contract. |
| Badges (D-06/D-07) | CODE2 uppercase + :HI/:Forced; amber=source/purple=VI/blue=audio; shape+aria-label non-color cue | LIB-04 + Phase-11 UI-SPEC; accessibility is a hard requirement, not polish. |
| Translate (D-08) | Row + season-header Translate → POST /api/translate → navigate('/queue'); absent when no file | LIB-05 + roadmap SC3. |
| Nav count badge (D-09) | Count items where `translated_count < total_count`, auto-hidden at zero | Cheap proxy from the list endpoint; documented approximation (can't see per-episode source-but-no-vi cheaply). |
| LIVE badge (D-10) | Derive from `GET /api/library` errors[] per source | Uses existing data; no new health endpoint. |
| Library.tsx removal (D-11) | Delete Library.tsx + /library route + EpisodeRow type once Series/Movies work | Completes P12→P14 route-split handoff (NAV-02). |

## Claude's Discretion
Table columns/sort fields, debounce timing, badge shape cue specifics, empty/loading/error copy, Translate-season confirmation, whether Movies rows navigate.

## Deferred Ideas
Movie detail page (not in scope); jolly-ui Table adoption (only if shadcn sort UX insufficient); existing-page reskin + bridge-token removal → Phase 15.
