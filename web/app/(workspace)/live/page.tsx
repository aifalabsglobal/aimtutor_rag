"use client";

import { useCallback } from "react";
import { useAuth } from "@clerk/nextjs";
import { LiveSession } from "@/components/live/LiveSession";
import { isClerkPublishableConfigured } from "@/lib/clerk-config";

const LOCAL_DEV_USER = "local-dev-user";

/**
 * Live Voice Session — page entry point.
 *
 * Mirrors `web/components/auth/SidebarAuth.tsx`:
 *   - Outer component checks `isClerkPublishableConfigured()` so
 *     `useAuth()` is only called inside a `<ClerkProvider>` tree.
 *   - When Clerk is not configured we hand the WS the literal
 *     `local-dev-user` string (matches the backend's non-Clerk branch).
 */
export default function LiveSessionPage() {
  if (!isClerkPublishableConfigured()) {
    return <LiveSessionLocalDev />;
  }
  return <LiveSessionWithClerk />;
}

function LiveSessionLocalDev() {
  const getToken = useCallback(async () => LOCAL_DEV_USER, []);
  return <LiveSession getToken={getToken} />;
}

function LiveSessionWithClerk() {
  const { getToken } = useAuth();

  const resolveToken = useCallback(async () => {
    try {
      const token = await getToken();
      return token ?? null;
    } catch {
      return null;
    }
  }, [getToken]);

  return <LiveSession getToken={resolveToken} />;
}
