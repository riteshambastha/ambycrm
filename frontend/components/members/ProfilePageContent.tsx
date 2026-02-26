"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useAuth } from "@clerk/nextjs";
import { useBackendOrg } from "@/lib/hooks/useBackendOrg";
import { apiClient } from "@/lib/api-client";
import { ProfileHeader } from "./ProfileHeader";
import { LimitControl } from "./LimitControl";
import { EmailsSection } from "./EmailsSection";
import { FilesSection } from "./FilesSection";
import { SalesforceSection } from "./SalesforceSection";
import { MeetingsSection } from "./MeetingsSection";
import { MemberChat } from "./MemberChat";
import { type SectionData } from "./SectionWrapper";
import { type PersonOut } from "./MemberCard";
import { Skeleton } from "@/components/ui/skeleton";

type Section = "emails" | "files" | "salesforce" | "meetings";

interface SectionState {
  loading: boolean;
  data: SectionData | null;
}

const SECTIONS: Section[] = ["emails", "files", "salesforce", "meetings"];

interface ProfilePageContentProps {
  personId: string;
  personType: "member" | "employee";
}

export function ProfilePageContent({ personId, personType }: ProfilePageContentProps) {
  const { getToken } = useAuth();
  const { orgId, org, isLoaded } = useBackendOrg();

  const [person, setPerson] = useState<PersonOut | null>(null);
  const [personLoading, setPersonLoading] = useState(true);
  const [limit, setLimit] = useState(15);

  const [sections, setSections] = useState<Record<Section, SectionState>>({
    emails: { loading: true, data: null },
    files: { loading: true, data: null },
    salesforce: { loading: true, data: null },
    meetings: { loading: true, data: null },
  });

  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const isAdmin = org?.role === "org_admin";

  // Load person info from the dedicated single-person info endpoint
  const loadPerson = useCallback(async () => {
    const token = await getToken();
    if (!token || !orgId) return;
    try {
      const path =
        personType === "member"
          ? `/organizations/${orgId}/members/${personId}/info`
          : `/organizations/${orgId}/employees/${personId}/info`;
      const data = await apiClient.get<PersonOut>(path, token);
      setPerson(data);
    } catch {
      setPerson(null);
    } finally {
      setPersonLoading(false);
    }
  }, [getToken, orgId, personId, personType]);

  // Load one section independently
  const loadSection = useCallback(
    async (section: Section, currentLimit: number) => {
      const token = await getToken();
      if (!token || !orgId) return;

      setSections((prev) => ({
        ...prev,
        [section]: { ...prev[section], loading: true },
      }));

      const path =
        personType === "member"
          ? `/organizations/${orgId}/members/${personId}/sections/${section}?limit=${currentLimit}`
          : `/organizations/${orgId}/employees/${personId}/sections/${section}?limit=${currentLimit}`;

      try {
        const data = await apiClient.get<SectionData>(path, token);
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
    [getToken, orgId, personId, personType]
  );

  // Load all sections in parallel
  const loadAllSections = useCallback(
    (currentLimit: number) => {
      SECTIONS.forEach((s) => loadSection(s, currentLimit));
    },
    [loadSection]
  );

  // Refresh a single section (re-fetches fresh from the connector)
  const refreshSection = useCallback(
    (section: Section) => {
      loadSection(section, limit);
    },
    [loadSection, limit]
  );

  // When limit changes, debounce re-fetch
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
    if (isLoaded && orgId) {
      loadPerson();
      loadAllSections(limit);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isLoaded, orgId]);

  if (personLoading) {
    return (
      <div className="h-full overflow-y-auto">
        <div className="p-6 space-y-4 max-w-7xl mx-auto">
          <Skeleton className="h-8 w-48" />
          <Skeleton className="h-20 rounded-xl" />
          <div className="grid grid-cols-1 lg:grid-cols-[1fr_380px] gap-5">
            <div className="space-y-5">
              {[...Array(4)].map((_, i) => <Skeleton key={i} className="h-32 rounded-xl" />)}
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (!person) {
    return (
      <div className="h-full flex items-center justify-center text-muted-foreground">
        Person not found or you don't have access.
      </div>
    );
  }

  return (
    /* h-full + overflow-y-auto makes this div the scroll container inside the
       dashboard layout's overflow-hidden wrapper */
    <div className="h-full overflow-y-auto">
      <div className="p-6 max-w-7xl mx-auto space-y-5 pb-10">
        {person && <ProfileHeader person={person} isAdmin={isAdmin} />}

        <LimitControl value={limit} onChange={handleLimitChange} />

        <div className="grid grid-cols-1 lg:grid-cols-[1fr_380px] gap-5 items-start">
          {/* Left: Data sections — scrolls with the page */}
          <div className="space-y-5 min-w-0">
            <EmailsSection
              loading={sections.emails.loading}
              data={sections.emails.data}
              onRetry={() => loadSection("emails", limit)}
              onRefresh={() => refreshSection("emails")}
            />
            <FilesSection
              loading={sections.files.loading}
              data={sections.files.data}
              onRetry={() => loadSection("files", limit)}
              onRefresh={() => refreshSection("files")}
            />
            <SalesforceSection
              loading={sections.salesforce.loading}
              data={sections.salesforce.data}
              onRetry={() => loadSection("salesforce", limit)}
              onRefresh={() => refreshSection("salesforce")}
            />
            <MeetingsSection
              loading={sections.meetings.loading}
              data={sections.meetings.data}
              onRetry={() => loadSection("meetings", limit)}
              onRefresh={() => refreshSection("meetings")}
            />
          </div>

          {/* Right: Chat panel — sticks to the top of the scroll container */}
          <div className="lg:sticky lg:top-0 h-[calc(100vh-8rem)]">
            {person && orgId && (
              <MemberChat
                orgId={orgId}
                personId={personId}
                personType={personType}
                displayName={person.display_name}
                workEmail={person.work_email}
              />
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
