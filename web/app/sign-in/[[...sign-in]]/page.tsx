import { SignIn } from "@clerk/nextjs";
import Link from "next/link";
import { isClerkServerConfigured } from "@/lib/clerk-config";

export default function SignInPage() {
  if (!isClerkServerConfigured()) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-[var(--background)] px-4 text-center text-[var(--foreground)]">
        <p className="max-w-md text-sm text-[var(--muted-foreground)]">
          Clerk is not configured. Set{" "}
          <code className="rounded bg-[var(--secondary)] px-1 py-0.5 text-xs">
            NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY
          </code>{" "}
          and{" "}
          <code className="rounded bg-[var(--secondary)] px-1 py-0.5 text-xs">
            CLERK_SECRET_KEY
          </code>{" "}
          in <code className="text-xs">web/.env.local</code>, then restart the dev
          server.
        </p>
        <Link
          href="/chat"
          className="text-sm font-medium text-[var(--foreground)] underline underline-offset-4"
        >
          Back to app
        </Link>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-[var(--background)] px-4 py-8">
      <SignIn
        routing="path"
        path="/sign-in"
        signUpUrl="/sign-up"
        appearance={{
          variables: {
            colorPrimary: "var(--foreground)",
            colorText: "var(--foreground)",
            colorTextSecondary: "var(--muted-foreground)",
            colorBackground: "var(--background)",
            colorInputBackground: "var(--secondary)",
            colorInputText: "var(--foreground)",
          },
        }}
      />
    </div>
  );
}
