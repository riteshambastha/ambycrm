"use client";

import { useAuth } from "@clerk/nextjs";

export function useApiToken() {
  const { getToken } = useAuth();
  return { getToken: () => getToken() };
}
