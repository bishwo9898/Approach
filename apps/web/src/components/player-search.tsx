"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { usePlayerSearch } from "@/hooks/use-api";

/**
 * Roster search by first, last or preferred name.
 *
 * Names are a convenience for humans only -- matching one grants nothing and
 * maps nothing. Internal ids are never shown; the coach navigates by name.
 */
export function PlayerSearch({ autoFocus = false }: { autoFocus?: boolean }) {
  const router = useRouter();
  const [term, setTerm] = useState("");
  const [debounced, setDebounced] = useState("");

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(term), 180);
    return () => clearTimeout(timer);
  }, [term]);

  const { data, isLoading } = usePlayerSearch(debounced);

  return (
    <div className="space-y-3">
      <Input
        value={term}
        onChange={(event) => setTerm(event.target.value)}
        placeholder="Search athletes by name…"
        aria-label="Search athletes"
        autoFocus={autoFocus}
      />

      {isLoading ? (
        <div className="space-y-2">
          <Skeleton className="h-12 w-full" />
          <Skeleton className="h-12 w-full" />
        </div>
      ) : !data || data.length === 0 ? (
        <EmptyState
          title={debounced ? `No athletes match “${debounced}”` : "No athletes yet"}
          description={
            debounced
              ? "Check the spelling, or the athlete may not be on this roster."
              : "Import a TrackMan session to populate the roster."
          }
        />
      ) : (
        <ul className="divide-y divide-border overflow-hidden rounded-lg border border-border">
          {data.map((player) => (
            <li key={player.id}>
              <button
                type="button"
                onClick={() => router.push(`/coach/players/${player.id}`)}
                className="flex w-full items-center justify-between px-4 py-3 text-left transition-colors hover:bg-accent"
              >
                <span className="text-sm font-medium">{player.display_name}</span>
                <span className="text-xs text-muted-foreground">
                  {[
                    player.position,
                    player.graduation_year && `Class of ${player.graduation_year}`,
                  ]
                    .filter(Boolean)
                    .join(" · ")}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
