"use client";

import { useCallback, useEffect, useState } from "react";
import { useAuth } from "@clerk/nextjs";
import { useBackendOrg } from "@/lib/hooks/useBackendOrg";
import { apiClient } from "@/lib/api-client";
import { MemberCard, type PersonOut } from "@/components/members/MemberCard";
import { Skeleton } from "@/components/ui/skeleton";
import { Input } from "@/components/ui/input";
import { Users2, Search } from "lucide-react";

export default function MembersPage() {
  const { getToken } = useAuth();
  const { orgId, isLoaded } = useBackendOrg();
  const [people, setPeople] = useState<PersonOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");

  const loadPeople = useCallback(async () => {
    const token = await getToken();
    if (!token || !orgId) return;
    try {
      const data = await apiClient.get<PersonOut[]>(
        `/organizations/${orgId}/people`,
        token
      );
      setPeople(data);
    } finally {
      setLoading(false);
    }
  }, [getToken, orgId]);

  useEffect(() => {
    if (isLoaded && orgId) {
      loadPeople();
    } else if (isLoaded && !orgId) {
      setLoading(false);
    }
  }, [isLoaded, orgId, loadPeople]);

  const filtered = people.filter((p) => {
    const q = search.toLowerCase();
    return (
      p.display_name.toLowerCase().includes(q) ||
      (p.work_email || "").toLowerCase().includes(q) ||
      (p.email || "").toLowerCase().includes(q)
    );
  });

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <Users2 className="size-6" />
          Members
        </h1>
        <p className="text-muted-foreground text-sm mt-1">
          Directory of all team members and employees. Click any person to view their profile.
        </p>
      </div>

      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-muted-foreground" />
        <Input
          placeholder="Search by name or email…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="pl-9"
        />
      </div>

      {loading ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {[...Array(6)].map((_, i) => (
            <Skeleton key={i} className="h-24 rounded-xl" />
          ))}
        </div>
      ) : filtered.length === 0 ? (
        <div className="text-center py-16 text-muted-foreground">
          {search ? "No members match your search." : "No members found."}
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {filtered.map((person) => (
            <MemberCard key={`${person.person_type}-${person.id}`} person={person} />
          ))}
        </div>
      )}

      {!loading && (
        <p className="text-xs text-muted-foreground text-center">
          {filtered.length} {filtered.length === 1 ? "person" : "people"}
          {search && ` matching "${search}"`}
        </p>
      )}
    </div>
  );
}
