import { NextRequest, NextResponse } from "next/server";
import { auth } from "@clerk/nextjs/server";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function GET(req: NextRequest) {
  const { getToken } = await auth();
  const token = await getToken();
  const { searchParams } = new URL(req.url);

  const code = searchParams.get("code");
  const state = searchParams.get("state");
  const error = searchParams.get("error");

  if (error) {
    return NextResponse.redirect(
      new URL(`/connections?error=${encodeURIComponent(error)}`, req.url)
    );
  }

  if (!code || !state) {
    return NextResponse.redirect(new URL("/connections?error=missing_params", req.url));
  }

  // Parse connector key from state (format: orgId:connectorKey:nonce)
  const parts = state.split(":");
  if (parts.length < 2) {
    return NextResponse.redirect(new URL("/connections?error=invalid_state", req.url));
  }
  const connectorKey = parts[1];

  try {
    const res = await fetch(`${API_BASE}/api/v1/integrations/oauth/callback`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ code, state, connector_key: connectorKey, org_id: parts[0] }),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      return NextResponse.redirect(
        new URL(`/connections?error=${encodeURIComponent(err.detail ?? "oauth_failed")}`, req.url)
      );
    }

    return NextResponse.redirect(new URL("/connections?success=true", req.url));
  } catch {
    return NextResponse.redirect(new URL("/connections?error=server_error", req.url));
  }
}
