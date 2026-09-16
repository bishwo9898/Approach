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
import { Icon } from "@/components/ui/icons";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import { DEV_TOKENS, setToken } from "@/lib/session";

/** Development sign-in, replaced by the production identity provider. */
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
    <main className="grid min-h-screen lg:grid-cols-[minmax(0,1.05fr)_minmax(440px,0.95fr)]">
      <section className="surface-grid relative hidden overflow-hidden bg-[#0b1730] p-12 text-white lg:flex lg:flex-col xl:p-16">
        <div className="absolute -left-20 top-1/3 size-80 rounded-full bg-blue-500/20 blur-3xl" />
        <div className="relative flex items-center gap-3">
          <span className="grid size-11 place-items-center rounded-2xl bg-white/10 ring-1 ring-white/15">
            <span className="block size-4 rotate-45 rounded-[3px] border-2 border-blue-300" />
          </span>
          <div>
            <p className="text-lg font-semibold tracking-tight">Approach</p>
            <p className="text-[10px] font-medium uppercase tracking-[0.16em] text-slate-400">
              Player Development
            </p>
          </div>
        </div>
        <div className="relative my-auto max-w-xl">
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-blue-300">
            Turn every session into progress
          </p>
          <h1 className="mt-5 text-4xl font-semibold leading-[1.12] tracking-[-0.035em] xl:text-5xl">
            The clearest view of athlete performance.
          </h1>
          <p className="mt-6 max-w-lg text-base leading-relaxed text-slate-300">
            Track trends, surface personal records, and give every coach and athlete the
            context they need to take the next step.
          </p>
          <div className="mt-10 grid gap-3 sm:grid-cols-3">
            <Feature icon="activity" label="Session trends" />
            <Feature icon="trophy" label="Personal records" />
            <Feature icon="database" label="Trusted data" />
          </div>
        </div>
        <p className="relative text-xs text-slate-500">
          Built for thoughtful, data-informed player development.
        </p>
      </section>

      <section className="flex items-center justify-center px-5 py-10 sm:px-10">
        <div className="w-full max-w-md">
          <div className="mb-7 lg:hidden">
            <p className="text-xl font-semibold tracking-tight">Approach</p>
            <p className="text-xs text-muted-foreground">Player Development</p>
          </div>
          <Card className="shadow-[0_18px_55px_rgba(15,23,42,0.09)]">
            <CardHeader className="pb-5">
              <span className="mb-2 grid size-10 place-items-center rounded-xl bg-blue-50 text-blue-600 ring-1 ring-blue-100">
                <Icon name="sparkles" className="size-[18px]" />
              </span>
              <CardTitle className="text-xl">Welcome back</CardTitle>
              <CardDescription>
                Sign in to open your performance workspace.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-5">
              <form
                className="space-y-3"
                onSubmit={(event) => {
                  event.preventDefault();
                  if (token.trim()) void signIn(token.trim());
                }}
              >
                <label className="block text-xs font-medium" htmlFor="dev-token">
                  Development token
                </label>
                <Input
                  id="dev-token"
                  value={token}
                  onChange={(event) => setValue(event.target.value)}
                  placeholder="dev|coach"
                  autoComplete="off"
                />
                <Button className="w-full" type="submit" disabled={busy || !token.trim()}>
                  {busy ? "Opening workspace…" : "Continue"}
                </Button>
              </form>
              {error ? (
                <p className="rounded-lg bg-negative/10 px-3 py-2 text-xs text-negative">
                  {error}
                </p>
              ) : null}
              <div className="border-t border-border pt-5">
                <div className="flex items-center justify-between">
                  <p className="text-xs font-medium">Seeded accounts</p>
                  <span className="rounded-full bg-muted px-2 py-1 text-[10px] font-medium text-muted-foreground">
                    Development only
                  </span>
                </div>
                <div className="mt-3 grid gap-2">
                  {DEV_TOKENS.map((entry) => (
                    <button
                      key={entry.token}
                      type="button"
                      disabled={busy}
                      onClick={() => void signIn(entry.token)}
                      className="group flex items-center gap-3 rounded-xl border border-border px-3 py-2.5 text-left transition-all hover:border-blue-200 hover:bg-blue-50/50 disabled:opacity-50"
                    >
                      <span className="grid size-8 place-items-center rounded-lg bg-muted text-xs font-semibold text-muted-foreground">
                        {entry.label[0]}
                      </span>
                      <span className="flex-1 text-sm font-medium">{entry.label}</span>
                      <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                        {entry.role}
                      </span>
                      <Icon
                        name="arrow"
                        className="size-3.5 text-muted-foreground transition-transform group-hover:translate-x-0.5"
                      />
                    </button>
                  ))}
                </div>
              </div>
            </CardContent>
          </Card>
          <p className="mt-5 text-center text-[11px] leading-relaxed text-muted-foreground">
            Athlete access is permission-scoped. Players only see their own performance
            data.
          </p>
        </div>
      </section>
    </main>
  );
}

function Feature({
  icon,
  label,
}: {
  icon: "activity" | "trophy" | "database";
  label: string;
}) {
  return (
    <div className="flex items-center gap-2 rounded-xl border border-white/10 bg-white/[0.05] px-3 py-3 text-xs font-medium text-slate-200">
      <Icon name={icon} className="size-4 text-blue-300" />
      {label}
    </div>
  );
}
