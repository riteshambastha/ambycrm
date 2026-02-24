"use client";

import { useCallback, useEffect, useState } from "react";
import { useAuth } from "@clerk/nextjs";
import { useOrg } from "@/lib/hooks/useOrg";
import { apiClient } from "@/lib/api-client";
import { ConnectorCard, type ConnectorDefinition, type IntegrationStatus } from "@/components/connectors/ConnectorCard";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { Plug } from "lucide-react";

const CATEGORIES = ["crm", "workspace", "meetings"];

export default function ConnectionsPage() {
  const { getToken } = useAuth();
  const { orgId, isLoaded } = useOrg();
  const [connectors, setConnectors] = useState<ConnectorDefinition[]>([]);
  const [integrations, setIntegrations] = useState<IntegrationStatus[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeCategory, setActiveCategory] = useState<string>("all");

  const load = useCallback(async () => {
    const token = await getToken();
    if (!token || !orgId) return;
    try {
      const [connData, intData] = await Promise.all([
        apiClient.get<ConnectorDefinition[]>("/integrations/connectors", token),
        apiClient.get<IntegrationStatus[]>(`/integrations/${orgId}`, token),
      ]);
      setConnectors(connData);
      setIntegrations(intData);
    } finally {
      setLoading(false);
    }
  }, [getToken, orgId]);

  useEffect(() => {
    if (isLoaded && orgId) load();
  }, [isLoaded, orgId, load]);

  const getIntegration = (key: string) => integrations.find((i) => i.connector_key === key);
  const connectedCount = integrations.filter((i) => i.status === "connected").length;

  const filtered =
    activeCategory === "all"
      ? connectors
      : connectors.filter((c) => c.category === activeCategory);

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Plug className="size-6" />
            Integration Hub
          </h1>
          <p className="text-muted-foreground text-sm mt-1">
            Connect your enterprise tools to unlock AI-powered insights.
          </p>
        </div>
        <Badge variant="outline" className="text-sm">
          {connectedCount} connected
        </Badge>
      </div>

      {/* Category filter */}
      <div className="flex flex-wrap gap-2">
        {["all", ...CATEGORIES].map((cat) => (
          <button
            key={cat}
            onClick={() => setActiveCategory(cat)}
            className={`px-3 py-1 rounded-full text-sm font-medium transition-colors border ${
              activeCategory === cat
                ? "bg-primary text-primary-foreground border-primary"
                : "bg-transparent hover:bg-accent border-border"
            }`}
          >
            {cat.charAt(0).toUpperCase() + cat.slice(1)}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-48 rounded-xl" />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {filtered.map((connector) => (
            <ConnectorCard
              key={connector.key}
              connector={connector}
              integration={getIntegration(connector.key)}
              orgId={orgId!}
              onStatusChange={load}
            />
          ))}
        </div>
      )}
    </div>
  );
}
