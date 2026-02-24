import { auth } from "@clerk/nextjs/server";
import { redirect } from "next/navigation";
import { ChatWindow } from "@/components/chat/ChatWindow";
import { ConversationList } from "@/components/chat/ConversationList";

// This is a server component — it can access the org from Clerk session claims
export default async function ChatPage() {
  const { orgId } = await auth();
  if (!orgId) {
    redirect("/settings/organization");
  }

  return (
    <div className="flex h-full">
      {/* Sidebar: rendered client-side in a wrapper */}
      <ConversationListWrapper orgId={orgId} />
      <div className="flex-1 flex flex-col min-w-0">
        <ChatWindow orgId={orgId} />
      </div>
    </div>
  );
}

// Client wrapper to fetch conversations
import { ConversationListClient } from "@/components/chat/ConversationListClient";

function ConversationListWrapper({ orgId }: { orgId: string }) {
  return <ConversationListClient orgId={orgId} />;
}
