"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import { usePlayerSearch, useResolveIdentity } from "@/hooks/use-api";
import { ApiError } from "@/lib/api";
import { formatRelative } from "@/lib/format";
import type { UnresolvedIdentity } from "@/lib/types";

/**
 * Maps an unknown TrackMan athlete to one of ours.
 *
 * The athlete must be chosen explicitly. There is no "looks like this one"
 * suggestion and no auto-match, because a wrong mapping silently corrupts two
 * athletes' histories at once and nobody would think to look for it.
 *
 * The vendor's display name is shown only so an operator can recognize who they
 * are looking at — it is never used to match.
 */
export function IdentityResolver({
  items,
  canResolve,
}: {
  items: UnresolvedIdentity[];
  canResolve: boolean;
}) {
  // Confirmations live here rather than in the row. A successful mapping
  // refetches the queue, which unmounts the row that performed it -- leaving
  // the admin with no record of what was recovered.
  const [confirmations, setConfirmations] = useState<string[]>([]);

  return (
    <div className="space-y-3">
      {confirmations.map((message, index) => (
        <p
          key={index}
          className="rounded-md border border-positive/30 bg-positive/5 px-3 py-2 text-xs text-positive"
        >
          {message}
        </p>
      ))}

      {items.length === 0 ? (
        <EmptyState
          title="Every athlete is mapped"
          description="No TrackMan identities are waiting on a decision."
        />
      ) : (
        <ul className="divide-y divide-border">
          {items.map((item) => (
            <UnresolvedRow
              key={item.id}
              item={item}
              canResolve={canResolve}
              onResolved={(message) =>
                setConfirmations((previous) => [...previous, message])
              }
            />
          ))}
        </ul>
      )}
    </div>
  );
}

function UnresolvedRow({
  item,
  canResolve,
  onResolved,
}: {
  item: UnresolvedIdentity;
  canResolve: boolean;
  onResolved: (message: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [term, setTerm] = useState("");
  const [error, setError] = useState<string | null>(null);

  const { data: candidates } = usePlayerSearch(term);
  const resolve = useResolveIdentity();

  const map = async (playerId: string) => {
    setError(null);
    try {
      const result = await resolve.mutateAsync({ itemId: item.id, playerId });
      const imports = result.imports_reprocessed;
      const records = result.new_personal_records;
      onResolved(
        `${item.external_id} mapped to ${result.player.display_name}. ` +
          `${imports} import${imports === 1 ? "" : "s"} reprocessed` +
          (records > 0
            ? `, ${records} personal record${records === 1 ? "" : "s"} recovered.`
            : "."),
      );
      setOpen(false);
    } catch (cause) {
      setError(
        cause instanceof ApiError ? cause.message : "The mapping could not be saved.",
      );
    }
  };

  return (
    <li className="space-y-3 py-3 text-sm">
      <div className="flex items-center gap-4">
        <div className="min-w-0 flex-1">
          <p className="font-medium">{item.external_display_name ?? "Unnamed athlete"}</p>
          <p className="text-xs text-muted-foreground">
            {item.provider} id {item.external_id} · {item.occurrence_count} events held ·
            last seen {formatRelative(item.last_seen_at)}
          </p>
        </div>
        {canResolve ? (
          <Button
            size="sm"
            variant={open ? "ghost" : "outline"}
            onClick={() => setOpen(!open)}
          >
            {open ? "Cancel" : "Map athlete"}
          </Button>
        ) : (
          <span className="text-xs text-muted-foreground">Admin mapping required</span>
        )}
      </div>

      {open ? (
        <div className="space-y-2 rounded-md border border-border bg-muted/30 p-3">
          <p className="text-xs text-muted-foreground">
            Choose the athlete this TrackMan id belongs to. Their held sessions will be
            reprocessed and attributed.
          </p>
          <Input
            value={term}
            onChange={(event) => setTerm(event.target.value)}
            placeholder="Search athletes by name…"
            aria-label={`Search athletes to map ${item.external_id}`}
            autoFocus
          />
          <div className="max-h-48 divide-y divide-border overflow-y-auto rounded-md border border-border bg-background">
            {(candidates ?? []).length === 0 ? (
              <p className="px-3 py-2 text-xs text-muted-foreground">
                No athletes match. They may need to be created first.
              </p>
            ) : (
              (candidates ?? []).map((player) => (
                <button
                  key={player.id}
                  type="button"
                  disabled={resolve.isPending}
                  onClick={() => void map(player.id)}
                  className="flex w-full items-center justify-between px-3 py-2 text-left text-sm transition-colors hover:bg-accent disabled:opacity-50"
                >
                  <span>{player.display_name}</span>
                  <span className="text-xs text-muted-foreground">
                    {[player.position, player.graduation_year]
                      .filter(Boolean)
                      .join(" · ")}
                  </span>
                </button>
              ))
            )}
          </div>
          {error ? <p className="text-xs text-negative">{error}</p> : null}
        </div>
      ) : null}
    </li>
  );
}
