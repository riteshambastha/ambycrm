"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { MessageSquare, Plus, Trash2, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";
import { formatDistanceToNow } from "date-fns";
import { useState } from "react";

export interface Conversation {
  id: string;
  title: string | null;
  updated_at: string;
}

interface ConversationListProps {
  conversations: Conversation[];
  orgId: string;
  onDelete: (id: string) => Promise<void>;
}

export function ConversationList({ conversations, orgId, onDelete }: ConversationListProps) {
  const pathname = usePathname();
  const router = useRouter();
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const handleDelete = async (e: React.MouseEvent, convId: string) => {
    e.preventDefault();
    e.stopPropagation();
    setDeletingId(convId);
    try {
      await onDelete(convId);
      // If we deleted the currently open conversation, go back to /chat
      if (pathname === `/chat/${convId}`) {
        router.push("/chat");
      }
    } finally {
      setDeletingId(null);
    }
  };

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
            <div
              key={conv.id}
              className={cn(
                "group relative flex items-start gap-2 rounded-lg px-3 py-2 text-sm hover:bg-accent transition-colors",
                pathname === `/chat/${conv.id}` && "bg-accent"
              )}
            >
              <Link
                href={`/chat/${conv.id}`}
                className="flex items-start gap-2 min-w-0 flex-1"
              >
                <MessageSquare className="size-3.5 mt-0.5 shrink-0 text-muted-foreground" />
                <div className="min-w-0 flex-1">
                  <p className="truncate font-medium leading-tight pr-6">
                    {conv.title ?? "New conversation"}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {formatDistanceToNow(new Date(conv.updated_at), { addSuffix: true })}
                  </p>
                </div>
              </Link>

              {/* Delete button — visible on hover */}
              <button
                onClick={(e) => handleDelete(e, conv.id)}
                disabled={deletingId === conv.id}
                className={cn(
                  "absolute right-2 top-2 p-1 rounded opacity-0 group-hover:opacity-100",
                  "text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-all"
                )}
                title="Delete conversation"
              >
                {deletingId === conv.id ? (
                  <Loader2 className="size-3 animate-spin" />
                ) : (
                  <Trash2 className="size-3" />
                )}
              </button>
            </div>
          ))}
        </div>
      </ScrollArea>
    </div>
  );
}
