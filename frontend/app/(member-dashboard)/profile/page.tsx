"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useMemberAuth } from "@/lib/hooks/useMemberAuth";
import { memberApiClient } from "@/lib/member-api-client";
import { LimitControl } from "@/components/members/LimitControl";
import { EmailsSection } from "@/components/members/EmailsSection";
import { FilesSection } from "@/components/members/FilesSection";
import { SalesforceSection } from "@/components/members/SalesforceSection";
import { MeetingsSection } from "@/components/members/MeetingsSection";
import { type SectionData } from "@/components/members/SectionWrapper";
import { Skeleton } from "@/components/ui/skeleton";
import { User } from "lucide-react";

type Section = "emails" | "files" | "salesforce" | "meetings";

interface SectionState {
  loading: boolean;
  data: SectionData | null;
}

const SECTIONS: Section[] = ["emails", "files", "salesforce", "meetings"];

export default function MemberProfilePage() {
  const { profile, isLoading: authLoading } = useMemberAuth();
  const [limit, setLimit] = useState(15);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const [sections, setSections] = useState<Record<Section, SectionState>>({
    emails: { loading: true, data: null },
    files: { loading: true, data: null },
    salesforce: { loading: true, data: null },
    meetings: { loading: true, data: null },
  });

  const loadSection = useCallback(
    async (section: Section, currentLimit: number) => {
      setSections((prev) => ({
        ...prev,
        [section]: { ...prev[section], loading: true },
      }));

      try {
        const data = await memberApiClient.get<SectionData>(
          `/member/sections/${section}?limit=${currentLimit}`
        );
        setSections((prev) => ({
          ...prev,
          [section]: { loading: false, data },
        }));
      } catch {
        setSections((prev) => ({
          ...prev,
          [section]: {
            loading: false,
            data: {
              connected: false,
              results: [],
              limit: currentLimit,
              error: "Failed to load data. Click retry.",
            },
          },
        }));
      }
    },
    []
  );

  const loadAllSections = useCallback(
    (currentLimit: number) => {
      SECTIONS.forEach((s) => loadSection(s, currentLimit));
    },
    [loadSection]
  );

  const handleLimitChange = useCallback(
    (newLimit: number) => {
      setLimit(newLimit);
      if (debounceRef.current) clearTimeout(debounceRef.current);
      debounceRef.current = setTimeout(() => {
        loadAllSections(newLimit);
      }, 300);
    },
    [loadAllSections]
  );

  useEffect(() => {
    if (!authLoading && profile) {
      loadAllSections(limit);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authLoading, profile]);

  if (authLoading) {
    return (
      <div className="h-full overflow-y-auto">
        <div className="p-6 space-y-4 max-w-5xl mx-auto">
          <Skeleton className="h-8 w-48" />
          <div className="space-y-5">
            {[...Array(4)].map((_, i) => <Skeleton key={i} className="h-32 rounded-xl" />)}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto">
      <div className="p-6 max-w-5xl mx-auto space-y-5 pb-10">
        {/* Profile Header */}
        <div className="flex items-center gap-4 p-4 rounded-xl border bg-card">
          <div className="size-12 rounded-full bg-primary/10 flex items-center justify-center">
            <User className="size-6 text-primary" />
          </div>
          <div>
            <h1 className="text-xl font-semibold">{profile?.name ?? "My Profile"}</h1>
            <p className="text-sm text-muted-foreground">{profile?.email}</p>
            {profile?.org_name && (
              <p className="text-xs text-muted-foreground mt-0.5">{profile.org_name}</p>
            )}
          </div>
        </div>

        <LimitControl value={limit} onChange={handleLimitChange} />

        <div className="space-y-5">
          <EmailsSection
            loading={sections.emails.loading}
            data={sections.emails.data}
            onRetry={() => loadSection("emails", limit)}
            onRefresh={() => loadSection("emails", limit)}
          />
          <FilesSection
            loading={sections.files.loading}
            data={sections.files.data}
            onRetry={() => loadSection("files", limit)}
            onRefresh={() => loadSection("files", limit)}
          />
          <SalesforceSection
            loading={sections.salesforce.loading}
            data={sections.salesforce.data}
            onRetry={() => loadSection("salesforce", limit)}
            onRefresh={() => loadSection("salesforce", limit)}
          />
          <MeetingsSection
            loading={sections.meetings.loading}
            data={sections.meetings.data}
            onRetry={() => loadSection("meetings", limit)}
            onRefresh={() => loadSection("meetings", limit)}
          />
        </div>
      </div>
    </div>
  );
}
