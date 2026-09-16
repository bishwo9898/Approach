"use client";

import { PlayerSearch } from "@/components/player-search";
import { PageHeader } from "@/components/page-header";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Icon } from "@/components/ui/icons";

export default function CoachPlayersPage() {
  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Roster"
        title="Athletes"
        description="Find an athlete and open their complete performance profile, records, and session history."
      />
      <Card className="max-w-3xl">
        <CardHeader className="flex-row items-start gap-3 space-y-0">
          <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-blue-50 text-blue-600 ring-1 ring-blue-100">
            <Icon name="players" className="size-[18px]" />
          </span>
          <div>
            <CardTitle>Search the roster</CardTitle>
            <CardDescription>
              Search by first, last, or preferred name. Athlete data stays scoped to your
              organization.
            </CardDescription>
          </div>
        </CardHeader>
        <CardContent>
          <PlayerSearch autoFocus />
        </CardContent>
      </Card>
    </div>
  );
}
