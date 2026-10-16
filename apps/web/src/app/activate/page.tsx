"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import { AuthCard } from "@/components/auth/auth-card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ApiError, api } from "@/lib/api";
import { passwordProblems } from "@/lib/password";
import type { ActivationTarget } from "@/lib/types";

/**
 * Setting up a provisioned account.
 *
 * Accounts already exist -- a coach creates them from the TrackMan roster -- so
 * this is not a sign-up. It is two steps: prove which account is yours, then
 * choose its password.
 *
 * The code field appears only if the server says this deployment needs one. It
 * is not shown up front because most athletes will never see it, and a field
 * nobody can fill in is worse than one that appears when it is relevant.
 */
function ActivateFlow() {
  const router = useRouter();
  const presetEmail = useSearchParams().get("email") ?? "";

  const [email, setEmail] = useState(presetEmail);
  const [code, setCode] = useState("");
  const [codeRequired, setCodeRequired] = useState(false);
  const [target, setTarget] = useState<ActivationTarget | null>(null);

  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [touched, setTouched] = useState(false);

  const [error, setError] = useState<string | null>(null);
  const [problems, setProblems] = useState<string[]>([]);
  const [alreadySetUp, setAlreadySetUp] = useState(false);
  const [busy, setBusy] = useState(false);

  const fail = (cause: unknown, fallback: string) => {
    if (cause instanceof ApiError) {
      if (cause.isUnreachable) {
        setError("Can't reach the server. It may be starting up — try again shortly.");
        return;
      }
      if (cause.code === "already_activated") {
        setAlreadySetUp(true);
      }
      if (cause.code === "activation_code_invalid") {
        setCodeRequired(true);
      }
      setProblems(cause.problems);
      setError(cause.message);
      return;
    }
    setError(fallback);
  };

  const checkEmail = async () => {
    setBusy(true);
    setError(null);
    setAlreadySetUp(false);
    try {
      setTarget(await api.checkEmail(email, code));
    } catch (cause) {
      fail(cause, "Email does not match.");
    } finally {
      setBusy(false);
    }
  };

  const createPassword = async () => {
    setBusy(true);
    setError(null);
    setProblems([]);
    try {
      await api.createPassword({
        email,
        password,
        passwordConfirmation: confirmation,
        code,
      });
      // Deliberately not signed in: using the new password straight away is
      // how someone finds out at once that they can reproduce it.
      router.replace("/login?created=1");
    } catch (cause) {
      fail(cause, "That password could not be set.");
      setBusy(false);
    }
  };

  const localProblems = passwordProblems(password, { email });
  const mismatch = confirmation.length > 0 && password !== confirmation;
  const canSubmitPassword =
    localProblems.length === 0 && confirmation.length > 0 && !mismatch;

  // -- step two: choose a password ------------------------------------------

  if (target) {
    return (
      <AuthCard>
        <p className="mb-1 text-center text-sm font-medium">
          {target.first_name ? `Hi ${target.first_name}` : "Choose a password"}
        </p>
        <p className="mb-5 break-all text-center text-xs text-muted-foreground">
          {target.email}
        </p>

        <form
          className="space-y-2.5"
          onSubmit={(event) => {
            event.preventDefault();
            if (canSubmitPassword) void createPassword();
          }}
        >
          <Input
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            onBlur={() => setTouched(true)}
            placeholder="New password"
            aria-label="New password"
            autoComplete="new-password"
            autoFocus
            className="h-10"
          />
          <Input
            type="password"
            value={confirmation}
            onChange={(event) => setConfirmation(event.target.value)}
            placeholder="Repeat password"
            aria-label="Repeat password"
            autoComplete="new-password"
            className="h-10"
          />
          <Button
            type="submit"
            className="h-10 w-full"
            disabled={busy || !canSubmitPassword}
          >
            {busy ? "Saving…" : "Create password"}
          </Button>
        </form>

        <div className="mt-3 min-h-16 text-xs" role="alert">
          {mismatch ? (
            <p className="text-negative">Those passwords do not match.</p>
          ) : null}
          {/* The server's own words win over the browser's hints. */}
          {problems.length > 0 ? (
            <ul className="space-y-0.5 text-negative">
              {problems.map((problem) => (
                <li key={problem}>{problem}</li>
              ))}
            </ul>
          ) : error ? (
            <p className="text-negative">{error}</p>
          ) : touched && localProblems.length > 0 ? (
            <ul className="space-y-0.5 text-muted-foreground">
              {localProblems.map((problem) => (
                <li key={problem}>{problem}</li>
              ))}
            </ul>
          ) : (
            /* The rules come from the server, so what is shown can never
               disagree with what is enforced. */
            <ul className="space-y-0.5 text-muted-foreground">
              {target.password_rules.map((rule) => (
                <li key={rule}>{rule}</li>
              ))}
            </ul>
          )}
        </div>
      </AuthCard>
    );
  }

  // -- step one: which account is yours? ------------------------------------

  const ready = email.trim().length > 0 && (!codeRequired || code.trim().length > 0);

  return (
    <AuthCard>
      <form
        className="space-y-2.5"
        onSubmit={(event) => {
          event.preventDefault();
          if (ready) void checkEmail();
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
        {codeRequired ? (
          <Input
            type="text"
            value={code}
            onChange={(event) => setCode(event.target.value)}
            placeholder="Activation code"
            aria-label="Activation code"
            autoComplete="one-time-code"
            autoCapitalize="characters"
            className="h-10 font-mono tracking-wider"
          />
        ) : null}
        <Button type="submit" className="h-10 w-full" disabled={busy || !ready}>
          {busy ? "Checking…" : "Continue"}
        </Button>
      </form>

      <p className="mt-3 min-h-8 text-center text-xs text-negative" role="alert">
        {error}
      </p>

      <p className="text-center text-xs text-muted-foreground">
        {alreadySetUp ? (
          <Link
            href="/login"
            className="underline underline-offset-2 hover:text-foreground"
          >
            Go to sign in
          </Link>
        ) : (
          <Link
            href="/login"
            className="underline underline-offset-2 hover:text-foreground"
          >
            Already set up? Sign in
          </Link>
        )}
      </p>
    </AuthCard>
  );
}

export default function ActivatePage() {
  return (
    <Suspense>
      <ActivateFlow />
    </Suspense>
  );
}
