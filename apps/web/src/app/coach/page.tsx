"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

/** The coach starts at the roster. There is no dashboard worth showing yet. */
export default function CoachIndexPage() {
  const router = useRouter();
  useEffect(() => {
    router.replace("/coach/players");
  }, [router]);
  return null;
}
