"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";

import { Icon, type IconName } from "@/components/ui/icons";
import { useCurrentUser } from "@/hooks/use-api";
import { clearToken } from "@/lib/session";
import { cn } from "@/lib/utils";

type NavItem = { href: string; label: string; icon?: IconName };

function Brand() {
  return (
    <Link href="/" className="flex items-center gap-3" aria-label="Approach home">
      <span className="surface-grid grid size-9 place-items-center rounded-xl bg-white/10 ring-1 ring-white/15">
        <span className="block size-3.5 rotate-45 rounded-[3px] border-2 border-blue-300" />
      </span>
      <span>
        <span className="block text-[15px] font-semibold tracking-tight text-white">
          Approach
        </span>
        <span className="block text-[10px] font-medium uppercase tracking-[0.14em] text-slate-400">
          Player Development
        </span>
      </span>
    </Link>
  );
}

export function AppShell({
  children,
  nav = [],
}: {
  children: React.ReactNode;
  nav?: NavItem[];
}) {
  const pathname = usePathname();
  const router = useRouter();
  const { data: user } = useCurrentUser();

  const signOut = () => {
    clearToken();
    router.replace("/login");
  };

  const isActive = (href: string) =>
    href === "/coach" || href === "/player"
      ? pathname === href
      : pathname.startsWith(href);
  const initials = user?.display_name
    .split(" ")
    .map((part) => part[0])
    .slice(0, 2)
    .join("");

  return (
    <div className="min-h-screen">
      <aside className="surface-grid fixed inset-y-0 left-0 z-30 hidden w-64 flex-col bg-[#0b1730] px-4 py-5 text-white lg:flex">
        <div className="px-2">
          <Brand />
        </div>
        <div className="mt-8 px-2">
          <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-500">
            Workspace
          </p>
          <p className="mt-1 truncate text-sm font-medium text-slate-200">
            {user?.organization_name ?? "Baseball Analytics"}
          </p>
        </div>
        <nav className="mt-6 space-y-1" aria-label="Primary navigation">
          {nav.map((item) => {
            const active = isActive(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "group flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm transition-all",
                  active
                    ? "bg-white/10 font-medium text-white shadow-sm ring-1 ring-white/10"
                    : "text-slate-400 hover:bg-white/[0.06] hover:text-slate-100",
                )}
              >
                <Icon
                  name={item.icon ?? "home"}
                  className={cn(
                    "size-[18px]",
                    active
                      ? "text-blue-300"
                      : "text-slate-500 group-hover:text-slate-300",
                  )}
                />
                {item.label}
                {active ? (
                  <span className="ml-auto size-1.5 rounded-full bg-blue-300" />
                ) : null}
              </Link>
            );
          })}
        </nav>
        <div className="mt-auto rounded-2xl border border-white/10 bg-white/[0.045] p-3">
          <div className="flex items-center gap-3">
            <span className="grid size-9 shrink-0 place-items-center rounded-xl bg-blue-400/15 text-xs font-semibold text-blue-200 ring-1 ring-blue-300/20">
              {initials || "—"}
            </span>
            <div className="min-w-0 flex-1">
              <p className="truncate text-xs font-medium text-slate-100">
                {user?.display_name ?? "Loading…"}
              </p>
              <p className="mt-0.5 text-[10px] uppercase tracking-wider text-slate-500">
                {user?.role.toLowerCase() ?? ""}
              </p>
            </div>
            <button
              type="button"
              onClick={signOut}
              className="rounded-lg p-2 text-slate-500 transition-colors hover:bg-white/10 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-400"
              aria-label="Sign out"
              title="Sign out"
            >
              <Icon name="logout" className="size-4" />
            </button>
          </div>
        </div>
      </aside>

      <div className="lg:pl-64">
        <header className="sticky top-0 z-20 border-b border-border/80 bg-background/90 backdrop-blur-xl lg:hidden">
          <div className="flex h-16 items-center justify-between px-4 sm:px-6">
            <div className="rounded-xl bg-[#0b1730] px-3 py-2">
              <Brand />
            </div>
            <button
              type="button"
              onClick={signOut}
              className="rounded-lg border border-border bg-card p-2.5 text-muted-foreground shadow-sm"
              aria-label="Sign out"
            >
              <Icon name="logout" className="size-4" />
            </button>
          </div>
          {nav.length > 0 ? (
            <nav className="flex gap-1 overflow-x-auto px-4 pb-3 sm:px-6">
              {nav.map((item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  className={cn(
                    "flex shrink-0 items-center gap-2 rounded-lg px-3 py-2 text-xs font-medium",
                    isActive(item.href)
                      ? "bg-primary text-primary-foreground"
                      : "text-muted-foreground",
                  )}
                >
                  <Icon name={item.icon ?? "home"} className="size-3.5" />
                  {item.label}
                </Link>
              ))}
            </nav>
          ) : null}
        </header>
        <main className="mx-auto min-h-screen max-w-[1440px] px-4 py-6 sm:px-7 sm:py-8 xl:px-10 xl:py-10">
          {children}
        </main>
      </div>
    </div>
  );
}
