"use client";

import { useState } from "react";
import { useAuth } from "@clerk/nextjs";
import { toast } from "sonner";
import { CheckCircle2, XCircle, Loader2, ExternalLink, Unplug } from "lucide-react";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { apiClient } from "@/lib/api-client";
import { cn } from "@/lib/utils";

export interface ConnectorDefinition {
  id: string;
  key: string;
  name: string;
  category: string;
  auth_type: string;
  description: string | null;
  is_available: boolean;
}

export interface IntegrationStatus {
  id: string;
  connector_key: string;
  status: "connected" | "disconnected" | "error";
  display_name: string | null;
  last_synced_at: string | null;
}

const CATEGORY_COLORS: Record<string, string> = {
  crm: "bg-blue-100 text-blue-800",
  workspace: "bg-green-100 text-green-800",
  meetings: "bg-purple-100 text-purple-800",
};

const CONNECTOR_ICONS: Record<string, string> = {
  salesforce: "☁️",
  hubspot: "🟠",
  dynamics: "🔵",
  sugarcrm: "🍬",
  google_workspace: "🔍",
  microsoft365: "📧",
  teams: "💬",
  fireflies: "🔥",
  otter: "🦦",
  recall: "⏺️",
};

interface ConnectorCardProps {
  connector: ConnectorDefinition;
  integration?: IntegrationStatus;
  orgId: string;
  onStatusChange: () => void;
}

export function ConnectorCard({ connector, integration, orgId, onStatusChange }: ConnectorCardProps) {
  const { getToken } = useAuth();
  const [isLoading, setIsLoading] = useState(false);

  const isConnected = integration?.status === "connected";

  const handleConnect = async () => {
    setIsLoading(true);
    try {
      const token = await getToken();
      if (!token) throw new Error("Not authenticated");

      const data = await apiClient.get<{ authorization_url: string; state: string }>(
        `/integrations/oauth/start?connector_key=${connector.key}&org_id=${orgId}`,
        token
      );
      // Redirect to OAuth consent page
      window.location.href = data.authorization_url;
    } catch (err: unknown) {
      toast.error((err as Error).message ?? "Failed to start OAuth flow");
    } finally {
      setIsLoading(false);
    }
  };

  const handleDisconnect = async () => {
    if (!integration) return;
    setIsLoading(true);
    try {
      const token = await getToken();
      if (!token) throw new Error("Not authenticated");
      await apiClient.delete(`/integrations/${orgId}/${integration.id}`, token);
      toast.success(`${connector.name} disconnected`);
      onStatusChange();
    } catch (err: unknown) {
      toast.error((err as Error).message ?? "Failed to disconnect");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <Card className={cn("flex flex-col", isConnected && "border-green-300")}>
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-2">
          <div className="flex items-center gap-3">
            <div className="text-2xl">{CONNECTOR_ICONS[connector.key] ?? "🔌"}</div>
            <div>
              <CardTitle className="text-base">{connector.name}</CardTitle>
              <Badge
                variant="secondary"
                className={cn("text-xs mt-1", CATEGORY_COLORS[connector.category])}
              >
                {connector.category}
              </Badge>
            </div>
          </div>
          {isConnected ? (
            <CheckCircle2 className="size-5 text-green-500 shrink-0" />
          ) : (
            <XCircle className="size-5 text-muted-foreground shrink-0" />
          )}
        </div>
      </CardHeader>

      <CardContent className="flex-1">
        <CardDescription className="text-xs">{connector.description}</CardDescription>
        {isConnected && integration?.last_synced_at && (
          <p className="text-xs text-muted-foreground mt-2">
            Last synced:{" "}
            {new Date(integration.last_synced_at).toLocaleString()}
          </p>
        )}
      </CardContent>

      <CardFooter className="pt-3 border-t">
        {isConnected ? (
          <Button
            variant="outline"
            size="sm"
            className="w-full text-destructive hover:text-destructive"
            onClick={handleDisconnect}
            disabled={isLoading}
          >
            {isLoading ? (
              <Loader2 className="size-3.5 mr-2 animate-spin" />
            ) : (
              <Unplug className="size-3.5 mr-2" />
            )}
            Disconnect
          </Button>
        ) : (
          <Button
            size="sm"
            className="w-full"
            onClick={handleConnect}
            disabled={isLoading || !connector.is_available}
          >
            {isLoading ? (
              <Loader2 className="size-3.5 mr-2 animate-spin" />
            ) : (
              <ExternalLink className="size-3.5 mr-2" />
            )}
            Connect
          </Button>
        )}
      </CardFooter>
    </Card>
  );
}
