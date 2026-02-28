"use client";

import { MemberChatWindow } from "@/components/member/MemberChatWindow";
import { MemberConversationList } from "@/components/member/MemberConversationList";

export default function MemberChatPage() {
  return (
    <div className="flex h-full">
      <MemberConversationList />
      <div className="flex-1 flex flex-col min-w-0">
        <MemberChatWindow />
      </div>
    </div>
  );
}
