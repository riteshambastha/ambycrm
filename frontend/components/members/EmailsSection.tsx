"use client";

import { useState } from "react";
import { Mail, ChevronDown, ChevronUp } from "lucide-react";
import { SectionWrapper, type SectionData } from "./SectionWrapper";
import { Button } from "@/components/ui/button";

interface Email {
  subject?: string;
  from?: string;
  from_name?: string;
  to?: string[];
  received?: string;
  body?: string;
}

function formatEmailDate(iso?: string): string {
  if (!iso) return "";
  return new Date(iso).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function EmailRow({ email }: { email: Email }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="border rounded-lg p-3 space-y-1.5">
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium truncate">{email.subject || "(No subject)"}</p>
          <p className="text-xs text-muted-foreground truncate">
            {email.from_name ? `${email.from_name} <${email.from}>` : email.from}
          </p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {email.received && (
            <span className="text-xs text-muted-foreground">{formatEmailDate(email.received)}</span>
          )}
          <Button
            variant="ghost"
            size="icon"
            className="size-6"
            onClick={() => setExpanded((p) => !p)}
          >
            {expanded ? <ChevronUp className="size-3" /> : <ChevronDown className="size-3" />}
          </Button>
        </div>
      </div>

      {expanded && email.body && (
        <p className="text-xs text-muted-foreground whitespace-pre-wrap border-t pt-2 mt-1 leading-relaxed">
          {email.body.length > 800 ? email.body.slice(0, 800) + "…" : email.body}
        </p>
      )}
    </div>
  );
}

interface EmailsSectionProps {
  loading: boolean;
  data: SectionData | null;
  onRetry?: () => void;
}

export function EmailsSection({ loading, data, onRetry }: EmailsSectionProps) {
  return (
    <SectionWrapper
      title="Emails"
      icon={<Mail className="size-4 text-blue-500" />}
      loading={loading}
      data={data}
      onRetry={onRetry}
    >
      {(results) => (
        <div className="space-y-2">
          {(results as unknown as Email[]).map((email, i) => (
            <EmailRow key={i} email={email} />
          ))}
        </div>
      )}
    </SectionWrapper>
  );
}
