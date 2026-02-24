"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@clerk/nextjs";
import { useOrg } from "@/lib/hooks/useOrg";
import { toast } from "sonner";
import { Loader2, Save, Building2, Users, CreditCard } from "lucide-react";
import Link from "next/link";
import { apiClient } from "@/lib/api-client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";

interface OrgData {
  id: string;
  name: string;
  slug: string;
  plan: string;
  max_seats: int;
}

// TypeScript note: using `any` for simplicity in the plan value
type int = number;

export default function OrganizationSettingsPage() {
  const { getToken } = useAuth();
  const { orgId, isLoaded } = useOrg();
  const [orgName, setOrgName] = useState("");
  const [orgData, setOrgData] = useState<OrgData | null>(null);
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const load = async () => {
      const token = await getToken();
      if (!token || !orgId) return;
      try {
        const data = await apiClient.get<OrgData>(`/organizations/${orgId}`, token);
        setOrgData(data);
        setOrgName(data.name);
      } finally {
        setLoading(false);
      }
    };
    if (isLoaded && orgId) load();
  }, [isLoaded, orgId, getToken]);

  const handleSave = async () => {
    setSaving(true);
    try {
      const token = await getToken();
      await apiClient.patch(`/organizations/${orgId}`, { name: orgName }, token!);
      toast.success("Organization settings saved");
    } catch {
      toast.error("Failed to save settings");
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-48">
        <Loader2 className="size-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="p-6 max-w-2xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <Building2 className="size-6" />
          Organization Settings
        </h1>
        <p className="text-muted-foreground text-sm mt-1">
          Manage your organization's profile and subscription.
        </p>
      </div>

      {/* Quick nav */}
      <div className="grid grid-cols-2 gap-3">
        <Link href="/settings/organization/members">
          <Card className="cursor-pointer hover:border-primary transition-colors">
            <CardContent className="flex items-center gap-3 p-4">
              <Users className="size-5 text-muted-foreground" />
              <div>
                <p className="text-sm font-medium">Team Members</p>
                <p className="text-xs text-muted-foreground">Invite & manage</p>
              </div>
            </CardContent>
          </Card>
        </Link>
        <Link href="/settings/organization/billing">
          <Card className="cursor-pointer hover:border-primary transition-colors">
            <CardContent className="flex items-center gap-3 p-4">
              <CreditCard className="size-5 text-muted-foreground" />
              <div>
                <p className="text-sm font-medium">Billing</p>
                <p className="text-xs text-muted-foreground">Plan & seats</p>
              </div>
            </CardContent>
          </Card>
        </Link>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>General</CardTitle>
          <CardDescription>Update your organization's display name.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="orgName">Organization Name</Label>
            <Input
              id="orgName"
              value={orgName}
              onChange={(e) => setOrgName(e.target.value)}
            />
          </div>
          <div className="space-y-2">
            <Label>Slug</Label>
            <Input value={orgData?.slug ?? ""} readOnly className="bg-muted cursor-not-allowed" />
          </div>
          <Button onClick={handleSave} disabled={saving}>
            {saving ? <Loader2 className="size-4 mr-2 animate-spin" /> : <Save className="size-4 mr-2" />}
            Save Changes
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Subscription</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-sm">Current Plan</span>
            <Badge>{orgData?.plan ?? "free"}</Badge>
          </div>
          <Separator />
          <div className="flex items-center justify-between">
            <span className="text-sm">Seat Limit</span>
            <span className="text-sm font-medium">{orgData?.max_seats} seats</span>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
