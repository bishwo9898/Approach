"use client";

import { PlayerSearch } from "@/components/player-search";

export default function CoachPlayersPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">Athletes</h1>
        <p className="text-sm text-muted-foreground">
          Search the roster by first, last or preferred name.
        </p>
      </div>
      <div className="max-w-2xl">
        <PlayerSearch autoFocus />
      </div>
    </div>
  );
}
