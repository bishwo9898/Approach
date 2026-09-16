"use client";

import { AppShell } from "@/components/app-shell";
import { AuthGate } from "@/components/auth-gate";

const NAV = [
  { href: "/coach", label: "Dashboard", icon: "home" as const },
  { href: "/coach/players", label: "Athletes", icon: "players" as const },
  { href: "/coach/operations", label: "Data Health", icon: "database" as const },
];

export default function CoachLayout({ children }: { children: React.ReactNode }) {
  return (
    <AuthGate allow={["COACH", "ADMIN"]}>
      <AppShell nav={NAV}>{children}</AppShell>
    </AuthGate>
  );
}
