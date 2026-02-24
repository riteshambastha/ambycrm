"use client";

import { Badge } from "@/components/ui/badge";
import { Plug, Database, FileText, Video } from "lucide-react";

const SOURCE_META: Record<string, { label: string; color: string; icon: React.ElementType }> = {
  salesforce: { label: "Salesforce", color: "bg-blue-100 text-blue-800", icon: Database },
  hubspot: { label: "HubSpot", color: "bg-orange-100 text-orange-800", icon: Database },
  dynamics: { label: "Dynamics 365", color: "bg-blue-100 text-blue-800", icon: Database },
  google_workspace: { label: "Gmail", color: "bg-red-100 text-red-800", icon: FileText },
  microsoft365: { label: "Outlook", color: "bg-blue-100 text-blue-800", icon: FileText },
  fireflies: { label: "Fireflies", color: "bg-purple-100 text-purple-800", icon: Video },
  teams: { label: "Teams", color: "bg-indigo-100 text-indigo-800", icon: Video },
  otter: { label: "Otter.ai", color: "bg-green-100 text-green-800", icon: Video },
  recall: { label: "Recall.ai", color: "bg-gray-100 text-gray-800", icon: Video },
};

interface SourceCitationProps {
  sources: string[];
}

export function SourceCitation({ sources }: SourceCitationProps) {
  if (!sources || sources.length === 0) return null;

  return (
    <div className="flex flex-wrap gap-1 mt-2">
      <span className="text-xs text-muted-foreground">Sources:</span>
      {sources.map((source) => {
        const meta = SOURCE_META[source] ?? {
          label: source,
          color: "bg-gray-100 text-gray-700",
          icon: Plug,
        };
        const Icon = meta.icon;
        return (
          <span
            key={source}
            className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${meta.color}`}
          >
            <Icon className="size-3" />
            {meta.label}
          </span>
        );
      })}
    </div>
  );
}
