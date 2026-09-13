"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import { DEV_TOKENS, setToken } from "@/lib/session";

/**
 * Development sign-in.
 *
 * Phase 1 uses the backend's dev auth provider, whose tokens are seeded and not
 * secret. This entire page is replaced by Clerk's hosted sign-in once a Clerk
 * application exists -- nothing else in the app changes, because roles and
 * athlete scope are read from our database, never from the credential.
 */
export default function LoginPage() {
  const router = useRouter();
  const [token, setValue] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const signIn = async (candidate: string) => {
    setBusy(true);
    setError(null);
    setToken(candidate);
    try {
      const user = await api.me();
      router.replace(user.role === "PLAYER" ? "/player" : "/coach");
    } catch {
      setError("That token is not recognized. Run the seed script and try one below.");
      setBusy(false);
    }
  };

  return (
    <div className="mx-auto flex min-h-screen max-w-md items-center px-6">
      <Card className="w-full">
        <CardHeader>
          <CardTitle className="text-base">Sign in</CardTitle>
          <CardDescription>
            Development authentication. Replaced by Clerk before any real athlete data is
            loaded.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <form
            className="flex gap-2"
            onSubmit={(event) => {
              event.preventDefault();
              if (token.trim()) void signIn(token.trim());
            }}
          >
            <Input
              value={token}
              onChange={(event) => setValue(event.target.value)}
              placeholder="dev|coach"
              aria-label="Development token"
              autoComplete="off"
            />
            <Button type="submit" disabled={busy || !token.trim()}>
              Continue
            </Button>
          </form>

          {error ? <p className="text-xs text-negative">{error}</p> : null}

          <div className="space-y-2 border-t border-border pt-4">
            <p className="text-xs font-medium text-muted-foreground">Seeded accounts</p>
            <div className="grid gap-2">
              {DEV_TOKENS.map((entry) => (
                <button
                  key={entry.token}
                  type="button"
                  disabled={busy}
                  onClick={() => void signIn(entry.token)}
                  className="flex items-center justify-between rounded-md border border-border px-3 py-2 text-left text-sm transition-colors hover:bg-accent disabled:opacity-50"
                >
                  <span>{entry.label}</span>
                  <span className="text-xs text-muted-foreground">{entry.role}</span>
                </button>
              ))}
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
