"use client";

import { useRef, useState } from "react";

import { useUploadCsv } from "@/hooks/use-api";
import { ApiError } from "@/lib/api";
import type { ImportResult } from "@/lib/types";

/**
 * Manual TrackMan CSV upload.
 *
 * The result is reported in full rather than as a checkmark. An import that
 * quietly rejected 40 rows or held an athlete back looks identical to a clean
 * one unless the numbers are shown, and the coach is the only person who will
 * notice that something is wrong.
 */
export function CsvUpload() {
  const inputRef = useRef<HTMLInputElement>(null);
  const upload = useUploadCsv();
  const [result, setResult] = useState<ImportResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const submit = async (file: File) => {
    setResult(null);
    setError(null);
    try {
      setResult(await upload.mutateAsync({ file }));
    } catch (cause) {
      setError(
        cause instanceof ApiError ? cause.message : "The upload could not be completed.",
      );
    } finally {
      if (inputRef.current) inputRef.current.value = "";
    }
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-3">
        {/* The native file input renders its own button; a second one beside it
            would just be two controls doing the same thing. */}
        <input
          ref={inputRef}
          type="file"
          accept=".csv,text/csv"
          aria-label="TrackMan CSV file"
          className="block w-full cursor-pointer text-sm text-muted-foreground file:mr-3 file:cursor-pointer file:rounded-md file:border file:border-border file:bg-background file:px-3 file:py-1.5 file:text-sm file:font-medium hover:file:bg-accent disabled:opacity-50"
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) void submit(file);
          }}
          disabled={upload.isPending}
        />
        {upload.isPending ? (
          <span className="whitespace-nowrap text-xs text-muted-foreground">
            Importing…
          </span>
        ) : null}
      </div>

      {error ? <p className="text-xs text-negative">{error}</p> : null}

      {result ? (
        result.is_duplicate ? (
          <p className="text-xs text-muted-foreground">
            These exact bytes were already imported. Nothing changed — re-uploading a file
            is always safe.
          </p>
        ) : (
          <dl className="grid grid-cols-2 gap-x-6 gap-y-1 rounded-md border border-border p-3 text-xs sm:grid-cols-3">
            <Row label="Status" value={result.status} />
            <Row
              label="Rows accepted"
              value={`${result.rows_accepted} / ${result.rows_total}`}
              alert={result.rows_rejected > 0}
            />
            <Row
              label="Sessions"
              value={`${result.sessions_created} new, ${result.sessions_updated} updated`}
            />
            <Row
              label="Events"
              value={`${result.pitch_events} pitches, ${result.hit_events} hits`}
            />
            <Row label="New PRs" value={String(result.new_personal_records)} />
            <Row
              label="Unresolved athletes"
              value={String(result.unresolved_players.length)}
              alert={result.unresolved_players.length > 0}
            />
          </dl>
        )
      ) : null}

      {result && result.unresolved_players.length > 0 ? (
        <p className="text-xs text-warning">
          Some events are being held because their athlete is not mapped. Map them below
          and their data will be recovered automatically.
        </p>
      ) : null}
    </div>
  );
}

function Row({
  label,
  value,
  alert = false,
}: {
  label: string;
  value: string;
  alert?: boolean;
}) {
  return (
    <div>
      <dt className="text-muted-foreground">{label}</dt>
      <dd
        className={alert ? "tabular font-semibold text-warning" : "tabular font-medium"}
      >
        {value}
      </dd>
    </div>
  );
}
