import { Section, Tile, percent, value } from "@/components/hitting/primitives";
import { TrendChart } from "@/components/hitting/trend-chart";
import { Card, CardContent } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { formatDate } from "@/lib/format";
import type { HittingPeriodSummary, PeriodComparison } from "@/lib/types";

/**
 * How an athlete has hit over a window of time.
 *
 * The companion to the single-session report, and built from the same numbers:
 * the server runs the identical report over every pitch in the window, so
 * "hardest ball" means one thing in both views.
 *
 * Most of this component is about saying how much is behind the numbers. A
 * facility that has just started collecting has windows with one session in
 * them, or none, and that is the normal case rather than an error state.
 */

/** A change against the preceding, equally long window. */
function Change({ comparison, unit }: { comparison: PeriodComparison; unit: string }) {
  if (comparison.delta === null || comparison.previous === null) {
    // A first window has not improved by zero -- it has nothing to compare to.
    return (
      <p className="text-[11px] text-muted-foreground">No earlier period to compare</p>
    );
  }

  const up = comparison.delta > 0;
  const flat = comparison.delta === 0;
  return (
    <p
      className={
        flat
          ? "text-[11px] text-muted-foreground"
          : up
            ? "text-[11px] text-positive"
            : "text-[11px] text-negative"
      }
    >
      {flat ? "No change" : `${up ? "+" : ""}${comparison.delta.toFixed(1)} ${unit}`}
      <span className="text-muted-foreground">
        {" "}
        vs previous ({comparison.previous_sample} ball
        {comparison.previous_sample === 1 ? "" : "s"})
      </span>
    </p>
  );
}

export function HittingPeriodView({ summary }: { summary: HittingPeriodSummary }) {
  const span =
    summary.first_session && summary.last_session
      ? summary.first_session === summary.last_session
        ? formatDate(summary.first_session)
        : `${formatDate(summary.first_session)} – ${formatDate(summary.last_session)}`
      : `${formatDate(summary.start)} – ${formatDate(summary.end)}`;

  if (!summary.has_data) {
    return (
      <div className="space-y-6">
        <p className="text-sm text-muted-foreground">
          {formatDate(summary.start)} – {formatDate(summary.end)}
        </p>
        <EmptyState
          title="Nothing to show yet"
          description="No session was recorded in this period. Try a longer one, or import a TrackMan export for these dates."
        />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <p className="text-sm font-medium">
          {summary.sessions} session{summary.sessions === 1 ? "" : "s"}
        </p>
        <p className="text-xs text-muted-foreground">
          {span} · {summary.batted_balls} batted ball
          {summary.batted_balls === 1 ? "" : "s"} measured
        </p>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Tile
          label="Hardest ball"
          figure={value(summary.best_exit_velocity_mph)}
          unit="mph"
          sub="best of the period"
          trend={<Change comparison={summary.best_exit_velocity_change} unit="mph" />}
        />
        <Tile
          label="Typical ball"
          figure={value(summary.average_exit_velocity_mph)}
          unit="mph"
          sub={`across ${summary.batted_balls} batted balls`}
          trend={<Change comparison={summary.average_exit_velocity_change} unit="mph" />}
        />
        <Tile
          label="Line-drive window"
          figure={percent(summary.sweet_spot_rate)}
          sub={`${summary.sweet_spot_count} of ${summary.batted_balls} balls, 8°–32°`}
        />
        <Tile
          label="Average launch angle"
          figure={value(summary.average_launch_angle_deg, 0)}
          unit="°"
          sub={`across ${summary.batted_balls} batted balls`}
        />
      </div>

      <Section
        title="Over time"
        hint={summary.has_trend ? `Exit velocity ${summary.grain_label}.` : undefined}
      >
        {summary.has_trend ? (
          <Card>
            <CardContent className="p-5">
              <TrendChart buckets={summary.buckets} grainLabel={summary.grain_label} />
            </CardContent>
          </Card>
        ) : (
          // One point is not a line, however many sessions produced it.
          // Drawing through it would imply a direction nobody has evidence for.
          <EmptyState
            title="Not enough for a trend yet"
            description={
              summary.sessions === 1
                ? `One session in this period. A second one in a different ${summary.grain} is enough to start showing movement — this fills in on its own as sessions are imported.`
                : `All ${summary.sessions} sessions in this period fall in the same ${summary.grain}, so there is one point rather than a line. A session in another ${summary.grain} starts the trend.`
            }
          />
        )}
      </Section>
    </div>
  );
}
