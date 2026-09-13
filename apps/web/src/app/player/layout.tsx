"use client";

import { AppShell } from "@/components/app-shell";
import { AuthGate } from "@/components/auth-gate";

export default function PlayerLayout({ children }: { children: React.ReactNode }) {
  return (
    <AuthGate allow={["PLAYER"]}>
      <AppShell>{children}</AppShell>
    </AuthGate>
  );
}
