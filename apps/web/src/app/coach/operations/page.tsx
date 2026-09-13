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
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">Data Health</h1>
        <p className="text-sm text-muted-foreground">
          TrackMan ingestion, athlete mapping, and Futures updates.
        </p>
      </div>

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
            />
            <StatTile
              label="Awaiting Verification"
              value={health.data.sessions_awaiting_verification}
              hint="TrackMan has not republished these as verified"
            />
            <StatTile
              label="Unresolved Athletes"
              value={health.data.unresolved_players}
              hint="data held until mapped"
            />
            <StatTile label="Failed Imports (7d)" value={health.data.failed_imports_7d} />
          </>
        )}
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Import a TrackMan Export</CardTitle>
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
          <CardTitle>Athlete Mapping Required</CardTitle>
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
          <CardTitle>Import History</CardTitle>
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
          <CardTitle>Futures Updates Pending</CardTitle>
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
