"use client";

import { CreditCard, Zap, Building2 } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

const PLANS = [
  {
    name: "Free",
    price: "$0",
    seats: 5,
    features: ["5 team members", "3 integrations", "100 AI queries/month"],
    current: true,
    icon: Zap,
  },
  {
    name: "Pro",
    price: "$49/mo",
    seats: 25,
    features: ["25 team members", "All integrations", "Unlimited AI queries", "Priority support"],
    current: false,
    icon: Building2,
  },
  {
    name: "Enterprise",
    price: "Custom",
    seats: 999,
    features: ["Unlimited members", "All integrations", "Unlimited AI queries", "SLA & SSO"],
    current: false,
    icon: CreditCard,
  },
];

export default function BillingPage() {
  return (
    <div className="p-6 max-w-4xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Billing & Plans</h1>
        <p className="text-muted-foreground text-sm mt-1">
          Manage your subscription and seat licenses.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {PLANS.map((plan) => {
          const Icon = plan.icon;
          return (
            <Card key={plan.name} className={plan.current ? "border-primary" : ""}>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle className="flex items-center gap-2">
                    <Icon className="size-4" />
                    {plan.name}
                  </CardTitle>
                  {plan.current && <Badge>Current</Badge>}
                </div>
                <p className="text-2xl font-bold">{plan.price}</p>
                <CardDescription>{plan.seats === 999 ? "Unlimited" : plan.seats} seats</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <ul className="space-y-2">
                  {plan.features.map((f) => (
                    <li key={f} className="text-sm flex items-center gap-2">
                      <span className="text-green-500">✓</span>
                      {f}
                    </li>
                  ))}
                </ul>
                <Button
                  className="w-full"
                  variant={plan.current ? "outline" : "default"}
                  disabled={plan.current}
                >
                  {plan.current ? "Current Plan" : plan.name === "Enterprise" ? "Contact Sales" : "Upgrade"}
                </Button>
              </CardContent>
            </Card>
          );
        })}
      </div>
    </div>
  );
}
