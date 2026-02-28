"use client";

import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import {
  getMemberToken,
  setMemberToken,
  clearMemberToken,
  isMemberAuthenticated,
  getMemberPayload,
} from "@/lib/member-auth";
import { memberApiClient } from "@/lib/member-api-client";

interface MemberProfile {
  employee_id: string;
  name: string;
  email: string;
  org_id: string;
  org_name: string;
  is_login_enabled: boolean;
}

interface OrgOption {
  org_id: string;
  org_name: string;
  employee_id: string;
  employee_name: string;
}

interface LoginResult {
  success: boolean;
  requiresOrgSelection?: boolean;
  selectionToken?: string;
  orgs?: OrgOption[];
  error?: string;
}

export function useMemberAuth() {
  const router = useRouter();
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [profile, setProfile] = useState<MemberProfile | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const authenticated = isMemberAuthenticated();
    setIsAuthenticated(authenticated);
    if (authenticated) {
      memberApiClient
        .get<MemberProfile>("/member-auth/me")
        .then(setProfile)
        .catch(() => {
          clearMemberToken();
          setIsAuthenticated(false);
        })
        .finally(() => setIsLoading(false));
    } else {
      setIsLoading(false);
    }
  }, []);

  const login = useCallback(
    async (email: string, password: string): Promise<LoginResult> => {
      try {
        const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
        const res = await fetch(`${API_BASE}/api/v1/member-auth/login`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email, password }),
        });

        if (!res.ok) {
          const data = await res.json().catch(() => ({ detail: "Login failed" }));
          return { success: false, error: data.detail || "Login failed" };
        }

        const data = await res.json();

        if (data.requires_org_selection) {
          return {
            success: false,
            requiresOrgSelection: true,
            selectionToken: data.selection_token,
            orgs: data.orgs,
          };
        }

        setMemberToken(data.token);
        setIsAuthenticated(true);
        setProfile({
          employee_id: data.employee_id,
          name: data.employee_name,
          email: data.email,
          org_id: data.org_id,
          org_name: data.org_name,
          is_login_enabled: true,
        });
        return { success: true };
      } catch (err) {
        return { success: false, error: (err as Error).message };
      }
    },
    [],
  );

  const selectOrg = useCallback(
    async (selectionToken: string, orgId: string): Promise<LoginResult> => {
      try {
        const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
        const res = await fetch(`${API_BASE}/api/v1/member-auth/select-org`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ selection_token: selectionToken, org_id: orgId }),
        });

        if (!res.ok) {
          const data = await res.json().catch(() => ({ detail: "Org selection failed" }));
          return { success: false, error: data.detail || "Org selection failed" };
        }

        const data = await res.json();
        setMemberToken(data.token);
        setIsAuthenticated(true);
        setProfile({
          employee_id: data.employee_id,
          name: data.employee_name,
          email: data.email,
          org_id: data.org_id,
          org_name: data.org_name,
          is_login_enabled: true,
        });
        return { success: true };
      } catch (err) {
        return { success: false, error: (err as Error).message };
      }
    },
    [],
  );

  const logout = useCallback(() => {
    clearMemberToken();
    setIsAuthenticated(false);
    setProfile(null);
    router.push("/member-login");
  }, [router]);

  const changePassword = useCallback(
    async (currentPassword: string, newPassword: string): Promise<{ success: boolean; error?: string }> => {
      try {
        const data = await memberApiClient.patch<{ token: string }>("/member-auth/change-password", {
          current_password: currentPassword,
          new_password: newPassword,
        });
        setMemberToken(data.token);
        return { success: true };
      } catch (err) {
        return { success: false, error: (err as Error).message };
      }
    },
    [],
  );

  return {
    isAuthenticated,
    isLoading,
    profile,
    orgId: profile?.org_id ?? getMemberPayload()?.org_id ?? null,
    login,
    selectOrg,
    logout,
    changePassword,
  };
}
