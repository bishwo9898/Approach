"use client";

import { useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import { AuthCard } from "@/components/auth/auth-card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ApiError, api } from "@/lib/api";
import { endSession, startSession } from "@/lib/session";

function LoginForm() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const justCreated = useSearchParams().get("created") === "1";

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [needsSetup, setNeedsSetup] = useState(false);
  const [busy, setBusy] = useState(false);

  const signIn = async () => {
    setBusy(true);
    setError(null);
    setNeedsSetup(false);
    // Any previous session goes first, so a failed sign-in never leaves a stale
    // credential -- or a previous person's cached pages -- behind.
    endSession(queryClient);
    try {
      const session = await api.login(email, password);
      startSession(queryClient, session.token);
      router.replace(session.role === "PLAYER" ? "/player" : "/coach");
    } catch (cause) {
      if (cause instanceof ApiError && cause.code === "password_not_set") {
        setNeedsSetup(true);
        setError(cause.message);
      } else if (cause instanceof ApiError && cause.isUnreachable) {
        // Not a wrong password. Saying so would send someone retyping a
        // password that was correct all along.
        setError("Can't reach the server. It may be starting up — try again shortly.");
      } else {
        setError(
          cause instanceof ApiError ? cause.message : "Email or password is incorrect.",
        );
      }
      setBusy(false);
    }
  };

  const ready = email.trim().length > 0 && password.length > 0;

  return (
    <AuthCard>
      {justCreated ? (
        <p className="mb-4 rounded-md bg-positive/10 px-3 py-2 text-center text-xs text-positive">
          Password created. Sign in below.
        </p>
      ) : null}

      <form
        className="space-y-2.5"
        onSubmit={(event) => {
          event.preventDefault();
          if (ready) void signIn();
        }}
      >
        <Input
          type="email"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          placeholder="Email"
          aria-label="Email"
          autoComplete="username"
          autoFocus
          className="h-10"
        />
        <Input
          type="password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          placeholder="Password"
          aria-label="Password"
          autoComplete="current-password"
          className="h-10"
        />
        <Button type="submit" className="h-10 w-full" disabled={busy || !ready}>
          {busy ? "Signing in…" : "Sign in"}
        </Button>
      </form>

      <p className="mt-3 min-h-8 text-center text-xs text-negative" role="alert">
        {error}
      </p>

      <p className="text-center text-xs text-muted-foreground">
        <Link
          href={needsSetup ? `/activate?email=${encodeURIComponent(email)}` : "/activate"}
          className="underline underline-offset-2 hover:text-foreground"
        >
          {needsSetup ? "Set your password" : "First time? Set up your account"}
        </Link>
      </p>
    </AuthCard>
  );
}

export default function LoginPage() {
  // useSearchParams needs a Suspense boundary for a statically rendered page.
  return (
    <Suspense>
      <LoginForm />
    </Suspense>
  );
}
