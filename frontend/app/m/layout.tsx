"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { SidebarProvider, SidebarTrigger } from "@/components/ui/sidebar";
import { MemberSidebar } from "@/components/member/MemberSidebar";
import { isMemberAuthenticated } from "@/lib/member-auth";
import { Loader2 } from "lucide-react";

export default function MemberDashboardLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [checked, setChecked] = useState(false);

  useEffect(() => {
    if (!isMemberAuthenticated()) {
      router.replace("/member-login");
    } else {
      setChecked(true);
    }
  }, [router]);

  if (!checked) {
    return (
      <div className="flex h-screen items-center justify-center">
        <Loader2 className="size-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <SidebarProvider>
      <div className="flex h-screen w-full overflow-hidden">
        <MemberSidebar />
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
