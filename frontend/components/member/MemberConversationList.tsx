"use client";

import { useCallback, useEffect, useState } from "react";
import { memberApiClient } from "@/lib/member-api-client";
import { ConversationList, type Conversation } from "@/components/chat/ConversationList";

export function MemberConversationList() {
  const [conversations, setConversations] = useState<Conversation[]>([]);

  const load = useCallback(async () => {
    try {
      const data = await memberApiClient.get<Conversation[]>(
        "/member/chat/conversations"
      );
      setConversations(data);
    } catch {
      // fail silently
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const handleDelete = useCallback(async (convId: string) => {
    await memberApiClient.delete(`/member/chat/conversations/${convId}`);
    setConversations((prev) => prev.filter((c) => c.id !== convId));
  }, []);

  return (
    <ConversationList
      conversations={conversations}
      orgId=""
      onDelete={handleDelete}
      basePath="/m/chat"
    />
  );
}
