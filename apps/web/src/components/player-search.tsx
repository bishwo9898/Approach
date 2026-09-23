"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { EmptyState } from "@/components/ui/empty-state";
import { Icon } from "@/components/ui/icons";
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
      <div className="relative">
        <Icon
          name="search"
          className="pointer-events-none absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
        />
        <Input
          value={term}
          onChange={(event) => setTerm(event.target.value)}
          placeholder="Search athletes by name…"
          aria-label="Search athletes"
          autoFocus={autoFocus}
          className="h-11 pl-10"
        />
      </div>

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
        <ul className="divide-y divide-border overflow-hidden rounded-xl border border-border bg-card">
          {data.map((player) => (
            <li key={player.id}>
              <button
                type="button"
                data-testid="athlete-row"
                onClick={() => router.push(`/coach/players/${player.id}`)}
                className="group flex w-full items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-accent/60"
              >
                <span className="grid size-9 shrink-0 place-items-center rounded-xl bg-muted text-xs font-semibold text-muted-foreground">
                  {player.display_name
                    .split(" ")
                    .map((part) => part[0])
                    .slice(0, 2)
                    .join("")}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-medium">
                    {player.display_name}
                  </span>
                  <span className="block text-xs text-muted-foreground">
                    {[
                      player.position,
                      player.graduation_year && `Class of ${player.graduation_year}`,
                    ]
                      .filter(Boolean)
                      .join(" · ") || "Roster athlete"}
                  </span>
                </span>
                <Icon
                  name="arrow"
                  className="size-4 text-muted-foreground transition-transform group-hover:translate-x-0.5 group-hover:text-foreground"
                />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
