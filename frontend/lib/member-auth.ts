"use client";

/**
 * Member (OrgEmployee) authentication utilities.
 * Stores JWT in localStorage, provides helpers for token management.
 */

const MEMBER_TOKEN_KEY = "member_token";

export function getMemberToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(MEMBER_TOKEN_KEY);
}

export function setMemberToken(token: string): void {
  localStorage.setItem(MEMBER_TOKEN_KEY, token);
}

export function clearMemberToken(): void {
  localStorage.removeItem(MEMBER_TOKEN_KEY);
}

export function isMemberAuthenticated(): boolean {
  const token = getMemberToken();
  if (!token) return false;
  try {
    const payload = JSON.parse(atob(token.split(".")[1]));
    const exp = payload.exp * 1000;
    return Date.now() < exp;
  } catch {
    return false;
  }
}

export function getMemberPayload(): {
  sub: string;
  org_id: string;
  email: string;
  type: string;
} | null {
  const token = getMemberToken();
  if (!token) return null;
  try {
    return JSON.parse(atob(token.split(".")[1]));
  } catch {
    return null;
  }
}
