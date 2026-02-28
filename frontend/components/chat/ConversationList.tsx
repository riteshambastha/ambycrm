"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { MessageSquare, Plus, Trash2, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
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
  basePath?: string;
}

export function ConversationList({ conversations, orgId, onDelete, basePath = "/chat" }: ConversationListProps) {
  const pathname = usePathname();
  const router = useRouter();
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const handleDelete = async (e: React.MouseEvent, convId: string) => {
    e.preventDefault();
    e.stopPropagation();
    setDeletingId(convId);
    try {
      await onDelete(convId);
      if (pathname === `${basePath}/${convId}`) {
        router.push(basePath);
      }
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <div className="flex flex-col h-full border-r w-64 shrink-0">
      <div className="p-3 border-b">
        <Button asChild className="w-full" size="sm">
          <Link href={basePath}>
            <Plus className="size-4 mr-2" />
            New Chat
          </Link>
        </Button>
      </div>

      {/* Plain scrollable list — avoids Radix ScrollArea clipping issues */}
      <div className="flex-1 overflow-y-auto min-h-0 p-2 space-y-0.5">
        {conversations.length === 0 && (
          <p className="text-xs text-muted-foreground text-center py-8">
            No conversations yet
          </p>
        )}
        {conversations.map((conv) => {
          const isDeleting = deletingId === conv.id;
          const isActive = pathname === `${basePath}/${conv.id}`;

          return (
            <div
              key={conv.id}
              className={cn(
                "group flex items-center rounded-lg text-sm transition-colors",
                isActive ? "bg-accent" : "hover:bg-accent"
              )}
            >
              <Link
                href={`${basePath}/${conv.id}`}
                className="flex items-center gap-2 min-w-0 flex-1 px-2 py-2"
              >
                <MessageSquare className="size-3.5 shrink-0 text-muted-foreground" />
                <div className="min-w-0 flex-1">
                  <p className="truncate font-medium leading-tight text-sm">
                    {conv.title ?? "New conversation"}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {formatDistanceToNow(new Date(conv.updated_at), { addSuffix: true })}
                  </p>
                </div>
              </Link>

              {/* Always-visible delete — dims when not focused, red on hover */}
              <button
                onClick={(e) => handleDelete(e, conv.id)}
                disabled={isDeleting}
                className={cn(
                  "shrink-0 mr-1.5 p-1 rounded transition-all",
                  "text-muted-foreground/30 hover:text-destructive hover:bg-destructive/10",
                  "group-hover:text-muted-foreground/70",
                  isDeleting && "text-muted-foreground"
                )}
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
    </div>
  );
}
