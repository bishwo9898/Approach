"use client";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { CsvUpload } from "@/components/csv-upload";
import { EmptyState } from "@/components/ui/empty-state";
import { IdentityResolver } from "@/components/identity-resolver";
import { ImportTable } from "@/components/import-table";
import { Skeleton } from "@/components/ui/skeleton";
import { StatTile } from "@/components/stat-tile";
import { PageHeader } from "@/components/page-header";
import { Icon } from "@/components/ui/icons";
import {
  useCurrentUser,
  useImports,
  useIntegrationStatus,
  useMarkFuturesUpdated,
  usePendingFuturesUpdates,
  useUnresolvedIdentities,
} from "@/hooks/use-api";
import { formatMeasurement, formatRelative } from "@/lib/format";

/**
 * Operational visibility.
 *
 * Broken automation is shown, not hidden. A coach who does not know an import
 * failed will read a stale dashboard as if it were current, and make training
 * decisions on it.
 */
export default function OperationsPage() {
  const user = useCurrentUser();
  const health = useIntegrationStatus();
  const unresolved = useUnresolvedIdentities();
  const imports = useImports(15);
  const pending = usePendingFuturesUpdates();
  const markUpdated = useMarkFuturesUpdated();

  const isAdmin = user.data?.role === "ADMIN";

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Operations"
        title="Data health"
        description="Monitor TrackMan ingestion, resolve athlete identities, and keep downstream systems current."
      />

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {health.isLoading || !health.data ? (
          Array.from({ length: 4 }, (_, index) => (
            <Skeleton key={index} className="h-[104px]" />
          ))
        ) : (
          <>
            <StatTile
              label="Last Import"
              value={formatRelative(health.data.last_successful_import_at)}
              hint={health.data.last_import_status ?? "no imports yet"}
              icon="database"
              tone="blue"
            />
            <StatTile
              label="Awaiting Verification"
              value={health.data.sessions_awaiting_verification}
              hint="TrackMan has not republished these as verified"
              icon="sessions"
              tone="violet"
            />
            <StatTile
              label="Unresolved Athletes"
              value={health.data.unresolved_players}
              hint="data held until mapped"
              icon="players"
              tone="amber"
            />
            <StatTile
              label="Failed Imports (7d)"
              value={health.data.failed_imports_7d}
              icon="activity"
              tone="amber"
              hint="Review any rejected rows below"
            />
          </>
        )}
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Icon name="database" className="size-4 text-accent-foreground" /> Import a
            TrackMan export
          </CardTitle>
          <CardDescription>
            Re-uploading a file you have already imported is safe — it is detected and
            does nothing.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <CsvUpload />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Icon name="players" className="size-4 text-warning" /> Athlete mapping
            required
          </CardTitle>
          <CardDescription>
            TrackMan reported these athletes with no mapping to one of ours. Their data is
            held, not guessed at. Mapping one recovers their held sessions automatically.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {unresolved.isLoading ? (
            <Skeleton className="h-20 w-full" />
          ) : (
            <IdentityResolver items={unresolved.data ?? []} canResolve={isAdmin} />
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Import history</CardTitle>
          <CardDescription>
            Rejected rows are kept and shown — nothing is silently discarded.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {imports.isLoading ? (
            <Skeleton className="h-32 w-full" />
          ) : (
            <ImportTable imports={imports.data ?? []} />
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Futures updates pending</CardTitle>
          <CardDescription>
            No automated Futures integration is available yet. These are the exact values
            to enter; mark each one once you have.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {pending.isLoading ? (
            <Skeleton className="h-20 w-full" />
          ) : !pending.data || pending.data.length === 0 ? (
            <EmptyState
              title="Nothing waiting for Futures"
              description="Every record has been entered."
            />
          ) : (
            <ul className="divide-y divide-border">
              {pending.data.slice(0, 25).map((job) => (
                <li key={job.id} className="flex items-center gap-4 py-3 text-sm">
                  <div className="min-w-0 flex-1">
                    <p className="font-medium">{job.player_display_name}</p>
                    <p className="text-xs text-muted-foreground">
                      {job.destination_field}
                    </p>
                  </div>
                  <span className="tabular font-semibold">
                    {formatMeasurement(job.value, job.unit, 1)}
                  </span>
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={markUpdated.isPending}
                    onClick={() => markUpdated.mutate(job.id)}
                  >
                    Mark updated
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
