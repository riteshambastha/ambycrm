"use client";

import Link from "next/link";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ArrowLeft, Mail, Briefcase, Calendar, ExternalLink } from "lucide-react";
import type { PersonOut } from "./MemberCard";

interface ProfileHeaderProps {
  person: PersonOut;
  isAdmin?: boolean;
}

function getInitials(name: string): string {
  const parts = name.trim().split(" ");
  if (parts.length >= 2) return `${parts[0][0]}${parts[1][0]}`.toUpperCase();
  return name.slice(0, 2).toUpperCase();
}

function formatDate(iso: string | null): string {
  if (!iso) return "";
  return new Date(iso).toLocaleDateString("en-US", {
    month: "long",
    day: "numeric",
    year: "numeric",
  });
}

export function ProfileHeader({ person, isAdmin }: ProfileHeaderProps) {
  const settingsHref =
    person.person_type === "member"
      ? "/settings/organization/members"
      : "/settings/organization/members";

  return (
    <div className="space-y-4">
      <Button variant="ghost" size="sm" asChild className="text-muted-foreground -ml-2">
        <Link href="/members">
          <ArrowLeft className="size-4 mr-1" />
          All Members
        </Link>
      </Button>

      <div className="flex items-start gap-4">
        <Avatar className="size-16 shrink-0">
          {person.avatar_url && (
            <AvatarImage src={person.avatar_url} alt={person.display_name} />
          )}
          <AvatarFallback className="text-xl font-bold bg-primary/10 text-primary">
            {getInitials(person.display_name)}
          </AvatarFallback>
        </Avatar>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h1 className="text-2xl font-bold">{person.display_name}</h1>
            {person.role && (
              <Badge variant={person.role === "org_admin" ? "default" : "secondary"}>
                {person.role === "org_admin" ? "Admin" : "Member"}
              </Badge>
            )}
            {person.person_type === "employee" && (
              <Badge variant="outline">M365 Employee</Badge>
            )}
            {!person.is_active && (
              <Badge variant="destructive">Inactive</Badge>
            )}
          </div>

          <div className="mt-1.5 space-y-1">
            {person.email && (
              <p className="text-sm text-muted-foreground flex items-center gap-1.5">
                <Mail className="size-3.5" />
                {person.email}
              </p>
            )}
            {person.work_email && (
              <p className="text-sm text-muted-foreground flex items-center gap-1.5">
                <Briefcase className="size-3.5" />
                {person.work_email}
                <span className="text-xs bg-muted px-1.5 py-0.5 rounded">work</span>
              </p>
            )}
            {!person.work_email && (
              <p className="text-sm text-amber-600 flex items-center gap-1.5">
                <Briefcase className="size-3.5" />
                No work email set — connector data unavailable.
                {isAdmin && (
                  <Link href={settingsHref} className="underline inline-flex items-center gap-0.5 ml-1">
                    Set it <ExternalLink className="size-3" />
                  </Link>
                )}
              </p>
            )}
            {person.joined_at && (
              <p className="text-sm text-muted-foreground flex items-center gap-1.5">
                <Calendar className="size-3.5" />
                Joined {formatDate(person.joined_at)}
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
