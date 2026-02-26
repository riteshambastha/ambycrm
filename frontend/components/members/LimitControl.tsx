"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { RefreshCw } from "lucide-react";

interface LimitControlProps {
  value: number;
  onChange: (limit: number) => void;
  onRefresh: () => void;
  isRefreshing?: boolean;
}

export function LimitControl({ value, onChange, onRefresh, isRefreshing }: LimitControlProps) {
  const [inputVal, setInputVal] = useState(String(value));

  function handleChange(raw: string) {
    setInputVal(raw);
    const n = parseInt(raw, 10);
    if (!isNaN(n) && n >= 1 && n <= 50) {
      onChange(n);
    }
  }

  return (
    <div className="flex items-center gap-3">
      <div className="flex items-center gap-2">
        <Label htmlFor="limit-input" className="text-sm text-muted-foreground whitespace-nowrap">
          Items per section
        </Label>
        <Input
          id="limit-input"
          type="number"
          min={1}
          max={50}
          step={5}
          value={inputVal}
          onChange={(e) => handleChange(e.target.value)}
          className="w-16 h-8 text-sm"
        />
      </div>
      <Button
        variant="outline"
        size="sm"
        onClick={onRefresh}
        disabled={isRefreshing}
        className="h-8 gap-1.5"
      >
        <RefreshCw className={`size-3.5 ${isRefreshing ? "animate-spin" : ""}`} />
        {isRefreshing ? "Refreshing…" : "Refresh all"}
      </Button>
    </div>
  );
}
