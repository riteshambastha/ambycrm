"use client";

import { useCallback, useEffect, useState } from "react";
import { useAuth } from "@clerk/nextjs";
import { useBackendOrg } from "@/lib/hooks/useBackendOrg";
import { apiClient } from "@/lib/api-client";
import { MemberTable, type Member } from "@/components/settings/MemberTable";
import { InviteUserModal } from "@/components/settings/InviteUserModal";
import { Skeleton } from "@/components/ui/skeleton";
import { Users } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export default function MembersPage() {
  const { getToken } = useAuth();
  const { orgId, org, isLoaded } = useBackendOrg();
  const [members, setMembers] = useState<Member[]>([]);
  const [loading, setLoading] = useState(true);

  // Role comes directly from useBackendOrg — no need to search the members list
  const isAdmin = org?.role === "org_admin";

  const load = useCallback(async () => {
    const token = await getToken();
    if (!token || !orgId) return;
    try {
      const data = await apiClient.get<Member[]>(`/organizations/${orgId}/members`, token);
      setMembers(data);
    } finally {
      setLoading(false);
    }
  }, [getToken, orgId]);

  useEffect(() => {
    if (isLoaded && orgId) load();
    else if (isLoaded && !orgId) setLoading(false);
  }, [isLoaded, orgId, load]);

  return (
    <div className="p-6 max-w-4xl mx-auto space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Users className="size-6" />
            Team Members
          </h1>
          <p className="text-muted-foreground text-sm mt-1">
            Manage your organization's members and their roles.
          </p>
        </div>
        {isAdmin && orgId && (
          <InviteUserModal orgId={orgId} onInvited={load} />
        )}
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            {members.length} Member{members.length !== 1 ? "s" : ""}
          </CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="space-y-3">
              {Array.from({ length: 4 }).map((_, i) => (
                <Skeleton key={i} className="h-12 rounded" />
              ))}
            </div>
          ) : (
            <MemberTable
              members={members}
              orgId={orgId!}
              canManage={isAdmin}
              onRefresh={load}
            />
          )}
        </CardContent>
      </Card>
    </div>
  );
}
