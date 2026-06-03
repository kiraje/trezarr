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
 */
import { useLocation, useNavigate } from "react-router-dom";
import { Captions, Tv, Film, List, History, BookOpen, Settings } from "lucide-react";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuItem,
  SidebarMenuButton,
  SidebarRail,
  SidebarTrigger,
} from "./ui/sidebar";

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

      {/* Nav (NAV-02): six locked items; accent bar via className (NAV-01) */}
      <SidebarContent>
        <SidebarMenu>
          {NAV_ITEMS.map(({ to, label, icon: Icon }) => {
            // D-05: prefix-match keeps /series active on /series/:id and /bible active on /bible/:id
            const isActive = pathname === to || pathname.startsWith(to + "/");
            return (
              <SidebarMenuItem key={to}>
                <SidebarMenuButton
                  isActive={isActive}
                  tooltip={label}
                  onClick={() => navigate(to)}
                  className="border-l-2 border-transparent data-[active=true]:border-sidebar-primary"
                >
                  <Icon size={16} />
                  <span>{label}</span>
                </SidebarMenuButton>
              </SidebarMenuItem>
            );
          })}
        </SidebarMenu>
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
