"use client";

import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Icon } from "@/components/ui/icons";
import { Input } from "@/components/ui/input";
import { usePlayerSearch } from "@/hooks/use-api";
import type { PlayerSummary } from "@/lib/types";

/**
 * Choose which athlete something belongs to.
 *
 * Deliberately a picker rather than a text field. Typing a name leaves the
 * system matching it afterwards, and with 482 athletes and 63 shared names
 * that match is exactly the thing that cannot be guessed. Picking states who
 * it is, once, before anything is uploaded.
 */
export function PlayerPicker({
  value,
  onChange,
  label = "Athlete",
}: {
  value: PlayerSummary | null;
  onChange: (player: PlayerSummary | null) => void;
  label?: string;
}) {
  const [term, setTerm] = useState("");
  const [debounced, setDebounced] = useState("");

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(term), 180);
    return () => clearTimeout(timer);
  }, [term]);

  const { data, isLoading } = usePlayerSearch(debounced);

  if (value) {
    return (
      <div className="flex items-center justify-between gap-3 rounded-md border border-border bg-card px-3 py-2">
        <span className="min-w-0">
          <span className="block truncate text-sm font-medium">{value.display_name}</span>
          <span className="block text-[11px] text-muted-foreground">{label}</span>
        </span>
        <Button size="sm" variant="outline" onClick={() => onChange(null)}>
          Change
        </Button>
      </div>
    );
  }

  const results = (data ?? []).slice(0, 8);

  return (
    <div className="space-y-2">
      <div className="relative">
        <Icon
          name="search"
          className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
        />
        <Input
          value={term}
          onChange={(event) => setTerm(event.target.value)}
          placeholder={`Search for the ${label.toLowerCase()}…`}
          aria-label={`Search for the ${label.toLowerCase()}`}
          className="pl-9"
        />
      </div>

      {debounced && !isLoading ? (
        results.length === 0 ? (
          <p className="px-1 text-xs text-muted-foreground">
            No athlete matches “{debounced}”.
          </p>
        ) : (
          <ul className="divide-y divide-border overflow-hidden rounded-md border border-border bg-card">
            {results.map((player) => (
              <li key={player.id}>
                <button
                  type="button"
                  onClick={() => {
                    onChange(player);
                    setTerm("");
                  }}
                  className="flex w-full items-center justify-between px-3 py-2 text-left text-sm transition-colors hover:bg-accent/60"
                >
                  {player.display_name}
                  <Icon name="arrow" className="size-3.5 text-muted-foreground" />
                </button>
              </li>
            ))}
          </ul>
        )
      ) : null}
    </div>
  );
}
