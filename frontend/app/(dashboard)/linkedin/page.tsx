"use client";

import { useCallback, useEffect, useState } from "react";
import { useAuth } from "@clerk/nextjs";
import { toast } from "sonner";
import {
  Linkedin,
  RefreshCw,
  Search,
  Building2,
  ExternalLink,
  FileText,
  MailIcon,
  BriefcaseIcon,
  ChevronDown,
  ChevronRight,
  MessageSquareText,
  Loader2,
  Calendar,
} from "lucide-react";
import { useBackendOrg } from "@/lib/hooks/useBackendOrg";
import { apiClient } from "@/lib/api-client";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { cn } from "@/lib/utils";

// ── Types ─────────────────────────────────────────────────────────────────────

interface AccountContact {
  id: string;
  salesforce_contact_id: string;
  name: string;
  email: string | null;
  title: string | null;
  phone: string | null;
  account_id: string | null;
  account_name: string | null;
  account_industry: string | null;
  linkedin_url: string | null;
  linkedin_fetched_at: string | null;
  post_count: number;
  salesforce_synced_at: string;
}

interface LinkedInPost {
  id: string;
  post_url: string | null;
  post_text: string | null;
  posted_at: string | null;
  fetched_at: string;
  created_at: string;
}

interface SyncSummary {
  contacts_synced: number;
  linkedin_profiles_found: number;
  posts_fetched: number;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function getInitials(name: string): string {
  const parts = name.trim().split(" ");
  if (parts.length >= 2) return `${parts[0][0]}${parts[1][0]}`.toUpperCase();
  return name.slice(0, 2).toUpperCase();
}

function groupByAccount(contacts: AccountContact[]): Map<string, AccountContact[]> {
  const map = new Map<string, AccountContact[]>();
  for (const c of contacts) {
    const key = c.account_name ?? "No Account";
    if (!map.has(key)) map.set(key, []);
    map.get(key)!.push(c);
  }
  return new Map([...map.entries()].sort(([a], [b]) => a.localeCompare(b)));
}

function formatPostDate(dateStr: string | null): string {
  if (!dateStr) return "";
  const d = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - d.getTime();
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));
  if (diffDays === 0) return "Today";
  if (diffDays === 1) return "Yesterday";
  if (diffDays < 7) return `${diffDays}d ago`;
  if (diffDays < 30) return `${Math.floor(diffDays / 7)}w ago`;
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

// ── Post card ─────────────────────────────────────────────────────────────────

