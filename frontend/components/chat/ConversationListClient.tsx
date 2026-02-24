"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@clerk/nextjs";
import { apiClient } from "@/lib/api-client";
import { useBackendOrg } from "@/lib/hooks/useBackendOrg";
import { ConversationList, type Conversation } from "./ConversationList";

export function ConversationListClient() {
  const { getToken } = useAuth();
  const { orgId, isLoaded } = useBackendOrg();
  const [conversations, setConversations] = useState<Conversation[]>([]);

  useEffect(() => {
    if (!isLoaded || !orgId) return;
    const load = async () => {
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
    };
    load();
  }, [isLoaded, orgId, getToken]);

  return <ConversationList conversations={conversations} orgId={orgId ?? ""} />;
}
