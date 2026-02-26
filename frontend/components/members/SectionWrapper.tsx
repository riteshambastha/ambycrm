"use client";

import { formatDistanceToNow } from "date-fns";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { AlertCircle, Clock, RefreshCw, Wifi, WifiOff } from "lucide-react";

export interface SectionData {
  connected: boolean;
  results: Record<string, unknown>[];
  summary?: string | null;
  error?: string | null;
  limit: number;
  cached?: boolean;
  fetched_at?: string | null;
  cache_status?: "fresh" | "stale_refresh" | "miss";
}

interface SectionWrapperProps {
  title: string;
  icon: React.ReactNode;
  loading: boolean;
  data: SectionData | null;
  onRetry?: () => void;
  children: (results: Record<string, unknown>[]) => React.ReactNode;
}

export function SectionWrapper({
  title,
  icon,
  loading,
  data,
  onRetry,
  children,
}: SectionWrapperProps) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between gap-2">
          <CardTitle className="text-base flex items-center gap-2">
            {icon}
            {title}
          </CardTitle>
          <div className="flex items-center gap-2">
            {data?.cache_status === "stale_refresh" && (
              <Badge variant="outline" className="text-xs gap-1 text-amber-600 border-amber-400">
                <RefreshCw className="size-3 animate-spin" />
                Refreshing
              </Badge>
            )}
            {data?.cached && data?.fetched_at && data.cache_status === "fresh" && (
              <span className="text-xs text-muted-foreground flex items-center gap-1">
                <Clock className="size-3" />
                Updated {formatDistanceToNow(new Date(data.fetched_at), { addSuffix: true })}
              </span>
            )}
            {data?.connected === false && !loading && (
              <Badge variant="outline" className="text-xs gap-1 text-muted-foreground">
                <WifiOff className="size-3" />
                Not connected
              </Badge>
            )}
            {data?.connected === true && !loading && (
              <Badge variant="outline" className="text-xs gap-1 text-green-600 border-green-400">
                <Wifi className="size-3" />
                Live
              </Badge>
            )}
          </div>
        </div>
      </CardHeader>

      <CardContent className="space-y-3">
        {loading && (
          <div className="space-y-2">
            <Skeleton className="h-16 rounded-lg" />
            {[...Array(3)].map((_, i) => (
              <Skeleton key={i} className="h-10 rounded" />
            ))}
          </div>
        )}

        {!loading && data?.error && (
          <div className="flex items-start gap-2 text-sm text-destructive p-3 rounded-lg bg-destructive/10">
            <AlertCircle className="size-4 shrink-0 mt-0.5" />
            <div className="flex-1">
              <p>{data.error}</p>
              {onRetry && (
                <Button variant="ghost" size="sm" onClick={onRetry} className="mt-1 h-7 text-xs px-2">
                  Retry
                </Button>
              )}
            </div>
          </div>
        )}

        {!loading && data?.connected === false && !data?.error && (
          <p className="text-sm text-muted-foreground py-2">
            {data?.results?.length === 0 && !data?.summary
              ? "Connect this integration in Connections to see data here."
              : data.error}
          </p>
        )}

        {!loading && data && !data.error && (
          <>
            {data.summary && (
              <div className="rounded-lg border bg-muted/40 p-3 text-sm space-y-1">
                <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-1.5">
                  AI Summary
                </p>
                <div className="whitespace-pre-wrap leading-relaxed">{data.summary}</div>
              </div>
            )}

            {data.results.length === 0 && !data.summary ? (
              <p className="text-sm text-muted-foreground py-2 text-center">No data found.</p>
            ) : (
              children(data.results)
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}