function PostCard({ post }: { post: LinkedInPost }) {
  const [expanded, setExpanded] = useState(false);
  const text = post.post_text ?? "";
  const isLong = text.length > 200;
  const displayText = isLong && !expanded ? text.slice(0, 200) + "…" : text;

  return (
    <div className="border rounded-lg p-3 bg-muted/20 hover:bg-muted/40 transition-colors space-y-2">
      <div className="flex items-start gap-2">
        <MessageSquareText className="size-4 text-[#0A66C2] shrink-0 mt-0.5" />
        <div className="flex-1 min-w-0 space-y-1">
          <p className="text-sm text-foreground leading-relaxed whitespace-pre-line">
            {displayText}
          </p>
          {isLong && (
            <button
              onClick={() => setExpanded((e) => !e)}
              className="text-xs text-[#0A66C2] hover:underline"
            >
              {expanded ? "Show less" : "Show more"}
            </button>
          )}
        </div>
      </div>
      <div className="flex items-center gap-3 text-xs text-muted-foreground pl-6">
        {post.posted_at && (
          <span className="flex items-center gap-1">
            <Calendar className="size-3" />
            {formatPostDate(post.posted_at)}
          </span>
        )}
        {post.post_url && (
          <a
            href={post.post_url}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1 hover:text-[#0A66C2] transition-colors"
          >
            <ExternalLink className="size-3" />
            View on LinkedIn
          </a>
        )}
      </div>
    </div>
  );
}

// ── Contact row with expandable posts ─────────────────────────────────────────

function ContactRow({
  contact,
  orgId,
  getToken,
}: {
  contact: AccountContact;
  orgId: string;
  getToken: () => Promise<string | null>;
}) {
  const hasLinkedIn = !!contact.linkedin_url;
  const [postsOpen, setPostsOpen] = useState(false);
  const [posts, setPosts] = useState<LinkedInPost[]>([]);
  const [loadingPosts, setLoadingPosts] = useState(false);
  const [fetchingPosts, setFetchingPosts] = useState(false);
  const [postsLoaded, setPostsLoaded] = useState(false);

  const loadPosts = useCallback(async () => {
    const token = await getToken();
    if (!token) return;
    setLoadingPosts(true);
    try {
      const data = await apiClient.get<LinkedInPost[]>(
        `/organizations/${orgId}/account-contacts/${contact.id}/posts`,
        token
      );
      setPosts(data);
      setPostsLoaded(true);
    } catch {
      toast.error("Failed to load posts");
    } finally {
      setLoadingPosts(false);
    }
  }, [getToken, orgId, contact.id]);

  const fetchNewPosts = async () => {
    const token = await getToken();
    if (!token) return;
    setFetchingPosts(true);
    try {
      const data = await apiClient.post<LinkedInPost[]>(
        `/organizations/${orgId}/account-contacts/${contact.id}/posts/refresh`,
        {},
        token
      );
      setPosts(data);
      setPostsLoaded(true);
      toast.success(`Fetched ${data.length} posts for ${contact.name}`);
    } catch {
      toast.error("Failed to fetch posts");
    } finally {
      setFetchingPosts(false);
    }
  };

  const handleTogglePosts = () => {
    if (!postsOpen && !postsLoaded && hasLinkedIn) {
      loadPosts();
    }
    setPostsOpen((o) => !o);
  };

  return (
    <div className="group">
      <div
        className={cn(
          "flex items-center gap-3 py-3 px-4 rounded-lg transition-colors",
          hasLinkedIn ? "hover:bg-[#0A66C2]/5" : "hover:bg-muted/40"
        )}
      >
        {/* Avatar */}
        <div
          className={cn(
            "size-9 rounded-full flex items-center justify-center text-xs font-semibold shrink-0 transition-colors",
            hasLinkedIn
              ? "bg-[#0A66C2]/10 text-[#0A66C2]"
              : "bg-primary/10 text-primary"
          )}
        >
          {getInitials(contact.name)}
        </div>

        {/* Info */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            {hasLinkedIn ? (
              <a
                href={contact.linkedin_url!}
                target="_blank"
                rel="noopener noreferrer"
                className="text-sm font-medium hover:text-[#0A66C2] transition-colors"
                onClick={(e) => e.stopPropagation()}
              >
                {contact.name}
              </a>
            ) : (
              <span className="text-sm font-medium">{contact.name}</span>
            )}
            {hasLinkedIn ? (
              <Badge variant="secondary" className="text-xs gap-1 py-0">
                <Linkedin className="size-3" />
                Linked
              </Badge>
            ) : contact.linkedin_fetched_at ? (
              <Badge variant="outline" className="text-xs text-muted-foreground py-0">
                Not found
              </Badge>
            ) : null}
            {contact.post_count > 0 && (
              <Badge variant="outline" className="text-xs gap-1 py-0">
                <FileText className="size-3" />
                {contact.post_count} posts
              </Badge>
            )}
          </div>

          <div className="flex flex-wrap gap-x-4 gap-y-0.5 mt-0.5">
            {contact.title && (
              <span className="text-xs text-muted-foreground flex items-center gap-1">
                <BriefcaseIcon className="size-3 shrink-0" />
                {contact.title}
              </span>
            )}
            {contact.email && (
              <span className="text-xs text-muted-foreground flex items-center gap-1 truncate max-w-[220px]">
                <MailIcon className="size-3 shrink-0" />
                {contact.email}
              </span>
            )}
          </div>
        </div>

        {/* Actions */}
        <div className="flex items-center gap-1 shrink-0">
          {hasLinkedIn && (
            <button
              onClick={handleTogglePosts}
              className={cn(
                "p-1.5 rounded-md transition-colors",
                postsOpen
                  ? "bg-[#0A66C2]/10 text-[#0A66C2]"
                  : "text-muted-foreground hover:text-[#0A66C2] hover:bg-muted"
              )}
              title="View posts"
            >
              <MessageSquareText className="size-4" />
            </button>
          )}
          {hasLinkedIn && (
            <a
              href={contact.linkedin_url!}
              target="_blank"
              rel="noopener noreferrer"
              className="p-1.5 rounded-md text-muted-foreground hover:text-[#0A66C2] hover:bg-muted transition-colors"
              title="Open LinkedIn profile"
            >
              <ExternalLink className="size-4" />
            </a>
          )}
        </div>
      </div>

      {/* Expandable posts section */}
      {postsOpen && hasLinkedIn && (
        <div className="ml-12 mr-4 mb-3 space-y-2">
          {loadingPosts ? (
            <div className="flex items-center gap-2 py-4 text-sm text-muted-foreground">
              <Loader2 className="size-4 animate-spin" />
              Loading posts…
            </div>
          ) : posts.length > 0 ? (
            <>
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs text-muted-foreground font-medium">
                  {posts.length} recent {posts.length === 1 ? "post" : "posts"}
                </span>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={fetchNewPosts}
                  disabled={fetchingPosts}
                  className="h-7 text-xs gap-1"
                >
                  {fetchingPosts ? (
                    <Loader2 className="size-3 animate-spin" />
                  ) : (
                    <RefreshCw className="size-3" />
                  )}
                  {fetchingPosts ? "Fetching…" : "Refresh Posts"}
                </Button>
              </div>
              {posts.map((p) => (
                <PostCard key={p.id} post={p} />
              ))}
            </>
          ) : (
            <div className="flex flex-col items-center gap-2 py-4">
              <p className="text-sm text-muted-foreground">No posts cached yet.</p>
              <Button
                variant="outline"
                size="sm"
                onClick={fetchNewPosts}
                disabled={fetchingPosts}
                className="gap-1.5"
              >
                {fetchingPosts ? (
                  <Loader2 className="size-3.5 animate-spin" />
                ) : (
                  <FileText className="size-3.5" />
                )}
                {fetchingPosts ? "Fetching posts…" : "Fetch Latest Posts"}
              </Button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── Account group card ────────────────────────────────────────────────────────

function AccountGroup({
  accountName,
  contacts,
  industry,
  defaultOpen,
  orgId,
  getToken,
}: {
  accountName: string;
  contacts: AccountContact[];
  industry: string | null;
  defaultOpen: boolean;
  orgId: string;
  getToken: () => Promise<string | null>;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const linkedCount = contacts.filter((c) => c.linkedin_url).length;
  const totalPosts = contacts.reduce((s, c) => s + c.post_count, 0);

  return (
    <Card className="overflow-hidden">
      <CardHeader
        className="px-4 py-3 cursor-pointer select-none flex flex-row items-center gap-3"
        onClick={() => setOpen((o) => !o)}
      >
        <div className="size-8 rounded-md bg-blue-50 text-blue-700 flex items-center justify-center shrink-0">
          <Building2 className="size-4" />
        </div>

        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold truncate">{accountName}</p>
          {industry && (
            <p className="text-xs text-muted-foreground truncate">{industry}</p>
          )}
        </div>

        <div className="flex items-center gap-2 shrink-0">
          <Badge variant="secondary" className="text-xs">
            {contacts.length} {contacts.length === 1 ? "contact" : "contacts"}
          </Badge>
          {linkedCount > 0 && (
            <Badge className="text-xs gap-1 bg-[#0A66C2] hover:bg-[#0A66C2]/90">
              <Linkedin className="size-3" />
              {linkedCount}
            </Badge>
          )}
          {totalPosts > 0 && (
            <Badge variant="outline" className="text-xs gap-1">
              <FileText className="size-3" />
              {totalPosts}
            </Badge>
          )}
          {open ? (
            <ChevronDown className="size-4 text-muted-foreground" />
          ) : (
            <ChevronRight className="size-4 text-muted-foreground" />
          )}
        </div>
      </CardHeader>

      {open && (
        <CardContent className="px-2 pb-2 pt-0 border-t divide-y divide-border/50">
          {contacts.map((c) => (
            <ContactRow
              key={c.id}
              contact={c}
              orgId={orgId}
              getToken={getToken}
            />
          ))}
        </CardContent>
      )}
    </Card>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function LinkedInPage() {
  const { getToken } = useAuth();
  const { orgId, isLoaded } = useBackendOrg();

  const [contacts, setContacts] = useState<AccountContact[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [search, setSearch] = useState("");

  const loadContacts = useCallback(async () => {
    const token = await getToken();
    if (!token || !orgId) return;
    try {
      const data = await apiClient.get<AccountContact[]>(
        `/organizations/${orgId}/account-contacts`,
        token
      );
      setContacts(data);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to load contacts";
      toast.error(msg);
    } finally {
      setLoading(false);
    }
  }, [getToken, orgId]);

  useEffect(() => {
    if (isLoaded && orgId) {
      loadContacts();
    } else if (isLoaded && !orgId) {
      setLoading(false);
    }
  }, [isLoaded, orgId, loadContacts]);

  const handleRefresh = async () => {
    const token = await getToken();
    if (!token || !orgId) return;
    setRefreshing(true);
    try {
      const summary = await apiClient.post<SyncSummary>(
        `/organizations/${orgId}/account-contacts/refresh`,
        {},
        token
      );
      toast.success(
        `Sync complete — ${summary.contacts_synced} contacts, ` +
          `${summary.linkedin_profiles_found} LinkedIn profiles found, ` +
          `${summary.posts_fetched} posts fetched`
      );
      await loadContacts();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Sync failed";
      toast.error(msg);
    } finally {
      setRefreshing(false);
    }
  };

  const filtered = contacts.filter((c) => {
    const q = search.toLowerCase();
    return (
      c.name.toLowerCase().includes(q) ||
      (c.account_name ?? "").toLowerCase().includes(q) ||
      (c.email ?? "").toLowerCase().includes(q) ||
      (c.title ?? "").toLowerCase().includes(q)
    );
  });

  const grouped = groupByAccount(filtered);

  const totalLinked = contacts.filter((c) => c.linkedin_url).length;
  const totalPosts = contacts.reduce((s, c) => s + c.post_count, 0);

  return (
    <div className="h-full flex flex-col overflow-hidden">
      {/* Sticky header area */}
      <div className="shrink-0 px-6 pt-6 pb-4 space-y-4 border-b bg-background">
        {/* Title + Refresh */}
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <h1 className="text-2xl font-bold flex items-center gap-2">
              <Linkedin className="size-6 text-[#0A66C2]" />
              LinkedIn Contacts
            </h1>
            <p className="text-muted-foreground text-sm mt-1">
              Client contacts from Salesforce, enriched with LinkedIn profiles and recent posts.
            </p>
          </div>
          <Button
            onClick={handleRefresh}
            disabled={refreshing || loading}
            className="gap-2 shrink-0"
          >
            <RefreshCw className={cn("size-4", refreshing && "animate-spin")} />
            {refreshing ? "Syncing…" : "Refresh"}
          </Button>
        </div>

        {/* Stats bar */}
        {!loading && contacts.length > 0 && (
          <div className="flex flex-wrap gap-4 text-sm text-muted-foreground">
            <span>
              <span className="font-semibold text-foreground">{contacts.length}</span> contacts
            </span>
            <span>
              <span className="font-semibold text-foreground">{grouped.size}</span> companies
            </span>
            <span>
              <span className="font-semibold text-[#0A66C2]">{totalLinked}</span> LinkedIn profiles
            </span>
            {totalPosts > 0 && (
              <span>
                <span className="font-semibold text-foreground">{totalPosts}</span> posts collected
              </span>
            )}
          </div>
        )}

        {/* Search */}
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-muted-foreground" />
          <Input
            placeholder="Search by name, company, title, or email…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-9"
          />
        </div>
      </div>

      {/* Scrollable content */}
      <div className="flex-1 min-h-0 overflow-y-auto">
        <div className="max-w-4xl mx-auto px-6 py-4 space-y-3">
          {loading ? (
            <div className="space-y-3">
              {[...Array(6)].map((_, i) => (
                <Skeleton key={i} className="h-14 rounded-xl" />
              ))}
            </div>
          ) : contacts.length === 0 ? (
            <div className="text-center py-20 space-y-3">
              <Linkedin className="size-10 text-muted-foreground/40 mx-auto" />
              <p className="text-muted-foreground">No contacts yet.</p>
              <p className="text-sm text-muted-foreground">
                Click <strong>Refresh</strong> to pull contacts from Salesforce and enrich them with LinkedIn data.
              </p>
            </div>
          ) : filtered.length === 0 ? (
            <div className="text-center py-16 text-muted-foreground">
              No contacts match <strong>&ldquo;{search}&rdquo;</strong>
            </div>
          ) : (
            <>
              {[...grouped.entries()].map(([accountName, accountContacts], idx) => (
                <AccountGroup
                  key={accountName}
                  accountName={accountName}
                  contacts={accountContacts}
                  industry={accountContacts[0]?.account_industry ?? null}
                  defaultOpen={idx < 3}
                  orgId={orgId!}
                  getToken={getToken}
                />
              ))}

              <p className="text-xs text-muted-foreground text-center pb-4 pt-2">
                Showing {filtered.length} {filtered.length === 1 ? "contact" : "contacts"} across{" "}
                {grouped.size} {grouped.size === 1 ? "company" : "companies"}
                {search && ` matching "${search}"`}
              </p>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
