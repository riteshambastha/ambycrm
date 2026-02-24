"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@clerk/nextjs";
import { apiClient } from "@/lib/api-client";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Shield, Building2 } from "lucide-react";

interface OrgSummary {
  id: string;
  name: string;
  slug: string;
  plan: string;
  max_seats: number;
  is_active: boolean;
  created_at: string;
}

export default function AdminOrganizationsPage() {
  const { getToken } = useAuth();
  const [orgs, setOrgs] = useState<OrgSummary[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const load = async () => {
      const token = await getToken();
      if (!token) return;
      try {
        // Super admin endpoint - returns all orgs
        const data = await apiClient.get<OrgSummary[]>("/admin/organizations", token);
        setOrgs(data);
      } catch {
        // fail silently if not super admin
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [getToken]);

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <Shield className="size-6" />
          Super Admin — Organizations
        </h1>
        <p className="text-muted-foreground text-sm mt-1">
          Platform-level view of all organizations.
        </p>
      </div>

      {loading ? (
        <div className="space-y-3">
          {Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-20 rounded-xl" />)}
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {orgs.map((org) => (
            <Card key={org.id}>
              <CardHeader className="pb-2">
                <CardTitle className="flex items-center gap-2 text-base">
                  <Building2 className="size-4" />
                  {org.name}
                  {!org.is_active && <Badge variant="destructive" className="text-xs">Inactive</Badge>}
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-1 text-sm text-muted-foreground">
                <p>Slug: <span className="font-mono text-xs">{org.slug}</span></p>
                <p>Plan: <Badge variant="outline" className="text-xs">{org.plan}</Badge></p>
                <p>Seats: {org.max_seats}</p>
                <p>Created: {new Date(org.created_at).toLocaleDateString()}</p>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
