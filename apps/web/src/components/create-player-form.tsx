"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useCreatePlayer } from "@/hooks/use-api";
import { ApiError } from "@/lib/api";
import type { PlayerSummary } from "@/lib/types";

/**
 * Add an athlete to the roster.
 *
 * Only a name is required. Demanding position and class year up front would
 * make onboarding a thirty-athlete roster needlessly slow, and they are
 * coaching labels that can be filled in later.
 */
export function CreatePlayerForm({
  initialFirstName = "",
  initialLastName = "",
  submitLabel = "Create athlete",
  onCreated,
  onCancel,
}: {
  initialFirstName?: string;
  initialLastName?: string;
  submitLabel?: string;
  onCreated: (player: PlayerSummary) => void;
  onCancel?: () => void;
}) {
  const [firstName, setFirstName] = useState(initialFirstName);
  const [lastName, setLastName] = useState(initialLastName);
  const [position, setPosition] = useState("");
  const [graduationYear, setGraduationYear] = useState("");
  const [error, setError] = useState<string | null>(null);

  const create = useCreatePlayer();
  const canSubmit = firstName.trim().length > 0 && lastName.trim().length > 0;

  const submit = async () => {
    setError(null);
    const year = Number.parseInt(graduationYear, 10);
    try {
      onCreated(
        await create.mutateAsync({
          first_name: firstName.trim(),
          last_name: lastName.trim(),
          position: position.trim() || null,
          graduation_year: Number.isNaN(year) ? null : year,
        }),
      );
    } catch (cause) {
      setError(
        cause instanceof ApiError ? cause.message : "The athlete could not be created.",
      );
    }
  };

  return (
    <form
      className="space-y-3"
      onSubmit={(event) => {
        event.preventDefault();
        if (canSubmit) void submit();
      }}
    >
      <div className="grid gap-2 sm:grid-cols-2">
        <label className="space-y-1">
          <span className="text-xs text-muted-foreground">First name</span>
          <Input
            value={firstName}
            onChange={(event) => setFirstName(event.target.value)}
            placeholder="Ryan"
            autoFocus
          />
        </label>
        <label className="space-y-1">
          <span className="text-xs text-muted-foreground">Last name</span>
          <Input
            value={lastName}
            onChange={(event) => setLastName(event.target.value)}
            placeholder="Jones"
          />
        </label>
        <label className="space-y-1">
          <span className="text-xs text-muted-foreground">Position (optional)</span>
          <Input
            value={position}
            onChange={(event) => setPosition(event.target.value)}
            placeholder="RHP"
          />
        </label>
        <label className="space-y-1">
          <span className="text-xs text-muted-foreground">
            Graduation year (optional)
          </span>
          <Input
            value={graduationYear}
            onChange={(event) => setGraduationYear(event.target.value)}
            placeholder="2028"
            inputMode="numeric"
          />
        </label>
      </div>

      {error ? <p className="text-xs text-negative">{error}</p> : null}

      <div className="flex gap-2">
        <Button type="submit" size="sm" disabled={!canSubmit || create.isPending}>
          {create.isPending ? "Creating…" : submitLabel}
        </Button>
        {onCancel ? (
          <Button type="button" size="sm" variant="ghost" onClick={onCancel}>
            Cancel
          </Button>
        ) : null}
      </div>
    </form>
  );
}
