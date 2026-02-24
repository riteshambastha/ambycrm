import { auth } from "@clerk/nextjs/server";
import { redirect } from "next/navigation";
import { ChatWindow } from "@/components/chat/ChatWindow";
import { ConversationListClient } from "@/components/chat/ConversationListClient";

// Server component: only checks authentication.
// The backend org UUID is resolved client-side via useBackendOrg.
export default async function ChatPage() {
  const { userId } = await auth();
  if (!userId) {
    redirect("/sign-in");
  }

  return (
    <div className="flex h-full">
      <ConversationListClient />
      <div className="flex-1 flex flex-col min-w-0">
        <ChatWindow />
      </div>
    </div>
  );
}
