"use client";

/**
 * useBackendOrg — returns the current user's organization from our backend DB.
 *
 * Why this exists: Clerk's useOrganization() returns Clerk's own org ID
 * (format: org_xxxx), but our backend stores orgs with PostgreSQL UUIDs.
 * This hook bridges that gap by calling GET /users/me/organizations.
 */

import { useState, useEffect, useCallback, useRef } from "react";
import { useAuth } from "@clerk/nextjs";
import { apiClient } from "@/lib/api-client";

export interface BackendOrg {
  org_id: string;   // PostgreSQL UUID — use this for all backend API calls
  org_name: string;
  org_slug: string;
  role: string;
  plan: string;
  max_seats: number;
}

interface UseBackendOrgResult {
  org: BackendOrg | null;
  orgId: string | null;   // Shortcut for org?.org_id
  isLoaded: boolean;
  error: string | null;
  refetch: () => void;
}

export function useBackendOrg(): UseBackendOrgResult {
  const { getToken, isSignedIn } = useAuth();
  const [org, setOrg] = useState<BackendOrg | null>(null);
  const [isLoaded, setIsLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fetchingRef = useRef(false);

  const fetchOrg = useCallback(async () => {
    if (fetchingRef.current) return;
    fetchingRef.current = true;
    try {
      const token = await getToken();
      if (!token) {
        setIsLoaded(true);
        return;
      }
      const orgs = await apiClient.get<BackendOrg[]>("/users/me/organizations", token);
      setOrg(orgs[0] ?? null);
      setError(null);
    } catch (e: unknown) {
      setError((e as Error).message ?? "Failed to load organization");
    } finally {
      setIsLoaded(true);
      fetchingRef.current = false;
    }
  }, [getToken]);

  useEffect(() => {
    if (isSignedIn) {
      fetchOrg();
    } else if (isSignedIn === false) {
      setIsLoaded(true);
    }
  }, [isSignedIn, fetchOrg]);

  return {
    org,
    orgId: org?.org_id ?? null,
    isLoaded,
    error,
    refetch: fetchOrg,
  };
}
