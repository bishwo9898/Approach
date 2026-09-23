"use client";

import { useState } from "react";

import { ContactChart } from "@/components/hitting/contact-chart";
import { InsightList } from "@/components/hitting/insight-list";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { formatDate } from "@/lib/format";
import type { HittingReport, PitchGroupSplit } from "@/lib/types";

/** A number that cannot be rendered shows as an em dash, never as zero. */
function value(n: number | null | undefined, digits = 1): string {
  return n === null || n === undefined ? "—" : n.toFixed(digits);
}

function percent(n: number | null | undefined): string {
  return n === null || n === undefined ? "—" : `${n.toFixed(0)}%`;
}

function Tile({
  label,
  figure,
  unit,
  sub,
}: {
  label: string;
  figure: string;
  unit?: string;
  sub: string;
}) {
  return (
    <Card>
      <CardContent className="p-5">
        <p className="text-xs font-medium text-muted-foreground">{label}</p>
        <p className="tabular mt-2 text-[28px] font-semibold leading-none tracking-tight">
          {figure}
          {unit ? (
            <span className="ml-1 text-base font-normal text-muted-foreground">
              {unit}
            </span>
          ) : null}
        </p>
        <p className="mt-2 text-[11px] text-muted-foreground">{sub}</p>
      </CardContent>
    </Card>
  );
}

function Section({
  title,
  hint,
  children,
}: {
  title: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="space-y-3">
      <div>
        <h2 className="text-sm font-semibold tracking-tight">{title}</h2>
        {hint ? <p className="mt-0.5 text-xs text-muted-foreground">{hint}</p> : null}
      </div>
      {children}
    </section>
  );
}

/**
 * One pitch type, as a card rather than a table row.
 *
 * Three rows across seven columns is a lot of grid for very little data, and it
 * collapses badly on a phone. The same numbers read faster grouped.
 */
function PitchGroupCard({ group }: { group: PitchGroupSplit }) {
  const stats: Array<[string, string]> = [
    ["Swings", String(group.swings)],
    ["Missed", `${group.whiffs} (${percent(group.whiff_rate)})`],
    ["In play", String(group.batted_balls)],
    ["Avg exit", `${value(group.average_exit_velocity_mph)} mph`],
  ];

  return (
    <Card>
      <CardContent className="p-5">
        <div className="flex items-baseline justify-between gap-3">
          <p className="text-sm font-semibold">{group.label}</p>
          <p className="tabular shrink-0 text-xs text-muted-foreground">
            {group.seen} seen · {value(group.average_pitch_velocity_mph)} mph
          </p>
        </div>

        {!group.enough_to_judge ? (
          <p className="mt-2 inline-block rounded-full bg-muted px-2 py-0.5 text-[10px] text-muted-foreground">
            too few to judge
          </p>
        ) : null}

        <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-3">
          {stats.map(([label, figure]) => (
            <div key={label}>
              <dt className="text-[11px] text-muted-foreground">{label}</dt>
              <dd className="tabular mt-0.5 text-sm font-medium">{figure}</dd>
            </div>
          ))}
        </dl>
      </CardContent>
    </Card>
  );
}

const VISIBLE_BALLS = 5;

/**
 * One hitting session, as the athlete and their coach both see it.
 *
 * Everything here comes from four measurements the export actually carries --
 * the pitch, whether they swung, whether they hit it, and how hard and at what
 * angle. Nothing is padded out with numbers that would only look like analysis.
 */
export function HittingSessionReport({ report }: { report: HittingReport }) {
  const [showAllBalls, setShowAllBalls] = useState(false);
  const balls = showAllBalls ? report.contact : report.contact.slice(0, VISIBLE_BALLS);

  return (
    <div className="space-y-10">
      <header>
        <p className="text-xs font-medium text-muted-foreground">
          {report.session_type === "LIVE_AT_BAT" ? "Live at-bats" : report.session_type}
          {report.opponent_name ? ` · vs ${report.opponent_name}` : ""}
        </p>
        <h2 className="mt-1 text-2xl font-semibold tracking-tight">
          {formatDate(report.session_date)}
        </h2>
        <p className="mt-1 text-sm text-muted-foreground">
          {report.pitches_faced} pitches · {report.swings} swings · {report.batted_balls}{" "}
          balls measured
        </p>
      </header>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Tile
          label="Hardest ball"
          figure={value(report.best_exit_velocity_mph)}
          unit="mph"
          sub="best of the session"
        />
        <Tile
          label="Typical ball"
          figure={value(report.average_exit_velocity_mph)}
          unit="mph"
          sub={`across ${report.batted_balls} batted balls`}
        />
        <Tile
          label="Line-drive window"
          figure={percent(report.sweet_spot_rate)}
          sub={`${report.sweet_spot_count} of ${report.batted_balls} balls, 8°–32°`}
        />
        <Tile
          label="Swings missed"
          figure={percent(report.whiff_rate)}
          sub={`${report.whiffs} of ${report.swings} swings`}
        />
      </div>

      <Section title="What this session says">
        <InsightList insights={report.insights} />
      </Section>

      {report.contact.length > 0 ? (
        <Section
          title="Every ball you put in play"
          hint="The shaded band is where line drives live."
        >
          <Card>
            <CardContent className="space-y-5 p-5">
              <ContactChart contact={report.contact} />

              <ul className="divide-y divide-border border-t border-border">
                {balls.map((ball, index) => (
                  <li key={index} className="flex items-center gap-3 py-2.5 text-sm">
                    <span className="w-10 shrink-0 text-xs text-muted-foreground">
                      #{ball.event_number ?? "—"}
                    </span>
                    <span className="tabular w-24 shrink-0 font-semibold">
                      {value(ball.exit_velocity_mph)} mph
                    </span>
                    <span className="tabular w-16 shrink-0 text-muted-foreground">
                      {value(ball.launch_angle_deg)}°
                    </span>
                    {ball.in_sweet_spot ? (
                      <span className="text-xs font-medium text-positive">
                        line drive
                      </span>
                    ) : null}
                  </li>
                ))}
              </ul>

              {report.contact.length > VISIBLE_BALLS ? (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setShowAllBalls(!showAllBalls)}
                >
                  {showAllBalls ? "Show fewer" : `Show all ${report.contact.length}`}
                </Button>
              ) : null}
            </CardContent>
          </Card>
        </Section>
      ) : null}

      <Section
        title="How you handled each pitch"
        hint="Grouped by measured movement — this export does not label pitch types."
      >
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {report.groups.map((group) => (
            <PitchGroupCard key={group.group} group={group} />
          ))}
        </div>
      </Section>

      <Section title="Video">
        {report.videos.length === 0 ? (
          <EmptyState
            title="No video yet"
            description="Clips your coach attaches appear here, next to the ball they show."
          />
        ) : (
          <ul className="grid gap-3 sm:grid-cols-2">
            {report.videos.map((video) => (
              <li key={video.id}>
                <Card>
                  <CardContent className="p-4">
                    <a
                      href={video.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-sm font-medium hover:underline"
                    >
                      {video.title}
                    </a>
                    {video.external_event_id ? (
                      <p className="mt-0.5 text-xs text-muted-foreground">
                        Pitch #{video.external_event_id}
                      </p>
                    ) : null}
                    {video.note ? (
                      <p className="mt-2 text-sm text-muted-foreground">{video.note}</p>
                    ) : null}
                  </CardContent>
                </Card>
              </li>
            ))}
          </ul>
        )}
      </Section>
    </div>
  );
}
