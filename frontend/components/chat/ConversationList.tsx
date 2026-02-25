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
  const [hoveredId, setHoveredId] = useState<string | null>(null);

  const handleDelete = async (e: React.MouseEvent, convId: string) => {
    e.preventDefault();
    e.stopPropagation();
    setDeletingId(convId);
    try {
      await onDelete(convId);
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
      <ScrollArea className="flex-1 h-0">
        <div className="p-2 space-y-1">
          {conversations.length === 0 && (
            <p className="text-xs text-muted-foreground text-center py-8">
              No conversations yet
            </p>
          )}
          {conversations.map((conv) => {
            const isHovered = hoveredId === conv.id;
            const isDeleting = deletingId === conv.id;
            const isActive = pathname === `/chat/${conv.id}`;

            return (
              <div
                key={conv.id}
                onMouseEnter={() => setHoveredId(conv.id)}
                onMouseLeave={() => setHoveredId(null)}
                className={cn(
                  "flex items-center rounded-lg text-sm transition-colors",
                  isActive ? "bg-accent" : "hover:bg-accent"
                )}
              >
                {/* Link takes all space minus the fixed-width delete slot */}
                <Link
                  href={`/chat/${conv.id}`}
                  className="flex items-center gap-2 min-w-0 flex-1 px-3 py-2"
                >
                  <MessageSquare className="size-3.5 shrink-0 text-muted-foreground" />
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-medium leading-tight text-sm">
                      {conv.title ?? "New conversation"}
                    </p>
                    <p className="text-xs text-muted-foreground truncate">
                      {formatDistanceToNow(new Date(conv.updated_at), { addSuffix: true })}
                    </p>
                  </div>
                </Link>

                {/* Delete — always reserves space, visible on row hover */}
                <button
                  onClick={(e) => handleDelete(e, conv.id)}
                  disabled={isDeleting}
                  style={{ opacity: isHovered || isDeleting ? 1 : 0 }}
                  className="shrink-0 mr-2 p-1 rounded text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-opacity"
                  title="Delete conversation"
                >
                  {isDeleting ? (
                    <Loader2 className="size-3.5 animate-spin" />
                  ) : (
                    <Trash2 className="size-3.5" />
                  )}
                </button>
              </div>
            );
          })}
        </div>
      </ScrollArea>
    </div>
  );
}
