"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import { ApiError, api } from "@/lib/api";
import { formatDate } from "@/lib/format";
import type { AthleteVideo, PlayerSummary } from "@/lib/types";

/**
 * Uploading clips for one athlete, and seeing what they already have.
 *
 * The clip goes to the media provider; what is kept here is which athlete it
 * is of. A session is deliberately not required — a coach usually has the clip
 * before deciding where it belongs, and an untied clip still shows on the
 * athlete's own page.
 */
export function VideoUpload({
  player,
  videos,
  onChanged,
}: {
  player: PlayerSummary;
  videos: AthleteVideo[];
  onChanged: () => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const upload = async () => {
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      await api.uploadVideo({
        playerId: player.id,
        file,
        title: title.trim() || file.name,
        note: note.trim(),
      });
      setFile(null);
      setTitle("");
      setNote("");
      onChanged();
    } catch (cause) {
      setError(
        cause instanceof ApiError ? cause.message : "That video could not be uploaded.",
      );
    } finally {
      setBusy(false);
    }
  };

  const remove = async (video: AthleteVideo) => {
    // Takes the file down at the provider too -- a row deleted on its own
    // leaves footage of a minor hosted and reachable by anyone with the link.
    if (!window.confirm(`Delete “${video.title}”? This removes the file as well.`))
      return;
    try {
      await api.deleteVideo(video.id);
      onChanged();
    } catch (cause) {
      setError(
        cause instanceof ApiError ? cause.message : "That video could not be removed.",
      );
    }
  };

  return (
    <div className="space-y-5">
      <div className="space-y-2">
        <input
          type="file"
          accept="video/mp4,video/quicktime,video/webm"
          aria-label="Video file"
          onChange={(event) => setFile(event.target.files?.[0] ?? null)}
          className="block w-full text-xs text-muted-foreground file:mr-3 file:rounded-md file:border file:border-border file:bg-card file:px-3 file:py-1.5 file:text-xs file:font-medium"
        />
        <div className="grid gap-2 sm:grid-cols-2">
          <Input
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            placeholder="Title (optional)"
            aria-label="Video title"
          />
          <Input
            value={note}
            onChange={(event) => setNote(event.target.value)}
            placeholder="Note for the athlete (optional)"
            aria-label="Note"
          />
        </div>
        <Button disabled={!file || busy} onClick={() => void upload()}>
          {busy ? "Uploading…" : "Upload clip"}
        </Button>
        {error ? (
          <p className="text-xs text-negative" role="alert">
            {error}
          </p>
        ) : null}
      </div>

      {videos.length === 0 ? (
        <EmptyState
          title="No clips yet"
          description={`Anything uploaded here appears on ${player.display_name}'s own page.`}
        />
      ) : (
        <ul className="grid gap-3 sm:grid-cols-2">
          {videos.map((video) => (
            <li key={video.id}>
              <Card>
                <CardContent className="space-y-2 p-3">
                  <video
                    src={video.playback_url}
                    poster={video.thumbnail_url ?? undefined}
                    controls
                    preload="metadata"
                    className="aspect-video w-full rounded-md bg-black"
                  />
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium">{video.title}</p>
                      <p className="text-[11px] text-muted-foreground">
                        {formatDate(video.created_at)}
                        {video.session_id ? " · tied to a session" : ""}
                      </p>
                    </div>
                    <Button size="sm" variant="ghost" onClick={() => void remove(video)}>
                      Delete
                    </Button>
                  </div>
                  {video.note ? (
                    <p className="text-xs text-muted-foreground">{video.note}</p>
                  ) : null}
                </CardContent>
              </Card>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
