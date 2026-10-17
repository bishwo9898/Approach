"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { PageHeader } from "@/components/page-header";
import { PlayerPicker } from "@/components/player-picker";
import { VideoUpload } from "@/components/video-upload";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { Icon } from "@/components/ui/icons";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import type { PlayerSummary } from "@/lib/types";

/** Clips of an athlete, which show up on that athlete's own page. */
export default function CoachMediaPage() {
  const [player, setPlayer] = useState<PlayerSummary | null>(null);
  const queryClient = useQueryClient();

  const videos = useQuery({
    queryKey: ["videos", player?.id],
    queryFn: () => api.playerVideos(player!.id),
    enabled: Boolean(player),
  });

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Media"
        title="Video"
        description="Upload clips for an athlete. They appear on that athlete's page."
      />

      <Card className="max-w-3xl">
        <CardHeader className="flex-row items-start gap-3 space-y-0">
          <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-blue-50 text-blue-600 ring-1 ring-blue-100">
            <Icon name="players" className="size-[18px]" />
          </span>
          <div>
            <CardTitle>Who is this footage of?</CardTitle>
            <CardDescription>
              A clip is filed under one athlete, and only they and their coaches can watch
              it.
            </CardDescription>
          </div>
        </CardHeader>
        <CardContent>
          <PlayerPicker value={player} onChange={setPlayer} />
        </CardContent>
      </Card>

      <Card className="max-w-3xl">
        <CardHeader className="flex-row items-start gap-3 space-y-0">
          <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-violet-50 text-violet-600 ring-1 ring-violet-100">
            <Icon name="sessions" className="size-[18px]" />
          </span>
          <div>
            <CardTitle>Clips</CardTitle>
            <CardDescription>
              MP4, MOV or WebM. The file is stored with the media provider, not in this
              database.
            </CardDescription>
          </div>
        </CardHeader>
        <CardContent>
          {!player ? (
            <EmptyState
              title="Choose an athlete first"
              description="So the clip can be shown on the right page, and only there."
            />
          ) : videos.isLoading ? (
            <Skeleton className="h-32 w-full" />
          ) : (
            <VideoUpload
              player={player}
              videos={videos.data ?? []}
              onChanged={() => {
                void queryClient.invalidateQueries({ queryKey: ["videos", player.id] });
                void queryClient.invalidateQueries({ queryKey: ["hitting"] });
              }}
            />
          )}
        </CardContent>
      </Card>
    </div>
  );
}
