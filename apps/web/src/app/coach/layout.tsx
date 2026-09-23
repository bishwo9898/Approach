"use client";

import { AppShell } from "@/components/app-shell";
import { AuthGate } from "@/components/auth-gate";

// Only what has real data behind it. A dashboard of zeroes and a progression
// chart with one point are worse than not showing them at all.
const NAV = [
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
