"use client";

import { useState } from "react";

import { ContactChart } from "@/components/hitting/contact-chart";
import { InsightList } from "@/components/hitting/insight-list";
import { Section, Tile, percent, value } from "@/components/hitting/primitives";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { formatDate } from "@/lib/format";
import type { HittingReport } from "@/lib/types";

/** The list opens showing the hardest few, with the rest behind a toggle. */
const VISIBLE_BALLS = 5;

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
          {report.pitches_faced} pitches recorded · {report.batted_balls} with a measured
          batted ball
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
          label="Average launch angle"
          figure={value(report.average_launch_angle_deg, 0)}
          unit="°"
          sub={`across ${report.batted_balls} batted balls`}
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
                  <CardContent className="space-y-2 p-3">
                    {/* Played in place rather than linked out. The URL is minted
                        per request and can expire, so it is not something to
                        hand to another tab. */}
                    <video
                      src={video.url}
                      poster={video.thumbnail_url ?? undefined}
                      controls
                      preload="metadata"
                      className="aspect-video w-full rounded-md bg-black"
                    />
                    <p className="text-sm font-medium">{video.title}</p>
                    {video.external_event_id ? (
                      <p className="text-xs text-muted-foreground">
                        Pitch #{video.external_event_id}
                      </p>
                    ) : null}
                    {video.note ? (
                      <p className="text-sm text-muted-foreground">{video.note}</p>
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
