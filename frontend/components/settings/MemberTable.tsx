"use client";

import { useState } from "react";
import { useAuth } from "@clerk/nextjs";
import { toast } from "sonner";
import { MoreHorizontal, ShieldCheck, UserX, Loader2, Mail } from "lucide-react";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { apiClient } from "@/lib/api-client";
import { formatDistanceToNow } from "date-fns";

export interface Member {
  id: string;
  user_id: string;
  email: string | null;
  first_name: string | null;
  last_name: string | null;
  avatar_url: string | null;
  role: string;
  is_active: boolean;
  work_email: string | null;
  joined_at: string;
}

interface MemberTableProps {
  members: Member[];
  orgId: string;
  currentUserId?: string;
  canManage: boolean;
  onRefresh: () => void;
}

export function MemberTable({ members, orgId, currentUserId, canManage, onRefresh }: MemberTableProps) {
  const { getToken } = useAuth();
  const [loadingId, setLoadingId] = useState<string | null>(null);

  // Work-email dialog state
  const [workEmailTarget, setWorkEmailTarget] = useState<Member | null>(null);
  const [workEmailInput, setWorkEmailInput] = useState("");
  const [savingWorkEmail, setSavingWorkEmail] = useState(false);

  const handleDeactivate = async (memberId: string) => {
    setLoadingId(memberId);
    try {
      const token = await getToken();
      await apiClient.patch(`/organizations/${orgId}/members/${memberId}/deactivate`, {}, token!);
      toast.success("Member deactivated");
      onRefresh();
    } catch (err: unknown) {
      toast.error((err as Error).message);
    } finally {
      setLoadingId(null);
    }
  };

  const handleRoleChange = async (memberId: string, newRole: string) => {
    setLoadingId(memberId);
    try {
      const token = await getToken();
      await apiClient.patch(
        `/organizations/${orgId}/members/${memberId}/role?role=${newRole}`,
        {},
        token!
      );
      toast.success("Role updated");
      onRefresh();
    } catch (err: unknown) {
      toast.error((err as Error).message);
    } finally {
      setLoadingId(null);
    }
  };

  const openWorkEmailDialog = (member: Member) => {
    setWorkEmailTarget(member);
    setWorkEmailInput(member.work_email ?? "");
  };

  const handleSaveWorkEmail = async () => {
    if (!workEmailTarget) return;
    setSavingWorkEmail(true);
    try {
      const token = await getToken();
      await apiClient.patch(
        `/organizations/${orgId}/members/${workEmailTarget.id}/work-email`,
        { work_email: workEmailInput || null },
        token!
      );
      toast.success("Work email updated");
      setWorkEmailTarget(null);
      onRefresh();
    } catch (err: unknown) {
      toast.error((err as Error).message);
    } finally {
      setSavingWorkEmail(false);
    }
  };

  const getInitials = (m: Member) => {
    const name = [m.first_name, m.last_name].filter(Boolean).join(" ");
    const fallback = m.email ?? m.work_email ?? "?";
    return name ? name.slice(0, 2).toUpperCase() : fallback.slice(0, 2).toUpperCase();
  };

  return (
    <>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Member</TableHead>
            <TableHead>Work Email (M365)</TableHead>
            <TableHead>Role</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Joined</TableHead>
            {canManage && <TableHead className="w-12" />}
          </TableRow>
        </TableHeader>
        <TableBody>
          {members.map((member) => (
            <TableRow key={member.id} className={!member.is_active ? "opacity-50" : ""}>
              <TableCell>
                <div className="flex items-center gap-3">
                  <Avatar className="size-8">
                    <AvatarImage src={member.avatar_url ?? undefined} />
                    <AvatarFallback className="text-xs">{getInitials(member)}</AvatarFallback>
                  </Avatar>
                  <div>
                    <p className="text-sm font-medium">
                      {[member.first_name, member.last_name].filter(Boolean).join(" ") ||
                        member.email ||
                        "—"}
                    </p>
                    <p className="text-xs text-muted-foreground">{member.email ?? "—"}</p>
                  </div>
                </div>
              </TableCell>
              <TableCell className="text-xs">
                {member.work_email ? (
                  <span className="text-green-700 font-mono">{member.work_email}</span>
                ) : (
                  <span className="text-muted-foreground italic">Not set</span>
                )}
              </TableCell>
              <TableCell>
                <Badge variant={member.role === "org_admin" ? "default" : "secondary"} className="text-xs">
                  {member.role === "org_admin" ? (
                    <><ShieldCheck className="size-3 mr-1" />Admin</>
                  ) : (
                    "Member"
                  )}
                </Badge>
              </TableCell>
              <TableCell>
                <Badge variant={member.is_active ? "outline" : "destructive"} className="text-xs">
                  {member.is_active ? "Active" : "Deactivated"}
                </Badge>
              </TableCell>
              <TableCell className="text-xs text-muted-foreground">
                {formatDistanceToNow(new Date(member.joined_at), { addSuffix: true })}
              </TableCell>
              {canManage && (
                <TableCell>
                  {member.user_id !== currentUserId && member.is_active && (
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button variant="ghost" size="sm" className="size-8 p-0">
                          {loadingId === member.id ? (
                            <Loader2 className="size-3 animate-spin" />
                          ) : (
                            <MoreHorizontal className="size-4" />
                          )}
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuItem onClick={() => openWorkEmailDialog(member)}>
                          <Mail className="size-4 mr-2" />
                          Set Work Email (M365)
                        </DropdownMenuItem>
                        <DropdownMenuSeparator />
                        {member.role === "user" ? (
                          <DropdownMenuItem onClick={() => handleRoleChange(member.id, "org_admin")}>
                            <ShieldCheck className="size-4 mr-2" />
                            Make Admin
                          </DropdownMenuItem>
                        ) : (
                          <DropdownMenuItem onClick={() => handleRoleChange(member.id, "user")}>
                            Remove Admin
                          </DropdownMenuItem>
                        )}
                        <DropdownMenuSeparator />
                        <DropdownMenuItem
                          onClick={() => handleDeactivate(member.id)}
                          className="text-destructive focus:text-destructive"
                        >
                          <UserX className="size-4 mr-2" />
                          Deactivate
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  )}
                </TableCell>
              )}
            </TableRow>
          ))}
        </TableBody>
      </Table>

      {/* Work Email Dialog */}
      <Dialog open={!!workEmailTarget} onOpenChange={(open) => { if (!open) setWorkEmailTarget(null); }}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>Set Work Email</DialogTitle>
            <DialogDescription>
              This is the Microsoft 365 email address used for org-level email queries.
              It is typically the employee's company email (e.g.{" "}
              <code>john@yourcompany.com</code>).
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2 py-2">
            <Label htmlFor="work-email-input">Microsoft 365 Email</Label>
            <Input
              id="work-email-input"
              type="email"
              placeholder="employee@yourcompany.com"
              value={workEmailInput}
              onChange={(e) => setWorkEmailInput(e.target.value)}
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setWorkEmailTarget(null)}>
              Cancel
            </Button>
            <Button onClick={handleSaveWorkEmail} disabled={savingWorkEmail}>
              {savingWorkEmail && <Loader2 className="size-4 mr-2 animate-spin" />}
              Save
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
