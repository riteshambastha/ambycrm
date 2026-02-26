"use client";

import { useState } from "react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

interface LimitControlProps {
  value: number;
  onChange: (limit: number) => void;
}

export function LimitControl({ value, onChange }: LimitControlProps) {
  const [inputVal, setInputVal] = useState(String(value));

  function handleChange(raw: string) {
    setInputVal(raw);
    const n = parseInt(raw, 10);
    if (!isNaN(n) && n >= 1 && n <= 50) {
      onChange(n);
    }
  }

  return (
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
  );
}
