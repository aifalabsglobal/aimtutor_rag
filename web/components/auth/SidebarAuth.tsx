"use client";

import { SignInButton, useAuth, UserButton } from "@clerk/nextjs";
import { LogIn } from "lucide-react";
import { useTranslation } from "react-i18next";
import { isClerkPublishableConfigured } from "@/lib/clerk-config";

interface SidebarAuthProps {
  collapsed: boolean;
}

/** Renders nothing when Clerk env is unset (no `ClerkProvider` in the tree). */
export function SidebarAuth(props: SidebarAuthProps) {
  if (!isClerkPublishableConfigured()) {
    return null;
  }
  return <SidebarAuthWithClerk {...props} />;
}

function SidebarAuthWithClerk({ collapsed }: SidebarAuthProps) {
  const { t } = useTranslation();
  const { isSignedIn, isLoaded } = useAuth();

  if (!isLoaded) {
    return collapsed ? (
      <div className="h-9 w-9 shrink-0 rounded-xl bg-[var(--background)]/30" aria-hidden />
    ) : (
      <div className="mx-3 h-10 rounded-lg bg-[var(--background)]/30" aria-hidden />
    );
  }

  if (collapsed) {
    return (
      <div className="flex w-full flex-col items-center gap-1">
        {isSignedIn ? (
          <div className="flex h-9 w-9 items-center justify-center">
            <UserButton
              appearance={{
                elements: {
                  avatarBox: "h-8 w-8 ring-1 ring-[var(--border)]/60",
                },
              }}
            />
          </div>
        ) : (
          <SignInButton mode="modal">
            <button
              type="button"
              title={t("Sign in") as string}
              aria-label={t("Sign in") as string}
              className="flex h-9 w-9 items-center justify-center rounded-xl text-[var(--muted-foreground)] transition-colors hover:bg-[var(--background)]/50 hover:text-[var(--foreground)]"
            >
              <LogIn size={16} strokeWidth={1.7} />
            </button>
          </SignInButton>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-px">
      {isSignedIn ? (
        <div className="flex items-center gap-2 rounded-lg px-3 py-2">
          <UserButton
            appearance={{
              elements: {
                avatarBox: "h-8 w-8 ring-1 ring-[var(--border)]/60",
              },
            }}
          />
          <span className="truncate text-[13.5px] text-[var(--muted-foreground)]">
            {t("Account")}
          </span>
        </div>
      ) : (
        <SignInButton mode="modal">
          <button
            type="button"
            className="flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-[13.5px] text-[var(--muted-foreground)] transition-colors hover:bg-[var(--background)]/60 hover:text-[var(--foreground)]"
          >
            <LogIn size={16} strokeWidth={1.7} />
            <span>{t("Sign in")}</span>
          </button>
        </SignInButton>
      )}
    </div>
  );
}
