/**
 * AppShell — thin SidebarProvider + AppSidebar + Outlet layout host.
 *
 * Conforms to 12-UI-SPEC.md Interaction Contract 1 and decisions:
 * - D-02: 48px TopBar dropped; green status dot moved to AppSidebar SidebarFooter
 * - D-04: layout-route element (<Route path="/" element={<AppShell/>}>);
 *         renders routed pages through react-router-dom <Outlet/>
 *
 * Shell composition:
 *   <SidebarProvider>      // whole-document context: open/collapsed state + cookie + Cmd/Ctrl+B
 *     <AppSidebar />       // hand-written nav (brand, 6 items, accent bar, footer status)
 *     <main ...>
 *       <Outlet />         // routed page renders here (replaces legacy children prop)
 *     </main>
 *   </SidebarProvider>
 *
 * main uses bg-background (purple-tinted root per Wiring Invariant) and p-6 (lg=24px spacing).
 * No children prop, no AppShellProps, no w-48, no TopBar.
 */
import { Outlet } from "react-router-dom";
import { SidebarProvider } from "./ui/sidebar";
import { AppSidebar } from "./app-sidebar";

export default function AppShell() {
  return (
    <SidebarProvider>
      <AppSidebar />
      <main className="flex-1 overflow-auto bg-background p-6">
        <Outlet />
      </main>
    </SidebarProvider>
  );
}
