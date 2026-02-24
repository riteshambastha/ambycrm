"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@clerk/nextjs";
import { apiClient } from "@/lib/api-client";
import { ConversationList, type Conversation } from "./ConversationList";

export function ConversationListClient({ orgId }: { orgId: string }) {
  const { getToken } = useAuth();
  const [conversations, setConversations] = useState<Conversation[]>([]);

  useEffect(() => {
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
        // fail silently
      }
    };
    load();
  }, [orgId, getToken]);

  return <ConversationList conversations={conversations} orgId={orgId} />;
}
