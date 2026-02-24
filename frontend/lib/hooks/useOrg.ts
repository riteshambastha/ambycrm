"use client";

import { useOrganization } from "@clerk/nextjs";

export function useOrg() {
  const { organization, isLoaded } = useOrganization();
  return {
    org: organization,
    orgId: organization?.id,
    orgName: organization?.name,
    isLoaded,
  };
}
