"use client";

import { useState } from "react";
import { Video, ChevronDown, ChevronUp, Clock } from "lucide-react";
import { SectionWrapper, type SectionData } from "./SectionWrapper";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

interface MeetingItem {
  subject?: string;
  title?: string;
  name?: string;
  start_time?: string;
  date?: string;
  duration?: number;
  status?: string;
  has_transcript?: boolean;
  transcript?: string;
  summary?: string;
  key_points?: string[];
  participants?: string[];
  [key: string]: unknown;
}

function getMeetingTitle(m: MeetingItem): string {
  return m.subject || m.title || m.name || "Meeting Recording";
}

function formatDate(iso?: string): string {
  if (!iso) return "";
  return new Date(iso).toLocaleDateString("en-US", {
    weekday: "short",
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatDuration(mins?: number): string {
  if (!mins) return "";
  const h = Math.floor(mins / 60);
  const m = mins % 60;
  return h > 0 ? `${h}h ${m}m` : `${m}m`;
}

function getStatusVariant(status?: string): "default" | "secondary" | "outline" {
  if (!status) return "outline";
  const s = status.toLowerCase();
  if (["done", "completed", "finished"].some((w) => s.includes(w))) return "default";
  if (["in_progress", "recording"].some((w) => s.includes(w))) return "secondary";
  return "outline";
}

function MeetingRow({ meeting }: { meeting: MeetingItem }) {
  const [expanded, setExpanded] = useState(false);
  const date = meeting.start_time || meeting.date;
  const transcriptText = meeting.summary || meeting.transcript;

  return (
    <div className="border rounded-lg p-3 space-y-2">
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium truncate">{getMeetingTitle(meeting)}</p>
          <div className="flex items-center gap-2 flex-wrap mt-0.5">
            {date && (
              <span className="text-xs text-muted-foreground">{formatDate(date)}</span>
            )}
            {meeting.duration && (
              <span className="text-xs text-muted-foreground flex items-center gap-0.5">
                <Clock className="size-2.5" />
                {formatDuration(meeting.duration)}
              </span>
            )}
          </div>
        </div>
        <div className="flex items-center gap-1.5 shrink-0">
          {meeting.status && (
            <Badge variant={getStatusVariant(meeting.status)} className="text-xs">
              {meeting.status}
            </Badge>
          )}
          {meeting.has_transcript === false && (
            <Badge variant="outline" className="text-xs text-muted-foreground">No transcript</Badge>
          )}
          {transcriptText && (
            <Button
              variant="ghost"
              size="icon"
              className="size-6"
              onClick={() => setExpanded((p) => !p)}
            >
              {expanded ? <ChevronUp className="size-3" /> : <ChevronDown className="size-3" />}
            </Button>
          )}
        </div>
      </div>

      {expanded && transcriptText && (
        <div className="border-t pt-2 space-y-1.5">
          {meeting.key_points && meeting.key_points.length > 0 ? (
            <div>
              <p className="text-xs font-semibold text-muted-foreground mb-1">Key Points</p>
              <ul className="text-xs space-y-0.5 list-disc pl-4">
                {meeting.key_points.map((pt, i) => (
                  <li key={i}>{pt}</li>
                ))}
              </ul>
            </div>
          ) : (
            <p className="text-xs text-muted-foreground whitespace-pre-wrap leading-relaxed">
              {transcriptText.length > 1000 ? transcriptText.slice(0, 1000) + "…" : transcriptText}
            </p>
          )}
        </div>
      )}
    </div>
  );
}

interface MeetingsSectionProps {
  loading: boolean;
  data: SectionData | null;
  onRetry?: () => void;
}

export function MeetingsSection({ loading, data, onRetry }: MeetingsSectionProps) {
  return (
    <SectionWrapper
      title="Meeting Recordings"
      icon={<Video className="size-4 text-purple-500" />}
      loading={loading}
      data={data}
      onRetry={onRetry}
    >
      {(results) => (
        <div className="space-y-2">
          {(results as unknown as MeetingItem[]).map((m, i) => (
            <MeetingRow key={i} meeting={m} />
          ))}
        </div>
      )}
    </SectionWrapper>
  );
}
