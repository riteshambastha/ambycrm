export const dynamic = "force-dynamic";

import { SidebarProvider, SidebarTrigger } from "@/components/ui/sidebar";
import { AppSidebar } from "@/components/layout/AppSidebar";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <SidebarProvider>
      <div className="flex h-screen w-full overflow-hidden">
        <AppSidebar />
        <main className="flex-1 flex flex-col overflow-hidden">
          <header className="flex h-12 items-center border-b px-4 shrink-0">
            <SidebarTrigger className="-ml-1" />
          </header>
          <div className="flex-1 min-h-0 overflow-hidden">{children}</div>
        </main>
      </div>
    </SidebarProvider>
  );
}
