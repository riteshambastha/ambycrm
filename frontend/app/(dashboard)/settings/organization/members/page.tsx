"use client";

import { useCallback, useEffect, useState } from "react";
import { useAuth } from "@clerk/nextjs";
import { useBackendOrg } from "@/lib/hooks/useBackendOrg";
import { apiClient } from "@/lib/api-client";
import { MemberTable, type Member } from "@/components/settings/MemberTable";
import { InviteUserModal } from "@/components/settings/InviteUserModal";
import { AddEmployeeModal } from "@/components/settings/AddEmployeeModal";
import { EmployeeTable, type OrgEmployee } from "@/components/settings/EmployeeTable";
import { Skeleton } from "@/components/ui/skeleton";
import { Users, Mail } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

export default function MembersPage() {
  const { getToken } = useAuth();
  const { orgId, org, isLoaded } = useBackendOrg();
  const [members, setMembers] = useState<Member[]>([]);
  const [employees, setEmployees] = useState<OrgEmployee[]>([]);
  const [loading, setLoading] = useState(true);
  const [empLoading, setEmpLoading] = useState(true);

  const isAdmin = org?.role === "org_admin";

  const loadMembers = useCallback(async () => {
    const token = await getToken();
    if (!token || !orgId) return;
    try {
      const data = await apiClient.get<Member[]>(`/organizations/${orgId}/members`, token);
      setMembers(data);
    } finally {
      setLoading(false);
    }
  }, [getToken, orgId]);

  const loadEmployees = useCallback(async () => {
    const token = await getToken();
    if (!token || !orgId) return;
    try {
      const data = await apiClient.get<OrgEmployee[]>(`/organizations/${orgId}/employees`, token);
      setEmployees(data);
    } finally {
      setEmpLoading(false);
    }
  }, [getToken, orgId]);

  useEffect(() => {
    if (isLoaded && orgId) {
      loadMembers();
      loadEmployees();
    } else if (isLoaded && !orgId) {
      setLoading(false);
      setEmpLoading(false);
    }
  }, [isLoaded, orgId, loadMembers, loadEmployees]);

  return (
    <div className="p-6 max-w-4xl mx-auto space-y-8">

      {/* ── AmbyChat Users ─────────────────────────────────────────────── */}
      <div>
        <div className="flex items-start justify-between mb-4">
          <div>
            <h1 className="text-2xl font-bold flex items-center gap-2">
              <Users className="size-6" />
              Team Members
            </h1>
            <p className="text-muted-foreground text-sm mt-1">
              People with humAInly accounts in your organization.
            </p>
          </div>
          {isAdmin && orgId && (
            <InviteUserModal orgId={orgId} onInvited={loadMembers} />
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
                {Array.from({ length: 3 }).map((_, i) => (
                  <Skeleton key={i} className="h-12 rounded" />
                ))}
              </div>
            ) : (
              <MemberTable
                members={members}
                orgId={orgId!}
                canManage={isAdmin}
                onRefresh={loadMembers}
              />
            )}
          </CardContent>
        </Card>
      </div>

      {/* ── M365 Employees ─────────────────────────────────────────────── */}
      <div>
        <div className="flex items-start justify-between mb-4">
          <div>
            <h2 className="text-xl font-bold flex items-center gap-2">
              <Mail className="size-5" />
              Microsoft 365 Employees
            </h2>
            <p className="text-muted-foreground text-sm mt-1">
              Register employees so the AI can query their email. No humAInly
              account needed — just their name and work email.
            </p>
          </div>
          {isAdmin && orgId && (
            <AddEmployeeModal orgId={orgId} onAdded={loadEmployees} />
          )}
        </div>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">
              {employees.length} Employee{employees.length !== 1 ? "s" : ""}
            </CardTitle>
            <CardDescription className="text-xs">
              In chat, ask: <em>"Show emails for Sarah Johnson"</em> or{" "}
              <em>"Show inbox for sarah@company.com"</em>
            </CardDescription>
          </CardHeader>
          <CardContent>
            {empLoading ? (
              <div className="space-y-3">
                {Array.from({ length: 2 }).map((_, i) => (
                  <Skeleton key={i} className="h-12 rounded" />
                ))}
              </div>
            ) : (
              <EmployeeTable
                employees={employees}
                orgId={orgId!}
                canManage={isAdmin}
                onRefresh={loadEmployees}
              />
            )}
          </CardContent>
        </Card>
      </div>

    </div>
  );
}
