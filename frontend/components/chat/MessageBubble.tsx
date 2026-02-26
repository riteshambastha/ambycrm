"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { cn } from "@/lib/utils";
import { SourceCitation } from "./SourceCitation";
import { VideoPlayer } from "./VideoPlayer";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Bot, User } from "lucide-react";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  sources?: string[];
  isStreaming?: boolean;
}

interface MessageBubbleProps {
  message: ChatMessage;
}

interface VideoMarker {
  ownerEmail: string;
  itemId: string;
  filename: string;
}

/** Split content into text segments and [VIDEO:...] markers. */
function parseVideoMarkers(content: string): Array<{ type: "text"; value: string } | { type: "video"; marker: VideoMarker }> {
  const VIDEO_RE = /\[VIDEO:([^\]|]+)\|([^\]|]+)\|([^\]]+)\]/g;
  const segments: Array<{ type: "text"; value: string } | { type: "video"; marker: VideoMarker }> = [];
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = VIDEO_RE.exec(content)) !== null) {
    if (match.index > lastIndex) {
      segments.push({ type: "text", value: content.slice(lastIndex, match.index) });
    }
    segments.push({
      type: "video",
      marker: { ownerEmail: match[1].trim(), itemId: match[2].trim(), filename: match[3].trim() },
    });
    lastIndex = match.index + match[0].length;
  }

  if (lastIndex < content.length) {
    segments.push({ type: "text", value: content.slice(lastIndex) });
  }

  return segments;
}

export function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === "user";
  const segments = isUser ? null : parseVideoMarkers(message.content);
  const hasVideos = segments?.some((s) => s.type === "video");

  return (
    <div className={cn("flex gap-3 px-4 py-3 min-w-0", isUser ? "flex-row-reverse" : "flex-row")}>
      <Avatar className="size-8 shrink-0 mt-0.5">
        <AvatarFallback
          className={cn(
            "text-xs",
            isUser ? "bg-primary text-primary-foreground" : "bg-muted"
          )}
        >
          {isUser ? <User className="size-4" /> : <Bot className="size-4" />}
        </AvatarFallback>
      </Avatar>

      <div className={cn("min-w-0 space-y-1 flex flex-col", isUser ? "items-end max-w-[80%]" : "items-start", hasVideos ? "w-full max-w-2xl" : "max-w-[80%]")}>
        <div
          className={cn(
            "rounded-2xl px-4 py-2.5 text-sm leading-relaxed min-w-0 w-full break-words",
            isUser
              ? "bg-primary text-primary-foreground rounded-tr-sm"
              : "bg-muted text-foreground rounded-tl-sm"
          )}
        >
          {isUser ? (
            <span className="whitespace-pre-wrap">{message.content}</span>
          ) : segments ? (
            <>
              {segments.map((seg, i) =>
                seg.type === "video" ? (
                  <VideoPlayer
                    key={i}
                    ownerEmail={seg.marker.ownerEmail}
                    itemId={seg.marker.itemId}
                    filename={seg.marker.filename}
                  />
                ) : (
                  <ReactMarkdown
                    key={i}
                    remarkPlugins={[remarkGfm]}
                    components={{
                      p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
                      strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
                      em: ({ children }) => <em className="italic">{children}</em>,
                      ul: ({ children }) => <ul className="list-disc pl-4 mb-2 space-y-0.5">{children}</ul>,
                      ol: ({ children }) => <ol className="list-decimal pl-4 mb-2 space-y-0.5">{children}</ol>,
                      li: ({ children }) => <li className="leading-relaxed">{children}</li>,
                      h1: ({ children }) => <h1 className="text-base font-bold mb-1">{children}</h1>,
                      h2: ({ children }) => <h2 className="text-sm font-bold mb-1">{children}</h2>,
                      h3: ({ children }) => <h3 className="text-sm font-semibold mb-1">{children}</h3>,
                      code: ({ children }) => (
                        <code className="bg-background/40 rounded px-1 py-0.5 text-xs font-mono break-all">
                          {children}
                        </code>
                      ),
                      pre: ({ children }) => (
                        <pre className="bg-background/40 rounded p-2 text-xs font-mono overflow-x-auto mb-2">
                          {children}
                        </pre>
                      ),
                      hr: () => <hr className="border-current/20 my-2" />,
                    }}
                  >
                    {seg.value}
                  </ReactMarkdown>
                )
              )}
            </>
          ) : null}
          {message.isStreaming && (
            <span className="inline-block w-1.5 h-4 ml-0.5 bg-current animate-pulse rounded-sm" />
          )}
        </div>
        {!isUser && message.sources && message.sources.length > 0 && (
          <SourceCitation sources={message.sources} />
        )}
      </div>
    </div>
  );
}
