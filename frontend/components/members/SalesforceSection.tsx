"use client";

import { Briefcase } from "lucide-react";
import { SectionWrapper, type SectionData } from "./SectionWrapper";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

interface SalesforceItem {
  type?: string;
  Name?: string;
  StageName?: string;
  Amount?: number;
  CloseDate?: string;
  Email?: string;
  Phone?: string;
  AccountName?: string;
  Status?: string;
  ActivityDate?: string;
  Subject?: string;
  Description?: string;
  [key: string]: unknown;
}

function formatCurrency(amount?: number): string {
  if (amount === undefined || amount === null) return "";
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(amount);
}

function formatDate(iso?: string): string {
  if (!iso) return "";
  return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

function getStageBadgeVariant(stage?: string): "default" | "secondary" | "destructive" | "outline" {
  if (!stage) return "outline";
  const s = stage.toLowerCase();
  if (s.includes("closed won")) return "default";
  if (s.includes("closed lost")) return "destructive";
  if (s.includes("proposal") || s.includes("negotiation")) return "secondary";
  return "outline";
}

function SFItem({ item }: { item: SalesforceItem }) {
  const type = item.type || "Record";

  if (type === "Opportunity") {
    return (
      <div className="border rounded-lg p-3 space-y-1">
        <div className="flex items-start justify-between gap-2">
          <p className="text-sm font-medium">{item.Name || "Unnamed Opportunity"}</p>
          <div className="flex items-center gap-1.5 shrink-0">
            {item.StageName && (
              <Badge variant={getStageBadgeVariant(item.StageName)} className="text-xs">
                {item.StageName}
              </Badge>
            )}
          </div>
        </div>
        <div className="flex gap-3 text-xs text-muted-foreground">
          {item.Amount !== undefined && <span>{formatCurrency(item.Amount)}</span>}
          {item.CloseDate && <span>Close: {formatDate(item.CloseDate)}</span>}
        </div>
      </div>
    );
  }

  if (type === "Contact") {
    return (
      <div className="border rounded-lg p-3 flex items-center gap-3">
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium truncate">{item.Name || "Unnamed Contact"}</p>
          <p className="text-xs text-muted-foreground">
            {[item.Email, item.Phone, item.AccountName].filter(Boolean).join(" · ")}
          </p>
        </div>
        <Badge variant="outline" className="text-xs shrink-0">Contact</Badge>
      </div>
    );
  }

  if (type === "Task" || type === "Activity") {
    const isOverdue =
      item.Status !== "Completed" &&
      item.ActivityDate &&
      new Date(item.ActivityDate as string) < new Date();
    return (
      <div className={cn("border rounded-lg p-3 space-y-1", isOverdue && "border-amber-400 bg-amber-50/40 dark:bg-amber-900/10")}>
        <div className="flex items-start justify-between gap-2">
          <p className="text-sm font-medium">{item.Subject || item.Description || "Activity"}</p>
          <div className="flex items-center gap-1.5 shrink-0">
            {isOverdue && <Badge variant="destructive" className="text-xs">Overdue</Badge>}
            {item.Status && <Badge variant="outline" className="text-xs">{item.Status}</Badge>}
          </div>
        </div>
        {item.ActivityDate && (
          <p className="text-xs text-muted-foreground">Due: {formatDate(item.ActivityDate as string)}</p>
        )}
      </div>
    );
  }

  // Generic fallback
  return (
    <div className="border rounded-lg p-3 flex items-center justify-between gap-2">
      <p className="text-sm truncate">{item.Name || JSON.stringify(item).slice(0, 80)}</p>
      <Badge variant="outline" className="text-xs shrink-0">{type}</Badge>
    </div>
  );
}

interface SalesforceSectionProps {
  loading: boolean;
  data: SectionData | null;
  onRetry?: () => void;
}

export function SalesforceSection({ loading, data, onRetry }: SalesforceSectionProps) {
  return (
    <SectionWrapper
      title="Salesforce / CRM"
      icon={<Briefcase className="size-4 text-sky-500" />}
      loading={loading}
      data={data}
      onRetry={onRetry}
    >
      {(results) => (
        <div className="space-y-2">
          {(results as unknown as SalesforceItem[]).map((item, i) => (
            <SFItem key={i} item={item} />
          ))}
        </div>
      )}
    </SectionWrapper>
  );
}
