"use client";

import { AppShell } from "@/components/app-shell";
import { AuthGate } from "@/components/auth-gate";

const NAV = [
  { href: "/coach", label: "Dashboard" },
  { href: "/coach/players", label: "Players" },
  { href: "/coach/operations", label: "Data Health" },
];

export default function CoachLayout({ children }: { children: React.ReactNode }) {
  return (
    <AuthGate allow={["COACH", "ADMIN"]}>
      <AppShell nav={NAV}>{children}</AppShell>
    </AuthGate>
  );
}
