"use client";

import { useCallback, useEffect, useState } from "react";
import { useAuth } from "@clerk/nextjs";
import { apiClient } from "@/lib/api-client";
import { useBackendOrg } from "@/lib/hooks/useBackendOrg";
import { ConversationList, type Conversation } from "./ConversationList";

export function ConversationListClient() {
  const { getToken } = useAuth();
  const { orgId, isLoaded } = useBackendOrg();
  const [conversations, setConversations] = useState<Conversation[]>([]);

  const load = useCallback(async () => {
    if (!orgId) return;
    const token = await getToken();
    if (!token) return;
    try {
      const data = await apiClient.get<Conversation[]>(
        `/chat/${orgId}/conversations`,
        token
      );
      setConversations(data);
    } catch {
      // fail silently — conversation list is non-critical
    }
  }, [orgId, getToken]);

  useEffect(() => {
    if (isLoaded && orgId) load();
  }, [isLoaded, orgId, load]);

  const handleDelete = useCallback(async (convId: string) => {
    const token = await getToken();
    if (!token || !orgId) return;
    await apiClient.delete(`/chat/${orgId}/conversations/${convId}`, token);
    // Remove from local state immediately
    setConversations((prev) => prev.filter((c) => c.id !== convId));
  }, [getToken, orgId]);

  return (
    <ConversationList
      conversations={conversations}
      orgId={orgId ?? ""}
      onDelete={handleDelete}
    />
  );
}
