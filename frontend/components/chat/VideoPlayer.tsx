"use client";

import { useState, useRef } from "react";
import { useAuth } from "@clerk/nextjs";
import { Play, Loader2, AlertCircle, Film } from "lucide-react";
import { Button } from "@/components/ui/button";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface VideoPlayerProps {
  ownerEmail: string;
  itemId: string;
  filename: string;
}

export function VideoPlayer({ ownerEmail, itemId, filename }: VideoPlayerProps) {
  const { getToken } = useAuth();
  const [state, setState] = useState<"idle" | "loading" | "ready" | "error">("idle");
  const [videoUrl, setVideoUrl] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState("");
  const videoRef = useRef<HTMLVideoElement>(null);

  const loadVideo = async () => {
    setState("loading");
    try {
      const token = await getToken();
      const res = await fetch(
        `${API_BASE}/api/v1/integrations/onedrive/video-url?user_email=${encodeURIComponent(ownerEmail)}&item_id=${encodeURIComponent(itemId)}`,
        { headers: { Authorization: `Bearer ${token}` } }
      );
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail ?? "Failed to load video");
      }
      const data = await res.json();
      setVideoUrl(data.url);
      setState("ready");
      // Auto-play once URL is set (browser policy: muted or user-gesture)
      setTimeout(() => videoRef.current?.play().catch(() => {}), 100);
    } catch (e: unknown) {
      setErrorMsg(e instanceof Error ? e.message : "Unknown error");
      setState("error");
    }
  };

  return (
    <div className="my-3 rounded-xl overflow-hidden border bg-black/90 max-w-2xl">
      {/* Header bar */}
      <div className="flex items-center gap-2 px-3 py-2 bg-background/10">
        <Film className="size-4 text-white/70 shrink-0" />
        <span className="text-xs text-white/80 truncate flex-1">{filename}</span>
      </div>

      {state === "idle" && (
        <div className="flex flex-col items-center justify-center py-12 gap-3">
          <div className="size-16 rounded-full bg-white/10 flex items-center justify-center">
            <Play className="size-7 text-white ml-1" />
          </div>
          <p className="text-white/60 text-xs">Click to load and play recording</p>
          <Button size="sm" onClick={loadVideo} className="bg-white/20 hover:bg-white/30 text-white border-white/20">
            <Play className="size-3.5 mr-1.5" />
            Load Recording
          </Button>
        </div>
      )}

      {state === "loading" && (
        <div className="flex items-center justify-center py-12 gap-2">
          <Loader2 className="size-5 text-white animate-spin" />
          <span className="text-white/70 text-sm">Loading secure URL…</span>
        </div>
      )}

      {state === "error" && (
        <div className="flex flex-col items-center justify-center py-10 gap-2">
          <AlertCircle className="size-5 text-red-400" />
          <p className="text-red-300 text-xs text-center px-4">{errorMsg}</p>
          <Button size="sm" variant="ghost" onClick={loadVideo} className="text-white/60 hover:text-white mt-1">
            Retry
          </Button>
        </div>
      )}

      {state === "ready" && videoUrl && (
        <video
          ref={videoRef}
          src={videoUrl}
          controls
          className="w-full max-h-[420px] bg-black"
          preload="metadata"
          onError={() => {
            setState("error");
            setErrorMsg("Video failed to load. The URL may have expired — click Retry.");
          }}
        />
      )}
    </div>
  );
}
