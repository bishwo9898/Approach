"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import { useCurrentUser } from "@/hooks/use-api";
import { clearToken } from "@/lib/session";
import { cn } from "@/lib/utils";

export function AppShell({
  children,
  nav = [],
}: {
  children: React.ReactNode;
  nav?: Array<{ href: string; label: string }>;
}) {
  const pathname = usePathname();
  const router = useRouter();
  const { data: user } = useCurrentUser();

  const signOut = () => {
    clearToken();
    router.replace("/login");
  };

  return (
    <div className="min-h-screen">
      <header className="border-b border-border bg-card">
        <div className="mx-auto flex h-14 max-w-6xl items-center gap-6 px-6">
          <Link href="/" className="text-sm font-semibold tracking-tight">
            {user?.organization_name ?? "Baseball Analytics"}
          </Link>
          <nav className="flex items-center gap-1">
            {nav.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "rounded-md px-3 py-1.5 text-sm transition-colors",
                  pathname === item.href
                    ? "bg-accent font-medium text-accent-foreground"
                    : "text-muted-foreground hover:text-foreground",
                )}
              >
                {item.label}
              </Link>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-3">
            {user ? (
              <span className="text-xs text-muted-foreground">
                {user.display_name} · {user.role}
              </span>
            ) : null}
            <Button variant="outline" size="sm" onClick={signOut}>
              Sign out
            </Button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-6 py-6">{children}</main>
    </div>
  );
}
