"use client";

import { useState } from "react";

import { PageHeader } from "@/components/page-header";
import { PlayerPicker } from "@/components/player-picker";
import { ScreenshotUpload } from "@/components/screenshot-upload";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { Icon } from "@/components/ui/icons";
import type { PlayerSummary } from "@/lib/types";

/**
 * Importing a session for one athlete.
 *
 * Choosing the athlete first is the point. The conversion then writes the CSV
 * under their canonical name and registers the TrackMan identity it will carry,
 * so the pitches attach to them on import instead of waiting in the mapping
 * queue — and with 63 shared names on this roster, nothing is left to be
 * matched afterwards.
 */
export default function CoachImportsPage() {
  const [player, setPlayer] = useState<PlayerSummary | null>(null);

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Imports"
        title="Add a session"
        description="Pick the athlete, then upload the TrackMan screenshots of their pitches."
      />

      <Card className="max-w-3xl">
        <CardHeader className="flex-row items-start gap-3 space-y-0">
          <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-blue-50 text-blue-600 ring-1 ring-blue-100">
            <Icon name="players" className="size-[18px]" />
          </span>
          <div>
            <CardTitle>Whose session is this?</CardTitle>
            <CardDescription>
              The pitches are filed under this athlete, so they appear on their page.
            </CardDescription>
          </div>
        </CardHeader>
        <CardContent>
          <PlayerPicker value={player} onChange={setPlayer} />
        </CardContent>
      </Card>

      <Card className="max-w-3xl">
        <CardHeader className="flex-row items-start gap-3 space-y-0">
          <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-emerald-50 text-emerald-600 ring-1 ring-emerald-100">
            <Icon name="database" className="size-[18px]" />
          </span>
          <div>
            <CardTitle>Screenshots</CardTitle>
            <CardDescription>
              Read into a CSV, archived alongside it, and imported — but only if every
              pitch reads cleanly.
            </CardDescription>
          </div>
        </CardHeader>
        <CardContent>
          {player ? (
            <ScreenshotUpload playerId={player.id} />
          ) : (
            <EmptyState
              title="Choose an athlete first"
              description="So the system knows whose pitches these are, and where to show them."
            />
          )}
        </CardContent>
      </Card>
    </div>
  );
}
