"use client";

import { Briefcase } from "lucide-react";
import { SectionWrapper, type SectionData } from "./SectionWrapper";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

interface SalesforceItem {
  _object_type?: string;
  type?: string;
  Name?: string;
  StageName?: string;
  Amount?: number;
  CloseDate?: string;
  Probability?: number;
  Email?: string;
  Phone?: string;
  Title?: string;
  Company?: string;
  Rating?: string;
  LeadSource?: string;
  Account?: { Name?: string };
  AccountName?: string;
  Owner?: { Name?: string };
  Status?: string;
  Priority?: string;
  ActivityDate?: string;
  Subject?: string;
  CaseNumber?: string;
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

function accountName(item: SalesforceItem): string | undefined {
  return item.Account?.Name || item.AccountName;
}

function ownerName(item: SalesforceItem): string | undefined {
  return item.Owner?.Name;
}

function SFItem({ item }: { item: SalesforceItem }) {
  const type = item._object_type || item.type || "Record";

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
        <div className="flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-muted-foreground">
          {item.Amount != null && <span>{formatCurrency(item.Amount)}</span>}
          {item.Probability != null && <span>{item.Probability}% prob</span>}
          {item.CloseDate && <span>Close: {formatDate(item.CloseDate)}</span>}
          {accountName(item) && <span>{accountName(item)}</span>}
        </div>
      </div>
    );
  }

  if (type === "Lead") {
    return (
      <div className="border rounded-lg p-3 space-y-1">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <p className="text-sm font-medium truncate">{item.Name || "Unnamed Lead"}</p>
            <p className="text-xs text-muted-foreground truncate">
              {[item.Company, item.Email, item.Phone].filter(Boolean).join(" · ")}
            </p>
          </div>
          <div className="flex items-center gap-1.5 shrink-0">
            {item.Status && <Badge variant="outline" className="text-xs">{item.Status}</Badge>}
            {item.Rating && <Badge variant="secondary" className="text-xs">{item.Rating}</Badge>}
          </div>
        </div>
      </div>
    );
  }

  if (type === "Contact") {
    return (
      <div className="border rounded-lg p-3 flex items-center gap-3">
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium truncate">{item.Name || "Unnamed Contact"}</p>
          <p className="text-xs text-muted-foreground truncate">
            {[item.Title, item.Email, item.Phone, accountName(item)].filter(Boolean).join(" · ")}
          </p>
        </div>
        <Badge variant="outline" className="text-xs shrink-0">Contact</Badge>
      </div>
    );
  }

  if (type === "Task") {
    const isOverdue =
      item.Status !== "Completed" &&
      item.ActivityDate &&
      new Date(item.ActivityDate as string) < new Date();
    return (
      <div className={cn("border rounded-lg p-3 space-y-1", isOverdue && "border-amber-400 bg-amber-50/40 dark:bg-amber-900/10")}>
        <div className="flex items-start justify-between gap-2">
          <p className="text-sm font-medium">{item.Subject || "Unnamed Task"}</p>
          <div className="flex items-center gap-1.5 shrink-0">
            {isOverdue && <Badge variant="destructive" className="text-xs">Overdue</Badge>}
            {item.Priority && <Badge variant="secondary" className="text-xs">{item.Priority}</Badge>}
            {item.Status && <Badge variant="outline" className="text-xs">{item.Status}</Badge>}
          </div>
        </div>
        <div className="text-xs text-muted-foreground">
          {item.ActivityDate && <span>Due: {formatDate(item.ActivityDate as string)}</span>}
          {ownerName(item) && <span> · {ownerName(item)}</span>}
        </div>
      </div>
    );
  }

  if (type === "Case") {
    return (
      <div className="border rounded-lg p-3 space-y-1">
        <div className="flex items-start justify-between gap-2">
          <p className="text-sm font-medium">{item.Subject || `Case #${item.CaseNumber}`}</p>
          <div className="flex items-center gap-1.5 shrink-0">
            {item.Priority && <Badge variant="secondary" className="text-xs">{item.Priority}</Badge>}
            {item.Status && <Badge variant="outline" className="text-xs">{item.Status}</Badge>}
          </div>
        </div>
        <p className="text-xs text-muted-foreground">
          {[accountName(item), ownerName(item)].filter(Boolean).join(" · ")}
        </p>
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
  onRefresh?: () => void;
}

const OBJECT_ORDER = ["Opportunity", "Lead", "Contact", "Task", "Case"];
const OBJECT_LABELS: Record<string, string> = {
  Opportunity: "Opportunities",
  Lead: "Leads",
  Contact: "Contacts",
  Task: "Tasks & Activities",
  Case: "Cases",
};

export function SalesforceSection({ loading, data, onRetry, onRefresh }: SalesforceSectionProps) {
  return (
    <SectionWrapper
      title="Salesforce / CRM"
      icon={<Briefcase className="size-4 text-sky-500" />}
      loading={loading}
      data={data}
      onRetry={onRetry}
      onRefresh={onRefresh}
    >
      {(results) => {
        const items = results as unknown as SalesforceItem[];
        const grouped: Record<string, SalesforceItem[]> = {};
        for (const item of items) {
          const t = item._object_type || item.type || "Other";
          (grouped[t] ??= []).push(item);
        }
        const sortedTypes = Object.keys(grouped).sort(
          (a, b) => (OBJECT_ORDER.indexOf(a) === -1 ? 99 : OBJECT_ORDER.indexOf(a))
                   - (OBJECT_ORDER.indexOf(b) === -1 ? 99 : OBJECT_ORDER.indexOf(b))
        );

        return (
          <div className="space-y-4">
            {sortedTypes.map((type) => (
              <div key={type} className="space-y-2">
                <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
                  {OBJECT_LABELS[type] || type} ({grouped[type].length})
                </p>
                {grouped[type].map((item, i) => (
                  <SFItem key={i} item={item} />
                ))}
              </div>
            ))}
          </div>
        );
      }}
    </SectionWrapper>
  );
}
