"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ApiError, api } from "@/lib/api";
import type { ScreenshotConversion } from "@/lib/types";

/**
 * Converting TrackMan screenshots into pitches.
 *
 * The screenshots are read by OCR, reconciled with each other, and imported --
 * but **only if every pitch read cleanly.** Anything the reader would not
 * believe stops the import and is listed here by pitch and column, because a
 * number nobody checked is worse than a number nobody has.
 *
 * The one requirement the coach has to meet is stated up front rather than
 * discovered on failure: every screenshot must include the header row.
 */
export function ScreenshotUpload({ playerId }: { playerId: string }) {
  const [files, setFiles] = useState<File[]>([]);
  const [sessionDate, setSessionDate] = useState("");
  const [opponent, setOpponent] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ScreenshotConversion | null>(null);

  const ready = files.length > 0 && sessionDate;

  const convert = async () => {
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      setResult(
        await api.convertScreenshots({
          files,
          playerId,
          sessionDate,
          opponentName: opponent.trim(),
        }),
      );
    } catch (cause) {
      setError(
        cause instanceof ApiError
          ? cause.message
          : "Those screenshots could not be read.",
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="rounded-md border border-dashed border-border px-4 py-3 text-xs text-muted-foreground">
        <p className="font-medium text-foreground">What the screenshots need</p>
        <ul className="mt-1.5 list-disc space-y-0.5 pl-4">
          <li>
            Include the header row — <strong>PITCH SPEED … LAUNCH ANGLE</strong>. Columns
            are read by name, and a screenshot without it is refused rather than guessed
            at.
          </li>
          <li>
            Overlap them by a row or two. A pitch read twice is a pitch checked twice.
          </li>
          <li>Keep the pitch numbers visible on the left.</li>
        </ul>
      </div>

      <div className="grid gap-2 sm:grid-cols-2">
        <Input
          type="date"
          value={sessionDate}
          onChange={(event) => setSessionDate(event.target.value)}
          aria-label="Session date"
        />
        <Input
          value={opponent}
          onChange={(event) => setOpponent(event.target.value)}
          placeholder="Opponent (optional)"
          aria-label="Opponent"
        />
      </div>

      <input
        type="file"
        accept="image/png,image/jpeg"
        multiple
        aria-label="TrackMan screenshots"
        onChange={(event) => setFiles(Array.from(event.target.files ?? []))}
        className="block w-full text-xs text-muted-foreground file:mr-3 file:rounded-md file:border file:border-border file:bg-card file:px-3 file:py-1.5 file:text-xs file:font-medium"
      />

      <Button disabled={!ready || busy} onClick={() => void convert()}>
        {busy
          ? "Reading…"
          : `Convert ${files.length || ""} screenshot${files.length === 1 ? "" : "s"}`}
      </Button>

      {error ? (
        <p className="text-xs text-negative" role="alert">
          {error}
        </p>
      ) : null}

      {result ? <ConversionReport result={result} /> : null}
    </div>
  );
}

function ConversionReport({ result }: { result: ScreenshotConversion }) {
  const blocking = result.problems.filter((p) => p.blocking);
  const notices = result.problems.filter((p) => !p.blocking);

  return (
    <Card>
      <CardContent className="space-y-3 p-4 text-xs">
        <p className="text-sm font-medium">
          {result.pitches} pitch{result.pitches === 1 ? "" : "es"} read
          {result.first_pitch !== null && result.last_pitch !== null
            ? ` (#${result.first_pitch}–#${result.last_pitch})`
            : ""}
          , {result.batted_balls} with a measured batted ball
        </p>

        {result.imported ? (
          <p className="text-positive">
            Imported — {result.imported.pitch_events} pitches and{" "}
            {result.imported.hit_events} batted balls are now on the athlete&apos;s page.
          </p>
        ) : (
          <p className="text-negative">
            Not imported. {blocking.length} value{blocking.length === 1 ? "" : "s"} could
            not be read, and those pitches are not in the file.
          </p>
        )}

        {blocking.length > 0 ? (
          <div>
            <p className="font-medium text-foreground">Needs a look</p>
            <ul className="mt-1 space-y-1">
              {blocking.map((problem, index) => (
                <li key={index} className="text-muted-foreground">
                  {problem.event_number !== null ? (
                    <span className="font-medium text-foreground">
                      #{problem.event_number}{" "}
                    </span>
                  ) : null}
                  {problem.message}
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        {notices.length > 0 ? (
          <p className="text-muted-foreground">
            {notices.length} cell{notices.length === 1 ? "" : "s"} were not recognized and
            read as “no measurement”. That is almost always TrackMan&apos;s dash, which
            OCR routinely drops.
          </p>
        ) : null}

        {result.csv_key ? (
          <p className="text-muted-foreground">
            Archived as <code>{result.csv_key}</code>, with the screenshots it came from.
          </p>
        ) : null}
      </CardContent>
    </Card>
  );
}
