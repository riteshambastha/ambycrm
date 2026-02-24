import { auth } from "@clerk/nextjs/server";
import { redirect } from "next/navigation";
import { ChatWindow } from "@/components/chat/ChatWindow";
import { ConversationListClient } from "@/components/chat/ConversationListClient";

interface ChatConversationPageProps {
  params: Promise<{ id: string }>;
}

export default async function ChatConversationPage({ params }: ChatConversationPageProps) {
  const { orgId } = await auth();
  if (!orgId) redirect("/onboarding");

  const { id } = await params;

  return (
    <div className="flex h-full">
      <ConversationListClient orgId={orgId} />
      <div className="flex-1 flex flex-col min-w-0">
        <ChatWindow orgId={orgId} conversationId={id} />
      </div>
    </div>
  );
}
