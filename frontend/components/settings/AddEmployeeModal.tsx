"use client";

import { useState } from "react";
import { useAuth } from "@clerk/nextjs";
import { toast } from "sonner";
import { UserPlus, Loader2 } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { apiClient } from "@/lib/api-client";

interface AddEmployeeModalProps {
  orgId: string;
  onAdded: () => void;
}

export function AddEmployeeModal({ orgId, onAdded }: AddEmployeeModalProps) {
  const { getToken } = useAuth();
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [workEmail, setWorkEmail] = useState("");
  const [loading, setLoading] = useState(false);

  const handleAdd = async () => {
    if (!name.trim() || !workEmail.trim()) return;
    setLoading(true);
    try {
      const token = await getToken();
      if (!token) throw new Error("Not authenticated");
      await apiClient.post(
        `/organizations/${orgId}/employees`,
        { name: name.trim(), work_email: workEmail.trim() },
        token
      );
      toast.success(`${name} added as an employee`);
      setOpen(false);
      setName("");
      setWorkEmail("");
      onAdded();
    } catch (err: unknown) {
      toast.error((err as Error).message ?? "Failed to add employee");
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") handleAdd();
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm">
          <UserPlus className="size-4 mr-2" />
          Add Employee
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Add Employee</DialogTitle>
          <DialogDescription>
            Register an employee's Microsoft 365 email so the AI can query their
            inbox. No humAInly account is required for the employee.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4 py-2">
          <div className="space-y-2">
            <Label htmlFor="emp-name">Full Name</Label>
            <Input
              id="emp-name"
              type="text"
              placeholder="Sarah Johnson"
              value={name}
              onChange={(e) => setName(e.target.value)}
              onKeyDown={handleKeyDown}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="emp-email">Microsoft 365 Work Email</Label>
            <Input
              id="emp-email"
              type="email"
              placeholder="sarah@yourcompany.com"
              value={workEmail}
              onChange={(e) => setWorkEmail(e.target.value)}
              onKeyDown={handleKeyDown}
            />
            <p className="text-xs text-muted-foreground">
              This must be the email address associated with their Microsoft 365
              account in your tenant.
            </p>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)}>
            Cancel
          </Button>
          <Button onClick={handleAdd} disabled={loading || !name.trim() || !workEmail.trim()}>
            {loading && <Loader2 className="size-4 mr-2 animate-spin" />}
            Add Employee
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
