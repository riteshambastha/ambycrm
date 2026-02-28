"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Loader2, MessageSquare, Building2, ArrowLeft } from "lucide-react";
import { useMemberAuth } from "@/lib/hooks/useMemberAuth";

interface OrgOption {
  org_id: string;
  org_name: string;
  employee_id: string;
  employee_name: string;
}

export default function MemberLoginPage() {
  const router = useRouter();
  const { isAuthenticated, isLoading: authLoading, login, selectOrg } = useMemberAuth();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Org selection state
  const [showOrgPicker, setShowOrgPicker] = useState(false);
  const [selectionToken, setSelectionToken] = useState<string | null>(null);
  const [orgs, setOrgs] = useState<OrgOption[]>([]);
  const [selectingOrgId, setSelectingOrgId] = useState<string | null>(null);

  useEffect(() => {
    if (!authLoading && isAuthenticated) {
      router.replace("/m/chat");
    }
  }, [authLoading, isAuthenticated, router]);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setIsSubmitting(true);

    const result = await login(email, password);
    setIsSubmitting(false);

    if (result.success) {
      router.replace("/m/chat");
      return;
    }

    if (result.requiresOrgSelection && result.orgs && result.selectionToken) {
      setShowOrgPicker(true);
      setSelectionToken(result.selectionToken);
      setOrgs(result.orgs);
      return;
    }

    setError(result.error || "Login failed");
  };

  const handleSelectOrg = async (orgId: string) => {
    if (!selectionToken) return;
    setSelectingOrgId(orgId);
    setError(null);

    const result = await selectOrg(selectionToken, orgId);
    setSelectingOrgId(null);

    if (result.success) {
      router.replace("/m/chat");
      return;
    }

    setError(result.error || "Failed to select organization");
  };

  if (authLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-background to-muted">
        <Loader2 className="size-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-background to-muted p-4">
      <div className="w-full max-w-md space-y-6">
        <div className="text-center space-y-2">
          <div className="inline-flex items-center justify-center size-12 rounded-xl bg-primary mb-2">
            <MessageSquare className="size-6 text-primary-foreground" />
          </div>
          <h1 className="text-3xl font-bold tracking-tight">humAInly</h1>
          <p className="text-muted-foreground text-sm">
            Member login &mdash; access your own data
          </p>
        </div>

        <Card>
          {showOrgPicker ? (
            <>
              <CardHeader>
                <CardTitle className="text-lg">Select Organization</CardTitle>
                <CardDescription>
                  Your account is associated with multiple organizations.
                  Choose which one to log into.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                {orgs.map((org) => (
                  <Button
                    key={org.org_id}
                    variant="outline"
                    className="w-full justify-start gap-3 h-auto py-3"
                    disabled={selectingOrgId !== null}
                    onClick={() => handleSelectOrg(org.org_id)}
                  >
                    {selectingOrgId === org.org_id ? (
                      <Loader2 className="size-4 animate-spin shrink-0" />
                    ) : (
                      <Building2 className="size-4 shrink-0" />
                    )}
                    <div className="text-left">
                      <div className="font-medium">{org.org_name}</div>
                      <div className="text-xs text-muted-foreground">{org.employee_name}</div>
                    </div>
                  </Button>
                ))}

                {error && (
                  <p className="text-sm text-destructive text-center">{error}</p>
                )}

                <Button
                  variant="ghost"
                  size="sm"
                  className="w-full mt-2"
                  onClick={() => {
                    setShowOrgPicker(false);
                    setSelectionToken(null);
                    setOrgs([]);
                    setError(null);
                  }}
                >
                  <ArrowLeft className="size-3 mr-1" />
                  Back to login
                </Button>
              </CardContent>
            </>
          ) : (
            <>
              <CardHeader>
                <CardTitle className="text-lg">Sign in</CardTitle>
                <CardDescription>
                  Enter the credentials provided by your administrator
                </CardDescription>
              </CardHeader>
              <CardContent>
                <form onSubmit={handleLogin} className="space-y-4">
                  <div className="space-y-2">
                    <Label htmlFor="email">Email address</Label>
                    <Input
                      id="email"
                      type="email"
                      placeholder="you@company.com"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      required
                      autoComplete="email"
                      autoFocus
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="password">Password</Label>
                    <Input
                      id="password"
                      type="password"
                      placeholder="Enter your password"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      required
                      autoComplete="current-password"
                    />
                  </div>

                  {error && (
                    <p className="text-sm text-destructive">{error}</p>
                  )}

                  <Button type="submit" className="w-full" disabled={isSubmitting}>
                    {isSubmitting && <Loader2 className="size-4 mr-2 animate-spin" />}
                    Sign in
                  </Button>
                </form>
              </CardContent>
            </>
          )}
        </Card>

        <p className="text-center text-xs text-muted-foreground">
          Admin?{" "}
          <a href="/sign-in" className="underline hover:text-foreground transition-colors">
            Sign in here
          </a>
        </p>
      </div>
    </div>
  );
}
