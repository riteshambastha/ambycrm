"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useAuth } from "@clerk/nextjs";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Loader2, Plus, Send, Sparkles } from "lucide-react";
import { cn } from "@/lib/utils";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const STARTER_PROMPTS = [
  "What are the most urgent emails right now?",
  "Summarize the last 3 meetings and their action items",
  "Any open Salesforce opportunities or overdue tasks?",
  "What OneDrive files were recently shared or edited?",
  "Show the most recent Teams or Recall transcripts",
];

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

interface MemberChatProps {
  orgId: string;
  personId: string;
  personType: "member" | "employee";
  displayName: string;
  workEmail: string | null;
}

export function MemberChat({ orgId, personId, personType, displayName, workEmail }: MemberChatProps) {
  const { getToken } = useAuth();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  const streamEndpoint =
    personType === "member"
      ? `/api/v1/organizations/${orgId}/members/${personId}/chat/stream`
      : `/api/v1/organizations/${orgId}/employees/${personId}/chat/stream`;

  useEffect(() => {
    scrollRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const sendMessage = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || isStreaming) return;

      setInput("");
      setMessages((prev) => [...prev, { role: "user", content: trimmed }]);
      setIsStreaming(true);

      // Add an empty assistant placeholder
      setMessages((prev) => [...prev, { role: "assistant", content: "" }]);

      const token = await getToken();
      const controller = new AbortController();
      abortRef.current = controller;

      try {
        const res = await fetch(`${API_BASE}${streamEndpoint}`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({
            message: trimmed,
            conversation_id: conversationId,
            org_id: orgId,
          }),
          signal: controller.signal,
        });

        if (!res.ok || !res.body) {
          let detail = "Something went wrong. Please try again.";
          try {
            const errBody = await res.json();
            const raw = errBody?.detail;
            if (typeof raw === "string") {
              detail = raw;
            } else if (Array.isArray(raw)) {
              detail = raw.map((e: { msg?: string }) => e.msg ?? JSON.stringify(e)).join("; ");
            }
          } catch { /* ignore parse error */ }
          setMessages((prev) => {
            const copy = [...prev];
            copy[copy.length - 1] = { role: "assistant", content: detail };
            return copy;
          });
          return;
        }

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        let full = "";

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop() ?? "";

          for (const line of lines) {
            if (!line.startsWith("data: ")) continue;
            const data = line.slice(6);
            if (data === "[DONE]") break;
            if (data.startsWith("[CONV_ID:")) {
              const id = data.slice(9, -1);
              setConversationId(id);
              continue;
            }
            // Server-side error event
            if (data.startsWith("[ERROR]")) {
              const errMsg = data.slice(7).trim() || "Something went wrong. Please try again.";
              setMessages((prev) => {
                const copy = [...prev];
                copy[copy.length - 1] = { role: "assistant", content: errMsg };
                return copy;
              });
              return;
            }
            try {
              const chunk: string = JSON.parse(data);
              full += chunk;
              setMessages((prev) => {
                const copy = [...prev];
                copy[copy.length - 1] = { role: "assistant", content: full };
                return copy;
              });
            } catch {
              // skip malformed chunks
            }
          }
        }
      } catch (err: unknown) {
        if ((err as Error).name !== "AbortError") {
          setMessages((prev) => {
            const copy = [...prev];
            copy[copy.length - 1] = {
              role: "assistant",
              content: "Connection error. Please try again.",
            };
            return copy;
          });
        }
      } finally {
        setIsStreaming(false);
      }
    },
    [isStreaming, conversationId, getToken, streamEndpoint]
  );

  function handleNewConversation() {
    abortRef.current?.abort();
    setMessages([]);
    setConversationId(null);
    setInput("");
    setIsStreaming(false);
  }

  const isEmpty = messages.length === 0;
  const firstName = displayName.split(" ")[0];

  return (
    <div className="flex flex-col h-full border rounded-xl overflow-hidden bg-card">
      {/* Header */}
      <div className="flex items-center justify-between p-3 border-b shrink-0">
        <div className="flex items-center gap-2">
          <Sparkles className="size-4 text-primary" />
          <span className="text-sm font-semibold">Ask about {firstName}</span>
        </div>
        <Button
          variant="ghost"
          size="sm"
          onClick={handleNewConversation}
          className="h-7 text-xs gap-1"
        >
          <Plus className="size-3" />
          New
        </Button>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-3 space-y-3 min-h-0">
        {isEmpty && (
          <div className="space-y-2 pt-2">
            {!workEmail && (
              <p className="text-xs text-amber-600 bg-amber-50 dark:bg-amber-900/20 rounded-lg p-2.5">
                No work email set for this person. Connector data won't be available in chat.
              </p>
            )}
            <p className="text-xs text-muted-foreground text-center pt-2">
              Ask anything about {firstName}'s emails, files, meetings, or CRM data.
            </p>
            <div className="space-y-1.5 pt-1">
              {STARTER_PROMPTS.map((prompt) => (
                <button
                  key={prompt}
                  onClick={() => sendMessage(prompt)}
                  className="w-full text-left text-xs p-2.5 rounded-lg border bg-muted/30 hover:bg-muted/60 transition-colors leading-relaxed"
                >
                  {prompt}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg, i) => (
          <div
            key={i}
            className={cn(
              "flex gap-2 items-start",
              msg.role === "user" ? "flex-row-reverse" : "flex-row"
            )}
          >
            {msg.role === "assistant" && (
              <Avatar className="size-6 shrink-0">
                <AvatarFallback className="text-xs bg-primary text-primary-foreground">AI</AvatarFallback>
              </Avatar>
            )}
            <div
              className={cn(
                "rounded-xl px-3 py-2 text-sm max-w-[85%] whitespace-pre-wrap leading-relaxed",
                msg.role === "user"
                  ? "bg-primary text-primary-foreground rounded-tr-sm"
                  : "bg-muted rounded-tl-sm"
              )}
            >
              {msg.content || (
                <span className="flex items-center gap-1 text-muted-foreground">
                  <Loader2 className="size-3 animate-spin" />
                  Thinking…
                </span>
              )}
            </div>
          </div>
        ))}
        <div ref={scrollRef} />
      </div>

      {/* Input */}
      <div className="p-3 border-t shrink-0">
        <form
          className="flex gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            sendMessage(input);
          }}
        >
          <Input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={`Ask about ${firstName}…`}
            disabled={isStreaming}
            className="h-9 text-sm"
          />
          <Button
            type="submit"
            size="icon"
            disabled={!input.trim() || isStreaming}
            className="size-9 shrink-0"
          >
            {isStreaming ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <Send className="size-4" />
            )}
          </Button>
        </form>
      </div>
    </div>
  );
}
