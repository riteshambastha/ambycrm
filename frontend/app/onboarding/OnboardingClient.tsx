"use client";

import { useState } from "react";
import { useAuth, useUser } from "@clerk/nextjs";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Building2, Loader2, ArrowRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { apiClient } from "@/lib/api-client";

function toSlug(name: string) {
  return name
    .toLowerCase()
    .replace(/[^a-z0-9\s-]/g, "")
    .trim()
    .replace(/\s+/g, "-");
}

export function OnboardingClient() {
  const { getToken } = useAuth();
  const { user } = useUser();
  const router = useRouter();
  const [orgName, setOrgName] = useState("");
  const [slug, setSlug] = useState("");
  const [loading, setLoading] = useState(false);

  const handleNameChange = (val: string) => {
    setOrgName(val);
    setSlug(toSlug(val));
  };

  const handleCreate = async () => {
    if (!orgName || !slug) return;
    setLoading(true);
    try {
      const token = await getToken();
      if (!token) throw new Error("Not authenticated");
      await apiClient.post("/organizations", { name: orgName, slug }, token);
      toast.success("Organization created!");
      router.push("/chat");
    } catch (err: unknown) {
      toast.error((err as Error).message ?? "Failed to create organization");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-background to-muted p-4">
      <Card className="w-full max-w-md">
        <CardHeader className="text-center">
          <div className="size-12 rounded-2xl bg-primary/10 flex items-center justify-center mx-auto mb-2">
            <Building2 className="size-6 text-primary" />
          </div>
          <CardTitle className="text-2xl">Create your organization</CardTitle>
          <CardDescription>
            Welcome{user?.firstName ? `, ${user.firstName}` : ""}! Set up your workspace to get started.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="orgName">Organization Name</Label>
            <Input
              id="orgName"
              placeholder="Acme Corp"
              value={orgName}
              onChange={(e) => handleNameChange(e.target.value)}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="slug">URL Slug</Label>
            <div className="flex items-center gap-2">
              <span className="text-xs text-muted-foreground shrink-0">amby.chat/</span>
              <Input
                id="slug"
                placeholder="acme-corp"
                value={slug}
                onChange={(e) => setSlug(toSlug(e.target.value))}
                className="font-mono text-sm"
              />
            </div>
          </div>
          <Button
            className="w-full"
            onClick={handleCreate}
            disabled={loading || !orgName || !slug}
          >
            {loading ? (
              <Loader2 className="size-4 mr-2 animate-spin" />
            ) : (
              <ArrowRight className="size-4 mr-2" />
            )}
            Create Organization
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
