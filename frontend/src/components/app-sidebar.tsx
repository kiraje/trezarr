/**
 * AppSidebar — hand-written Trezarr nav component composing shadcn vendor primitives.
 *
 * Conforms to 12-UI-SPEC.md Interaction Contracts 2/3/4/5/6/7 and decisions:
 * - D-01: collapsible="icon" (icon rail); default expanded; SidebarRail + Cmd/Ctrl+B toggle;
 *         vendor sidebar_state cookie persistence; mobile Sheet (vendor-automatic)
 * - D-02: SidebarFooter green status dot (static server-is-serving; NOT wired to *arr state)
 * - D-05: active state via useLocation prefix-match (pathname === to || pathname.startsWith(to+"/"));
 *         navigation via onClick navigate(to) — NOT asChild+anchor (fights Radix Slot)
 * - D-06: brand = lucide Captions glyph (text-sidebar-primary) + uppercase TREZARR pill in SidebarHeader
 *
 * NAV-01: left 2px purple accent bar on the active item is composed via className on each
 * SidebarMenuButton ("border-l-2 border-transparent data-[active=true]:border-sidebar-primary").
 * The vendor primitive provides filled-bg active state only (sidebar.tsx:523); this className
 * adds the bar additively via cn() — never edit the vendor file.
 *
 * NAV-02: exactly six nav items in locked order (Series/Movies/Queue/History/Bible/Settings);
 * /library is absent from NAV_ITEMS (D-03 — transitional route, not a nav item).
 *
 * NAV-03 (D-09/D-10 badge wiring, Phase 14 plan 02):
 *   - Series/Movies rows show a count badge (purple) for items needing VI translation.
 *     Auto-hides when count === 0 (renders nothing, not a "0" badge).
 *   - Series/Movies rows show a LIVE badge (emerald) when the backing *arr service is connected.
 *     Derivation is via getSeriesLiveBadge / getMoviesLiveBadge (D-10 rule in LibraryContext).
 *   - Both badges use group-data-[collapsible=icon]:hidden to disappear in icon rail mode.
 *
 * WR-01 (Phase-12 carry-forward, Phase 14 plan 02):
 *   SidebarContent > SidebarGroup > SidebarMenu — adds p-2 inset, prevents nav ul from
 *   rendering flush to panel walls, fixes icon-mode padding transitions.
 */
import { useLocation, useNavigate } from "react-router-dom";
import { Captions, Tv, Film, List, History, BookOpen, Settings } from "lucide-react";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuItem,
  SidebarMenuButton,
  SidebarRail,
  SidebarTrigger,
} from "./ui/sidebar";
import { Badge } from "./ui/badge";
import {
  useLibraryContext,
  getSeriesLiveBadge,
  getMoviesLiveBadge,
  getSeriesNeedsViCount,
  getMoviesNeedsViCount,
} from "../contexts/LibraryContext";

/** Locked six-item nav table (NAV-02 / UI-SPEC Interaction Contract 4). /library absent (D-03). */
const NAV_ITEMS = [
  { to: "/series",   label: "Series",   icon: Tv },
  { to: "/movies",   label: "Movies",   icon: Film },
  { to: "/queue",    label: "Queue",    icon: List },
  { to: "/history",  label: "History",  icon: History },
  { to: "/bible",    label: "Bible",    icon: BookOpen },
  { to: "/settings", label: "Settings", icon: Settings },
] as const;

export function AppSidebar() {
  const { pathname } = useLocation();
  const navigate = useNavigate();

  // NAV-03: read shared library data from context — no additional fetch.
  // When no library page has loaded yet, libraryData is null → all badges hidden (correct).
  const { libraryData } = useLibraryContext();
  const seriesCount = getSeriesNeedsViCount(libraryData);
  const moviesCount = getMoviesNeedsViCount(libraryData);
  const seriesLive = getSeriesLiveBadge(libraryData);
  const moviesLive = getMoviesLiveBadge(libraryData);

  return (
    <Sidebar collapsible="icon">
      {/* Brand header (D-06 / NAV-01): Captions glyph tinted text-sidebar-primary + TREZARR pill */}
      <SidebarHeader>
        <div className="flex items-center gap-2 px-1">
          <Captions className="text-sidebar-primary" size={20} />
          <span className="font-semibold uppercase tracking-wide text-sm group-data-[collapsible=icon]:hidden">
            TREZARR
          </span>
          {/* SidebarTrigger in header (D-01 discretion ON — TopBar gone, ergonomics) */}
          <SidebarTrigger className="ml-auto group-data-[collapsible=icon]:hidden" />
        </div>
      </SidebarHeader>

      {/* Nav (NAV-02): six locked items; accent bar via className (NAV-01).
          WR-01: SidebarGroup adds p-2 inset, prevents flush-wall rendering. */}
      <SidebarContent>
        <SidebarGroup>
          <SidebarMenu>
            {NAV_ITEMS.map(({ to, label, icon: Icon }) => {
              // D-05: prefix-match keeps /series active on /series/:id and /bible active on /bible/:id
              const isActive = pathname === to || pathname.startsWith(to + "/");

              // NAV-03: derive badge state for /series and /movies rows only.
              const isLive = to === "/series" ? seriesLive : to === "/movies" ? moviesLive : false;
              const count = to === "/series" ? seriesCount : to === "/movies" ? moviesCount : 0;

              return (
                <SidebarMenuItem key={to}>
                  <SidebarMenuButton
                    isActive={isActive}
                    tooltip={label}
                    onClick={() => navigate(to)}
                    className="border-l-2 border-transparent data-[active=true]:border-sidebar-primary"
                  >
                    <Icon size={16} />
                    <span className="flex-1">{label}</span>
                    {/* NAV-03 badge slot — rendered only for /series and /movies.
                        Both badges hidden in collapsed icon mode via group-data selector. */}
                    {(to === "/series" || to === "/movies") && (
                      <span className="flex items-center gap-1">
                        {isLive && (
                          <Badge
                            className="ml-0 text-xs bg-emerald-600 text-white border-transparent
                                       group-data-[collapsible=icon]:hidden"
                            aria-label="Service connected"
                          >
                            LIVE
                          </Badge>
                        )}
                        {count > 0 && (
                          <Badge
                            className="ml-0 text-xs bg-[hsl(var(--primary))] text-primary-foreground
                                       border-transparent group-data-[collapsible=icon]:hidden"
                            aria-label={`${count} items need Vietnamese translation`}
                          >
                            {count}
                          </Badge>
                        )}
                      </span>
                    )}
                  </SidebarMenuButton>
                </SidebarMenuItem>
              );
            })}
          </SidebarMenu>
        </SidebarGroup>
      </SidebarContent>

      {/* Footer status (D-02): green dot verbatim from legacy AppShell:64-69; static semantics */}
      <SidebarFooter>
        <div className="flex items-center gap-2 px-2">
          <span
            className="h-2 w-2 rounded-full bg-[#22c55e]"
            aria-label="Service status: running"
            title="Service running"
          />
          <span className="text-sm text-muted-foreground group-data-[collapsible=icon]:hidden">
            Running
          </span>
        </div>
      </SidebarFooter>

      {/* SidebarRail: draggable collapse affordance (D-01) */}
      <SidebarRail />
    </Sidebar>
  );
}
