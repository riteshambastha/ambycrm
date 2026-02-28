"use client";

import { use } from "react";
import { MemberChatWindow } from "@/components/member/MemberChatWindow";
import { MemberConversationList } from "@/components/member/MemberConversationList";

export default function MemberConversationPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);

  return (
    <div className="flex h-full">
      <MemberConversationList />
      <div className="flex-1 flex flex-col min-w-0">
        <MemberChatWindow conversationId={id} />
      </div>
    </div>
  );
}
