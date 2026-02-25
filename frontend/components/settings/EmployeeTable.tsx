"use client";

import { useState } from "react";
import { useAuth } from "@clerk/nextjs";
import { toast } from "sonner";
import { Trash2, Loader2, Mail } from "lucide-react";
import { Button } from "@/components/ui/button";
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

export interface OrgEmployee {
  id: string;
  name: string;
  work_email: string;
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

  if (employees.length === 0) {
    return (
      <div className="text-center py-10 text-muted-foreground text-sm">
        <Mail className="size-8 mx-auto mb-2 opacity-30" />
        <p>No employees added yet.</p>
        <p className="text-xs mt-1">
          Add employees to enable AI email queries like{" "}
          <em>"Show emails for Sarah Johnson"</em>.
        </p>
      </div>
    );
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Name</TableHead>
          <TableHead>Microsoft 365 Email</TableHead>
          <TableHead>Added</TableHead>
          {canManage && <TableHead className="w-12" />}
        </TableRow>
      </TableHeader>
      <TableBody>
        {employees.map((emp) => (
          <TableRow key={emp.id}>
            <TableCell className="font-medium">{emp.name}</TableCell>
            <TableCell className="font-mono text-xs text-green-700">
              {emp.work_email}
            </TableCell>
            <TableCell className="text-xs text-muted-foreground">
              {formatDistanceToNow(new Date(emp.created_at), { addSuffix: true })}
            </TableCell>
            {canManage && (
              <TableCell>
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
              </TableCell>
            )}
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
