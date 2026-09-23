"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ApiError, api } from "@/lib/api";
import { setToken } from "@/lib/session";

export default function LoginPage() {
  const router = useRouter();
  const [passcode, setPasscode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const signIn = async () => {
    setBusy(true);
    setError(null);
    setToken(passcode);
    try {
      const user = await api.me();
      router.replace(user.role === "PLAYER" ? "/player" : "/coach");
    } catch (cause) {
      // An unreachable API is not a wrong passcode, and saying so would send
      // someone retyping a passcode that was correct all along.
      setError(
        cause instanceof ApiError && cause.isUnreachable
          ? "Can't reach the server. It may be starting up — try again shortly."
          : "Passcode not recognized.",
      );
      setBusy(false);
    }
  };

  return (
    <main className="grid min-h-screen place-items-center bg-background px-6">
      <div className="w-full max-w-[280px]">
        <div className="mb-10 flex items-center justify-center gap-2.5">
          <span className="grid size-8 place-items-center rounded-lg bg-primary">
            <span className="block size-3 rotate-45 rounded-[2px] border-2 border-primary-foreground" />
          </span>
          <span className="text-lg font-semibold tracking-tight">Approach</span>
        </div>

        <form
          className="space-y-2.5"
          onSubmit={(event) => {
            event.preventDefault();
            if (passcode.trim()) void signIn();
          }}
        >
          <Input
            type="password"
            value={passcode}
            onChange={(event) => setPasscode(event.target.value)}
            placeholder="Passcode"
            aria-label="Passcode"
            autoComplete="current-password"
            autoFocus
            className="h-10 text-center"
          />
          <Button
            type="submit"
            className="h-10 w-full"
            disabled={busy || !passcode.trim()}
          >
            {busy ? "Signing in…" : "Continue"}
          </Button>
        </form>

        <p className="mt-3 h-4 text-center text-xs text-negative" role="alert">
          {error}
        </p>

        {/* Stripped from the production bundle by the bundler's dead-code
            elimination, so deployed builds carry no hint at all. */}
        {process.env.NODE_ENV === "development" ? (
          <p className="mt-6 text-center text-[11px] text-muted-foreground">
            Development: <code>coach</code> or <code>player</code>
          </p>
        ) : null}
      </div>
    </main>
  );
}
