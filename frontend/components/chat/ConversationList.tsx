"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { MessageSquare, Plus, Archive } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";
import { formatDistanceToNow } from "date-fns";

export interface Conversation {
  id: string;
  title: string | null;
  updated_at: string;
}

interface ConversationListProps {
  conversations: Conversation[];
  orgId: string;
}

export function ConversationList({ conversations, orgId }: ConversationListProps) {
  const pathname = usePathname();

  return (
    <div className="flex flex-col h-full border-r w-64 shrink-0">
      <div className="p-3 border-b">
        <Button asChild className="w-full" size="sm">
          <Link href="/chat">
            <Plus className="size-4 mr-2" />
            New Chat
          </Link>
        </Button>
      </div>
      <ScrollArea className="flex-1">
        <div className="p-2 space-y-1">
          {conversations.length === 0 && (
            <p className="text-xs text-muted-foreground text-center py-8">
              No conversations yet
            </p>
          )}
          {conversations.map((conv) => (
            <Link
              key={conv.id}
              href={`/chat/${conv.id}`}
              className={cn(
                "flex items-start gap-2 rounded-lg px-3 py-2 text-sm hover:bg-accent transition-colors",
                pathname === `/chat/${conv.id}` && "bg-accent"
              )}
            >
              <MessageSquare className="size-3.5 mt-0.5 shrink-0 text-muted-foreground" />
              <div className="min-w-0 flex-1">
                <p className="truncate font-medium leading-tight">
                  {conv.title ?? "New conversation"}
                </p>
                <p className="text-xs text-muted-foreground">
                  {formatDistanceToNow(new Date(conv.updated_at), { addSuffix: true })}
                </p>
              </div>
            </Link>
          ))}
        </div>
      </ScrollArea>
    </div>
  );
}
