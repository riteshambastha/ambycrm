"use client";

import { FileText, Video, ExternalLink, File } from "lucide-react";
import { SectionWrapper, type SectionData } from "./SectionWrapper";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

interface FileItem {
  name?: string;
  web_url?: string;
  last_modified?: string;
  size?: number;
  is_video?: boolean;
  owner?: string;
  item_id?: string;
}

function getFileExtension(name?: string): string {
  if (!name) return "";
  return name.split(".").pop()?.toLowerCase() || "";
}

function getFileBadgeColor(ext: string): string {
  if (["docx", "doc"].includes(ext)) return "text-blue-600 border-blue-300";
  if (["xlsx", "xls"].includes(ext)) return "text-green-600 border-green-300";
  if (["pptx", "ppt"].includes(ext)) return "text-orange-600 border-orange-300";
  if (["pdf"].includes(ext)) return "text-red-600 border-red-300";
  if (["mp4", "mov", "avi", "webm"].includes(ext)) return "text-purple-600 border-purple-300";
  return "text-muted-foreground";
}

function formatFileDate(iso?: string): string {
  if (!iso) return "";
  return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

function formatBytes(bytes?: number): string {
  if (!bytes) return "";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function FileRow({ file }: { file: FileItem }) {
  const ext = getFileExtension(file.name);
  const badgeColor = getFileBadgeColor(ext);
  const Icon = file.is_video ? Video : ext ? FileText : File;

  return (
    <div className="flex items-center gap-3 p-2.5 border rounded-lg hover:bg-muted/30 transition-colors">
      <Icon className={cn("size-4 shrink-0", file.is_video ? "text-purple-500" : "text-blue-500")} />
      <div className="flex-1 min-w-0">
        {file.web_url ? (
          <a
            href={file.web_url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-sm font-medium hover:underline text-foreground flex items-center gap-1 truncate"
          >
            {file.name || "Unnamed file"}
            <ExternalLink className="size-3 shrink-0 text-muted-foreground" />
          </a>
        ) : (
          <p className="text-sm font-medium truncate">{file.name || "Unnamed file"}</p>
        )}
        <p className="text-xs text-muted-foreground">
          {[formatFileDate(file.last_modified), formatBytes(file.size)].filter(Boolean).join(" · ")}
        </p>
      </div>
      {ext && (
        <Badge variant="outline" className={cn("text-xs uppercase shrink-0", badgeColor)}>
          {ext}
        </Badge>
      )}
    </div>
  );
}

interface FilesSectionProps {
  loading: boolean;
  data: SectionData | null;
  onRetry?: () => void;
  onRefresh?: () => void;
}

export function FilesSection({ loading, data, onRetry, onRefresh }: FilesSectionProps) {
  return (
    <SectionWrapper
      title="OneDrive / Drive Files"
      icon={<FileText className="size-4 text-green-500" />}
      loading={loading}
      data={data}
      onRetry={onRetry}
      onRefresh={onRefresh}
    >
      {(results) => (
        <div className="space-y-1.5">
          {(results as unknown as FileItem[]).map((file, i) => (
            <FileRow key={i} file={file} />
          ))}
        </div>
      )}
    </SectionWrapper>
  );
}
