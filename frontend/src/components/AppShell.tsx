/**
 * AppShell — TopBar + Sidebar + Content area layout.
 *
 * Conforms to 07-UI-SPEC.md §App Shell:
 * - TopBar: 48px, bg-surface, "Trezarr" wordmark, service status dot
 * - Sidebar: 192px (w-48), nav items Settings/Queue/History + Bible placeholder
 * - Content area: flex-1, base background, xl horizontal padding
 *
 * Active nav item: left 2px accent border + bg-stripe background.
 * "Bible" nav item is muted/non-functional (Phase 8 placeholder).
 */
import { ReactNode } from "react";
import { NavLink } from "react-router-dom";
import { Settings, List, History, BookOpen } from "lucide-react";

interface AppShellProps {
  children: ReactNode;
}

interface NavItemProps {
  to: string;
  icon: ReactNode;
  label: string;
  disabled?: boolean;
}

function NavItem({ to, icon, label, disabled = false }: NavItemProps) {
  if (disabled) {
    return (
      <div
        className="flex items-center gap-2 px-4 min-h-10 text-sm text-[#6b7280] cursor-default"
        title="Available in a future release"
      >
        {icon}
        <span>{label}</span>
      </div>
    );
  }

  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        [
          "flex items-center gap-2 px-4 min-h-10 text-sm no-underline transition-colors duration-150",
          isActive
            ? "border-l-2 border-accent bg-bg-stripe text-[#e2e6f0] pl-[14px]"
            : "text-[#e2e6f0] hover:bg-[#1e2130] border-l-2 border-transparent pl-[14px]",
        ].join(" ")
      }
    >
      {icon}
      <span>{label}</span>
    </NavLink>
  );
}

export default function AppShell({ children }: AppShellProps) {
  return (
    <div className="flex flex-col min-h-screen bg-bg-base">
      {/* TopBar: 48px, bg-surface */}
      <header className="h-12 bg-bg-surface border-b border-[#2d3148] flex items-center justify-between px-4 flex-shrink-0">
        <span className="text-base font-semibold text-[#e2e6f0]">Trezarr</span>
        {/* Service status dot — green = running (the server is serving this page) */}
        <div
          className="w-2 h-2 rounded-full bg-[#22c55e]"
          aria-label="Service status: running"
          title="Service running"
        />
      </header>

      <div className="flex flex-1">
        {/* Sidebar: 192px (w-48), bg-surface */}
        <nav
          className="w-48 bg-bg-surface border-r border-[#2d3148] flex flex-col py-2 flex-shrink-0"
          aria-label="Primary navigation"
        >
          <NavItem
            to="/settings"
            icon={<Settings size={16} />}
            label="Settings"
          />
          <NavItem
            to="/queue"
            icon={<List size={16} />}
            label="Queue"
          />
          <NavItem
            to="/history"
            icon={<History size={16} />}
            label="History"
          />
          <NavItem
            to="/bible"
            icon={<BookOpen size={16} />}
            label="Bible"
          />
        </nav>

        {/* Content area: flex-1, xl horizontal padding, lg vertical padding */}
        <main className="flex-1 bg-bg-base px-8 py-6 overflow-auto">
          {children}
        </main>
      </div>
    </div>
  );
}
