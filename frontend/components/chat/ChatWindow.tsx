"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useAuth } from "@clerk/nextjs";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Send, Square, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { ScrollArea } from "@/components/ui/scroll-area";
import { MessageBubble, type ChatMessage } from "./MessageBubble";
import { useBackendOrg } from "@/lib/hooks/useBackendOrg";
import { apiClient } from "@/lib/api-client";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface MessageOut {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  metadata_?: { sources?: string[] };
  created_at: string;
}

interface ChatWindowProps {
  conversationId?: string;
  initialMessages?: ChatMessage[];
  onConversationCreated?: (id: string) => void;
}

export function ChatWindow({
  conversationId: initialConvId,
  initialMessages = [],
  onConversationCreated,
}: ChatWindowProps) {
  const { getToken } = useAuth();
  const { orgId, isLoaded: orgLoaded } = useBackendOrg();
  const router = useRouter();
  const [messages, setMessages] = useState<ChatMessage[]>(initialMessages);
  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [isLoadingHistory, setIsLoadingHistory] = useState(false);
  const [conversationId, setConversationId] = useState(initialConvId);
  const bottomRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Load past messages when opening an existing conversation
  useEffect(() => {
    if (!initialConvId || !orgId) return;
    let cancelled = false;
    const load = async () => {
      setIsLoadingHistory(true);
      try {
        const token = await getToken();
        if (!token || cancelled) return;
        const data = await apiClient.get<MessageOut[]>(
          `/chat/${orgId}/conversations/${initialConvId}/messages`,
          token
        );
        if (cancelled) return;
        setMessages(
          data.map((m) => ({
            id: m.id,
            role: m.role,
            content: m.content,
            sources: m.metadata_?.sources ?? [],
          }))
        );
        setConversationId(initialConvId);
      } catch {
        // non-critical — just show empty chat
      } finally {
        if (!cancelled) setIsLoadingHistory(false);
      }
    };
    load();
    return () => { cancelled = true; };
  }, [initialConvId, orgId, getToken]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const stopStreaming = useCallback(() => {
    abortRef.current?.abort();
    setIsStreaming(false);
    setMessages((prev) =>
      prev.map((m) => (m.isStreaming ? { ...m, isStreaming: false } : m))
    );
  }, []);

  const sendMessage = useCallback(async () => {
    const text = input.trim();
    if (!text || isStreaming) return;

    const token = await getToken();
    if (!token) {
      toast.error("Not authenticated");
      return;
    }
    if (!orgId) {
      toast.error("No organization found. Please create one first.");
      return;
    }

    const userMsg: ChatMessage = {
      id: crypto.randomUUID(),
      role: "user",
      content: text,
    };
    const assistantMsg: ChatMessage = {
      id: crypto.randomUUID(),
      role: "assistant",
      content: "",
      isStreaming: true,
      sources: [],
    };

    setMessages((prev) => [...prev, userMsg, assistantMsg]);
    setInput("");
    setIsStreaming(true);

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const res = await fetch(`${API_BASE}/api/v1/chat/${orgId}/stream`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          message: text,
          conversation_id: conversationId ?? null,
          org_id: orgId,
        }),
        signal: controller.signal,
      });

      if (!res.ok) {
        throw new Error(`Server error: ${res.statusText}`);
      }

      const reader = res.body!.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";

        for (const line of lines) {
          if (line.startsWith("data: ")) {
            const raw = line.slice(6);

            // Control frames (not JSON-encoded)
            if (raw === "[DONE]") {
              setIsStreaming(false);
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantMsg.id ? { ...m, isStreaming: false } : m
                )
              );
              break;
            }
            if (raw.startsWith("[CONV_ID:")) {
              const newConvId = raw.slice(9, -1);
              setConversationId(newConvId);
              onConversationCreated?.(newConvId);
              if (!initialConvId) {
                router.replace(`/chat/${newConvId}`);
              }
              continue;
            }

            // Text chunks are JSON-encoded so newlines survive the SSE wire
            let chunk: string;
            try {
              chunk = JSON.parse(raw);
            } catch {
              chunk = raw; // fallback for any non-JSON frame
            }

            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantMsg.id
                  ? { ...m, content: m.content + chunk }
                  : m
              )
            );
          }
        }
      }
    } catch (err: unknown) {
      if ((err as Error)?.name !== "AbortError") {
        toast.error("Failed to send message. Please try again.");
        setMessages((prev) => prev.filter((m) => m.id !== assistantMsg.id));
      }
    } finally {
      setIsStreaming(false);
    }
  }, [input, isStreaming, orgId, conversationId, getToken]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const isEmpty = messages.length === 0;

  if (!orgLoaded || isLoadingHistory) {
    return (
      <div className="flex items-center justify-center h-full">
        <Loader2 className="size-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      {/* Messages area */}
      <ScrollArea className="flex-1 h-0">
        {isEmpty ? (
          <div className="flex flex-col items-center justify-center h-full min-h-[60vh] text-center px-4 space-y-4">
            <div className="size-16 rounded-2xl bg-primary/10 flex items-center justify-center">
              <svg className="size-8 text-primary" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                  d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
              </svg>
            </div>
            <div>
              <h2 className="text-xl font-semibold">How can I help you today?</h2>
              <p className="text-muted-foreground text-sm mt-1 max-w-md">
                Ask me anything about your connected CRMs, emails, meetings, or documents.
              </p>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 w-full max-w-lg">
              {[
                "Show emails for sarah@company.com",
                "Show inbox for John Smith",
                "Find emails about invoices from last week",
                "What deals are open in Salesforce?",
              ].map((suggestion) => (
                <button
                  key={suggestion}
                  onClick={() => setInput(suggestion)}
                  className="text-left text-xs p-3 rounded-xl border bg-card hover:bg-accent transition-colors"
                >
                  {suggestion}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="py-4">
            {messages.map((message) => (
              <MessageBubble key={message.id} message={message} />
            ))}
            <div ref={bottomRef} />
          </div>
        )}
      </ScrollArea>

      {/* Input area */}
      <div className="border-t bg-background p-4">
        <div className="max-w-3xl mx-auto relative">
          <Textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask anything about your connected tools..."
            className="pr-24 min-h-[56px] max-h-[200px] resize-none rounded-2xl text-sm"
            rows={1}
          />
          <div className="absolute right-3 bottom-3 flex items-center gap-2">
            {isStreaming ? (
              <Button
                size="sm"
                variant="destructive"
                className="size-8 p-0 rounded-lg"
                onClick={stopStreaming}
              >
                <Square className="size-3" />
              </Button>
            ) : (
              <Button
                size="sm"
                className="size-8 p-0 rounded-lg"
                onClick={sendMessage}
                disabled={!input.trim()}
              >
                <Send className="size-3" />
              </Button>
            )}
          </div>
        </div>
        <p className="text-center text-xs text-muted-foreground mt-2">
          AmbyChat can make mistakes. Verify important information.
        </p>
      </div>
    </div>
  );
}
