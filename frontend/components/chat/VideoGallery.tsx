"use client";

import { useState, useRef } from "react";
import { useAuth } from "@clerk/nextjs";
import { Play, Loader2, AlertCircle, Film, ChevronDown, ChevronUp, Clock } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface VideoItem {
  ownerEmail: string;
  itemId: string;
  filename: string;
}

interface VideoGalleryProps {
  videos: VideoItem[];
}

interface PlayerState {
  status: "idle" | "loading" | "ready" | "error";
  url?: string;
  error?: string;
}

function formatFilename(name: string): string {
  // Strip common timestamp suffixes to make names more readable
  return name
    .replace(/\.(mp4|mov|avi|mkv|webm|wmv)$/i, "")
    .replace(/-Meeting Recording$/i, "")
    .replace(/_/g, " ")
    .trim();
}

function parseDate(filename: string): string {
  // Try to extract a date from filenames like "Meeting-20260223_145956UTC"
  const m = filename.match(/(\d{4})(\d{2})(\d{2})[_T](\d{2})(\d{2})/);
  if (m) {
    const [, y, mo, d, h, min] = m;
    return new Date(`${y}-${mo}-${d}T${h}:${min}:00Z`).toLocaleDateString("en-US", {
      month: "short", day: "numeric", year: "numeric", hour: "2-digit", minute: "2-digit",
    });
  }
  return "";
}

export function VideoGallery({ videos }: VideoGalleryProps) {
  const { getToken } = useAuth();
  const [activeIndex, setActiveIndex] = useState<number | null>(null);
  const [players, setPlayers] = useState<Record<number, PlayerState>>({});
  const [collapsed, setCollapsed] = useState(false);
  const videoRef = useRef<HTMLVideoElement>(null);

  const loadVideo = async (index: number, video: VideoItem) => {
    // If already active and ready, collapse the player
    if (activeIndex === index && players[index]?.status === "ready") {
      setActiveIndex(null);
      return;
    }

    setActiveIndex(index);

    if (players[index]?.status === "ready") return; // already loaded

    setPlayers((p) => ({ ...p, [index]: { status: "loading" } }));
    try {
      const token = await getToken();
      const res = await fetch(
        `${API_BASE}/api/v1/integrations/onedrive/video-url?user_email=${encodeURIComponent(video.ownerEmail)}&item_id=${encodeURIComponent(video.itemId)}`,
        { headers: { Authorization: `Bearer ${token}` } }
      );
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail ?? "Failed to load video");
      }
      const data = await res.json();
      setPlayers((p) => ({ ...p, [index]: { status: "ready", url: data.url } }));
      setTimeout(() => videoRef.current?.play().catch(() => {}), 150);
    } catch (e: unknown) {
      setPlayers((p) => ({
        ...p,
        [index]: { status: "error", error: e instanceof Error ? e.message : "Unknown error" },
      }));
    }
  };

  return (
    <div className="my-3 rounded-xl border overflow-hidden max-w-2xl bg-card">
      {/* Header */}
      <button
        className="w-full flex items-center gap-2 px-3 py-2.5 bg-muted/60 hover:bg-muted transition-colors text-left"
        onClick={() => setCollapsed((c) => !c)}
      >
        <Film className="size-4 text-muted-foreground shrink-0" />
        <span className="text-sm font-medium flex-1">
          {videos.length} Meeting Recording{videos.length !== 1 ? "s" : ""}
        </span>
        {collapsed ? (
          <ChevronDown className="size-4 text-muted-foreground" />
        ) : (
          <ChevronUp className="size-4 text-muted-foreground" />
        )}
      </button>

      {!collapsed && (
        <div className="divide-y">
          {videos.map((video, i) => {
            const player = players[i];
            const isActive = activeIndex === i;
            const dateStr = parseDate(video.filename);

            return (
              <div key={i}>
                {/* Row */}
                <button
                  className={cn(
                    "w-full flex items-center gap-3 px-3 py-2.5 text-left transition-colors",
                    isActive ? "bg-accent" : "hover:bg-accent/50"
                  )}
                  onClick={() => loadVideo(i, video)}
                >
                  {/* Play button indicator */}
                  <div className={cn(
                    "size-7 rounded-full flex items-center justify-center shrink-0 transition-colors",
                    isActive ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground"
                  )}>
                    {player?.status === "loading" ? (
                      <Loader2 className="size-3.5 animate-spin" />
                    ) : (
                      <Play className="size-3.5 ml-0.5" />
                    )}
                  </div>

                  {/* File info */}
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium truncate">{formatFilename(video.filename)}</p>
                    {dateStr && (
                      <p className="text-xs text-muted-foreground flex items-center gap-1 mt-0.5">
                        <Clock className="size-3" />
                        {dateStr}
                      </p>
                    )}
                  </div>

                  {/* Status badge */}
                  {player?.status === "error" && (
                    <AlertCircle className="size-4 text-destructive shrink-0" />
                  )}
                  {isActive && player?.status === "ready" && (
                    <span className="text-xs text-primary font-medium shrink-0">Playing</span>
                  )}
                </button>

                {/* Inline player (only for active item) */}
                {isActive && player && (
                  <div className="bg-black">
                    {player.status === "loading" && (
                      <div className="flex items-center justify-center py-8 gap-2">
                        <Loader2 className="size-5 text-white animate-spin" />
                        <span className="text-white/70 text-sm">Loading secure URL…</span>
                      </div>
                    )}
                    {player.status === "error" && (
                      <div className="flex flex-col items-center justify-center py-6 gap-2">
                        <AlertCircle className="size-5 text-red-400" />
                        <p className="text-red-300 text-xs">{player.error}</p>
                        <Button
                          size="sm" variant="ghost"
                          className="text-white/60 hover:text-white"
                          onClick={(e) => { e.stopPropagation(); loadVideo(i, video); }}
                        >
                          Retry
                        </Button>
                      </div>
                    )}
                    {player.status === "ready" && player.url && (
                      <video
                        ref={videoRef}
                        src={player.url}
                        controls
                        className="w-full max-h-[400px]"
                        preload="metadata"
                        onError={() =>
                          setPlayers((p) => ({
                            ...p,
                            [i]: { status: "error", error: "Playback failed — URL may have expired. Click the row to retry." },
                          }))
                        }
                      />
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
