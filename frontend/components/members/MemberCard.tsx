"use client";

import Link from "next/link";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Mail, Calendar } from "lucide-react";
import { cn } from "@/lib/utils";

export interface PersonOut {
  id: string;
  person_type: "member" | "employee";
  first_name: string | null;
  last_name: string | null;
  display_name: string;
  email: string | null;
  work_email: string | null;
  avatar_url: string | null;
  role: string | null;
  is_active: boolean;
  joined_at: string | null;
}

interface MemberCardProps {
  person: PersonOut;
}

function getInitials(name: string): string {
  const parts = name.trim().split(" ");
  if (parts.length >= 2) return `${parts[0][0]}${parts[1][0]}`.toUpperCase();
  return name.slice(0, 2).toUpperCase();
}

function formatDate(iso: string | null): string {
  if (!iso) return "";
  return new Date(iso).toLocaleDateString("en-US", { month: "short", year: "numeric" });
}

export function MemberCard({ person }: MemberCardProps) {
  const href =
    person.person_type === "member"
      ? `/members/m/${person.id}`
      : `/members/e/${person.id}`;

  return (
    <Link href={href}>
      <Card
        className={cn(
          "hover:shadow-md transition-shadow cursor-pointer border",
          !person.is_active && "opacity-60"
        )}
      >
        <CardContent className="p-4 flex items-start gap-3">
          <Avatar className="size-11 shrink-0">
            {person.avatar_url && <AvatarImage src={person.avatar_url} alt={person.display_name} />}
            <AvatarFallback className="text-sm font-semibold bg-primary/10 text-primary">
              {getInitials(person.display_name)}
            </AvatarFallback>
          </Avatar>

          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <p className="text-sm font-semibold truncate">{person.display_name}</p>
              {person.role && (
                <Badge variant={person.role === "org_admin" ? "default" : "secondary"} className="text-xs shrink-0">
                  {person.role === "org_admin" ? "Admin" : "Member"}
                </Badge>
              )}
              {person.person_type === "employee" && (
                <Badge variant="outline" className="text-xs shrink-0">Employee</Badge>
              )}
              {!person.is_active && (
                <Badge variant="destructive" className="text-xs shrink-0">Inactive</Badge>
              )}
            </div>

            {person.work_email && (
              <p className="text-xs text-muted-foreground flex items-center gap-1 mt-0.5 truncate">
                <Mail className="size-3 shrink-0" />
                {person.work_email}
              </p>
            )}

            {person.joined_at && (
              <p className="text-xs text-muted-foreground flex items-center gap-1 mt-0.5">
                <Calendar className="size-3 shrink-0" />
                Joined {formatDate(person.joined_at)}
              </p>
            )}
          </div>
        </CardContent>
      </Card>
    </Link>
  );
}
