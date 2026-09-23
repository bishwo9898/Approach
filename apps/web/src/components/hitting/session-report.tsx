"use client";

import { ContactChart } from "@/components/hitting/contact-chart";
import { InsightList } from "@/components/hitting/insight-list";
import { Card, CardContent } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { formatDate } from "@/lib/format";
import type { HittingReport } from "@/lib/types";

/** A number that cannot be rendered is shown as an em dash, never as zero. */
function value(n: number | null | undefined, digits = 1): string {
  return n === null || n === undefined ? "—" : n.toFixed(digits);
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
  sub?: string;
}) {
  return (
    <Card>
      <CardContent className="p-4">
        <p className="text-xs font-medium text-muted-foreground">{label}</p>
        <p className="tabular mt-1 text-2xl font-semibold tracking-tight">
          {figure}
          {unit ? (
            <span className="ml-1 text-sm font-normal text-muted-foreground">{unit}</span>
          ) : null}
        </p>
        {sub ? <p className="mt-0.5 text-[11px] text-muted-foreground">{sub}</p> : null}
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
        {hint ? <p className="text-xs text-muted-foreground">{hint}</p> : null}
      </div>
      {children}
    </section>
  );
}

/**
 * One hitting session, as the athlete and their coach both see it.
 *
 * Deliberately short. Everything on this page comes from four measurements the
 * export actually carries -- the pitch, whether they swung, whether they hit
 * it, and how hard and at what angle. Nothing is padded out with numbers that
 * would only look like analysis.
 */
export function HittingSessionReport({ report }: { report: HittingReport }) {
  const contactPct =
    report.sweet_spot_rate === null || report.sweet_spot_rate === undefined
      ? "—"
      : `${report.sweet_spot_rate.toFixed(0)}%`;

  return (
    <div className="space-y-8">
      <header>
        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
          {report.session_type === "LIVE_AT_BAT" ? "Live at-bats" : report.session_type}
          {report.opponent_name ? ` · vs ${report.opponent_name}` : ""}
        </p>
        {/* The page that embeds this owns the h1, so the session date is a
            level below it -- one h1 per page. */}
        <h2 className="mt-1 text-2xl font-semibold tracking-tight">
          {formatDate(report.session_date)}
        </h2>
        <p className="mt-1 text-sm text-muted-foreground">
          {report.pitches_faced} pitches faced · {report.swings} swings ·{" "}
          {report.batted_balls} balls measured off the bat
        </p>
      </header>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Tile
          label="Hardest ball"
          figure={value(report.best_exit_velocity_mph)}
          unit="mph"
          sub="your ceiling this session"
        />
        <Tile
          label="Typical ball"
          figure={value(report.average_exit_velocity_mph)}
          unit="mph"
          sub={`across ${report.batted_balls} batted balls`}
        />
        <Tile
          label="Line-drive window"
          figure={contactPct}
          sub={`${report.sweet_spot_count} of ${report.batted_balls} balls, 8°–32°`}
        />
        <Tile
          label="Swings that missed"
          figure={
            report.whiff_rate === null || report.whiff_rate === undefined
              ? "—"
              : `${report.whiff_rate.toFixed(0)}%`
          }
          sub={`${report.whiffs} of ${report.swings} swings`}
        />
      </div>

      <Section title="What this session says">
        <InsightList insights={report.insights} />
      </Section>

      {report.contact.length > 0 ? (
        <Section
          title="Every ball you put in play"
          hint="Hardest first. The window is where line drives live."
        >
          <Card>
            <CardContent className="space-y-6 p-5">
              <ContactChart contact={report.contact} />
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border text-left text-xs text-muted-foreground">
                      <th className="py-2 pr-4 font-medium">Pitch</th>
                      <th className="py-2 pr-4 text-right font-medium">Exit velo</th>
                      <th className="py-2 pr-4 text-right font-medium">Launch angle</th>
                      <th className="py-2 font-medium">In the window</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {report.contact.map((ball, index) => (
                      <tr key={index}>
                        <td className="py-2 pr-4 text-muted-foreground">
                          #{ball.event_number ?? "—"}
                        </td>
                        <td className="tabular py-2 pr-4 text-right font-semibold">
                          {value(ball.exit_velocity_mph)} mph
                        </td>
                        <td className="tabular py-2 pr-4 text-right">
                          {value(ball.launch_angle_deg)}°
                        </td>
                        <td className="py-2">
                          {ball.in_sweet_spot ? (
                            <span className="text-positive">yes</span>
                          ) : (
                            <span className="text-muted-foreground">no</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
        </Section>
      ) : null}

      <Section
        title="How you handled each pitch"
        hint="TrackMan did not label pitch types in this export, so these are grouped by measured vertical movement."
      >
        <Card>
          <CardContent className="overflow-x-auto p-5">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left text-xs text-muted-foreground">
                  <th className="py-2 pr-4 font-medium">Pitch</th>
                  <th className="py-2 pr-4 text-right font-medium">Seen</th>
                  <th className="py-2 pr-4 text-right font-medium">Avg speed</th>
                  <th className="py-2 pr-4 text-right font-medium">Swings</th>
                  <th className="py-2 pr-4 text-right font-medium">Missed</th>
                  <th className="py-2 pr-4 text-right font-medium">In play</th>
                  <th className="py-2 text-right font-medium">Avg exit velo</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {report.groups.map((group) => (
                  <tr key={group.group}>
                    <td className="py-2.5 pr-4 font-medium">
                      {group.label}
                      {!group.enough_to_judge ? (
                        <span
                          className="ml-2 rounded-full bg-muted px-2 py-0.5 text-[10px] text-muted-foreground"
                          title="Too few swings to read anything into these numbers."
                        >
                          too few to judge
                        </span>
                      ) : null}
                    </td>
                    <td className="tabular py-2.5 pr-4 text-right">{group.seen}</td>
                    <td className="tabular py-2.5 pr-4 text-right">
                      {value(group.average_pitch_velocity_mph)}
                    </td>
                    <td className="tabular py-2.5 pr-4 text-right">{group.swings}</td>
                    <td className="tabular py-2.5 pr-4 text-right">
                      {group.whiffs}
                      {group.whiff_rate !== null && group.whiff_rate !== undefined ? (
                        <span className="ml-1 text-xs text-muted-foreground">
                          ({group.whiff_rate.toFixed(0)}%)
                        </span>
                      ) : null}
                    </td>
                    <td className="tabular py-2.5 pr-4 text-right">
                      {group.batted_balls}
                    </td>
                    <td className="tabular py-2.5 text-right">
                      {value(group.average_exit_velocity_mph)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>
      </Section>

      <Section title="Video">
        {report.videos.length === 0 ? (
          <EmptyState
            title="No video for this session yet"
            description="When your coach attaches footage of a swing it appears here, next to the ball it belongs to."
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
