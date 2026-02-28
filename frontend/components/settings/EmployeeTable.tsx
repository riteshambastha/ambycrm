"use client";

import { useState } from "react";
import { useAuth } from "@clerk/nextjs";
import { toast } from "sonner";
import { Trash2, Loader2, Mail, KeyRound, Check, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { apiClient } from "@/lib/api-client";
import { formatDistanceToNow } from "date-fns";

export interface OrgEmployee {
  id: string;
  name: string;
  work_email: string;
  is_login_enabled?: boolean;
  created_at: string;
}

interface EmployeeTableProps {
  employees: OrgEmployee[];
  orgId: string;
  canManage: boolean;
  onRefresh: () => void;
}

export function EmployeeTable({ employees, orgId, canManage, onRefresh }: EmployeeTableProps) {
  const { getToken } = useAuth();
  const [deletingId, setDeletingId] = useState<string | null>(null);

  // Password modal state
  const [passwordModal, setPasswordModal] = useState<{ id: string; name: string } | null>(null);
  const [password, setPassword] = useState("");
  const [isSettingPassword, setIsSettingPassword] = useState(false);

  const handleDelete = async (employeeId: string, name: string) => {
    setDeletingId(employeeId);
    try {
      const token = await getToken();
      if (!token) throw new Error("Not authenticated");
      await apiClient.delete(`/organizations/${orgId}/employees/${employeeId}`, token);
      toast.success(`${name} removed`);
      onRefresh();
    } catch (err: unknown) {
      toast.error((err as Error).message ?? "Failed to remove employee");
    } finally {
      setDeletingId(null);
    }
  };

  const handleSetPassword = async () => {
    if (!passwordModal) return;
    if (password.length < 8) {
      toast.error("Password must be at least 8 characters");
      return;
    }

    setIsSettingPassword(true);
    try {
      const token = await getToken();
      if (!token) throw new Error("Not authenticated");
      await apiClient.patch(
        `/organizations/${orgId}/employees/${passwordModal.id}/set-password`,
        { password },
        token
      );
      toast.success(`Login password set for ${passwordModal.name}`);
      setPasswordModal(null);
      setPassword("");
      onRefresh();
    } catch (err: unknown) {
      toast.error((err as Error).message ?? "Failed to set password");
    } finally {
      setIsSettingPassword(false);
    }
  };

  if (employees.length === 0) {
    return (
      <div className="text-center py-10 text-muted-foreground text-sm">
        <Mail className="size-8 mx-auto mb-2 opacity-30" />
        <p>No employees added yet.</p>
        <p className="text-xs mt-1">
          Add employees to enable AI email queries like{" "}
          <em>&quot;Show emails for Sarah Johnson&quot;</em>.
        </p>
      </div>
    );
  }

  return (
    <>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Name</TableHead>
            <TableHead>Microsoft 365 Email</TableHead>
            <TableHead>Login</TableHead>
            <TableHead>Added</TableHead>
            {canManage && <TableHead className="w-24" />}
          </TableRow>
        </TableHeader>
        <TableBody>
          {employees.map((emp) => (
            <TableRow key={emp.id}>
              <TableCell className="font-medium">{emp.name}</TableCell>
              <TableCell className="font-mono text-xs text-green-700">
                {emp.work_email}
              </TableCell>
              <TableCell>
                {emp.is_login_enabled ? (
                  <Badge variant="secondary" className="text-xs gap-1">
                    <ShieldCheck className="size-3" />
                    Enabled
                  </Badge>
                ) : (
                  <span className="text-xs text-muted-foreground">Disabled</span>
                )}
              </TableCell>
              <TableCell className="text-xs text-muted-foreground">
                {formatDistanceToNow(new Date(emp.created_at), { addSuffix: true })}
              </TableCell>
              {canManage && (
                <TableCell>
                  <div className="flex items-center gap-1">
                    <Button
                      variant="ghost"
                      size="sm"
                      className="size-8 p-0"
                      title={emp.is_login_enabled ? "Reset password" : "Set password"}
                      onClick={() => {
                        setPasswordModal({ id: emp.id, name: emp.name });
                        setPassword("");
                      }}
                    >
                      <KeyRound className="size-4" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="size-8 p-0 text-destructive hover:text-destructive"
                      onClick={() => handleDelete(emp.id, emp.name)}
                      disabled={deletingId === emp.id}
                    >
                      {deletingId === emp.id ? (
                        <Loader2 className="size-3 animate-spin" />
                      ) : (
                        <Trash2 className="size-4" />
                      )}
                    </Button>
                  </div>
                </TableCell>
              )}
            </TableRow>
          ))}
        </TableBody>
      </Table>

      {/* Set Password Dialog */}
      <Dialog open={passwordModal !== null} onOpenChange={(open) => { if (!open) setPasswordModal(null); }}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>
              {passwordModal?.name ? `Set login password` : "Set Password"}
            </DialogTitle>
            <DialogDescription>
              {passwordModal?.name
                ? `Set a password so ${passwordModal.name} can log in at /member-login and access their own data.`
                : "Set a login password for this employee."}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <div className="space-y-2">
              <Label htmlFor="emp-password">Password</Label>
              <Input
                id="emp-password"
                type="password"
                placeholder="Minimum 8 characters"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoFocus
                onKeyDown={(e) => {
                  if (e.key === "Enter") handleSetPassword();
                }}
              />
              <p className="text-xs text-muted-foreground">
                The employee will use this password along with their email to sign in.
                No email will be sent &mdash; share the password directly.
              </p>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setPasswordModal(null)}>
              Cancel
            </Button>
            <Button onClick={handleSetPassword} disabled={isSettingPassword || password.length < 8}>
              {isSettingPassword ? (
                <Loader2 className="size-4 mr-2 animate-spin" />
              ) : (
                <Check className="size-4 mr-2" />
              )}
              Set Password
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
