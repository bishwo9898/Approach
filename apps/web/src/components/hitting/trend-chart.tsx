import type { TrendBucket } from "@/lib/types";

/**
 * Exit velocity across the buckets of a period.
 *
 * Three deliberate choices, all of them about not overstating what is known:
 *
 * **A line, not bars.** Exit velocities live between about 60 and 105 mph, so a
 * bar chart would either waste its whole height on an empty 0–60 range or use a
 * cropped baseline, which makes a 2 mph difference look like a doubling. A line
 * carries no baseline claim.
 *
 * **Gaps break the line.** A bucket with no session is not a zero and not a
 * straight interpolation between its neighbours. The line stops and restarts,
 * and the empty bucket keeps its label, so an athlete who trained twice in a
 * month does not read as one who trained steadily.
 *
 * **Each point carries its sample size** in its tooltip. A best exit velocity
 * off one batted ball and off forty are not the same number.
 */

const WIDTH = 720;
const HEIGHT = 200;
const PAD = { top: 16, right: 12, bottom: 28, left: 34 };

type Point = {
  x: number;
  best: number | null;
  average: number | null;
  bucket: TrendBucket;
};

function scaleY(value: number, min: number, max: number): number {
  const span = max - min || 1;
  return PAD.top + (1 - (value - min) / span) * (HEIGHT - PAD.top - PAD.bottom);
}

/** Connected runs of non-empty points, so a gap genuinely breaks the line. */
function runs(points: Point[], key: "best" | "average"): Point[][] {
  const out: Point[][] = [];
  let current: Point[] = [];
  for (const point of points) {
    if (point[key] === null) {
      if (current.length) out.push(current);
      current = [];
    } else {
      current.push(point);
    }
  }
  if (current.length) out.push(current);
  return out;
}

export function TrendChart({
  buckets,
  grainLabel,
}: {
  buckets: TrendBucket[];
  grainLabel: string;
}) {
  const measured = buckets.flatMap((b) =>
    [b.best_exit_velocity_mph, b.average_exit_velocity_mph].filter(
      (v): v is number => v !== null,
    ),
  );
  if (measured.length === 0) return null;

  // Padded by a few mph so a point never sits on the frame, and widened when
  // every value is nearly identical so a flat period reads as flat rather than
  // as noise amplified to fill the height.
  const low = Math.min(...measured);
  const high = Math.max(...measured);
  const pad = Math.max(3, (high - low) * 0.15);
  const min = low - pad;
  const max = high + pad;

  const innerWidth = WIDTH - PAD.left - PAD.right;
  const step = buckets.length > 1 ? innerWidth / (buckets.length - 1) : 0;
  const points: Point[] = buckets.map((bucket, index) => ({
    x: PAD.left + (buckets.length > 1 ? index * step : innerWidth / 2),
    best: bucket.best_exit_velocity_mph,
    average: bucket.average_exit_velocity_mph,
    bucket,
  }));

  // At most a handful of x labels, so a 90-day window does not overprint.
  const labelEvery = Math.ceil(buckets.length / 6);

  const path = (run: Point[], key: "best" | "average") =>
    run
      .map(
        (p, i) => `${i === 0 ? "M" : "L"} ${p.x} ${scaleY(p[key] as number, min, max)}`,
      )
      .join(" ");

  return (
    <figure className="space-y-2">
      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        className="w-full"
        role="img"
        aria-label={`Exit velocity ${grainLabel}`}
      >
        {[max, (max + min) / 2, min].map((tick) => (
          <g key={tick}>
            <line
              x1={PAD.left}
              x2={WIDTH - PAD.right}
              y1={scaleY(tick, min, max)}
              y2={scaleY(tick, min, max)}
              className="stroke-border"
              strokeWidth={1}
            />
            <text
              x={PAD.left - 6}
              y={scaleY(tick, min, max) + 3}
              textAnchor="end"
              className="fill-muted-foreground text-[9px]"
            >
              {tick.toFixed(0)}
            </text>
          </g>
        ))}

        {runs(points, "average").map((run, index) => (
          <path
            key={`avg-${index}`}
            d={path(run, "average")}
            fill="none"
            className="stroke-primary"
            strokeWidth={2}
            strokeLinecap="round"
          />
        ))}
        {runs(points, "best").map((run, index) => (
          <path
            key={`best-${index}`}
            d={path(run, "best")}
            fill="none"
            className="stroke-primary/35"
            strokeWidth={2}
            strokeDasharray="4 4"
            strokeLinecap="round"
          />
        ))}

        {points.map((point) => (
          <g key={point.bucket.start}>
            {point.average !== null ? (
              <circle
                cx={point.x}
                cy={scaleY(point.average, min, max)}
                r={3.5}
                className="fill-primary"
              >
                <title>
                  {`${point.bucket.label}: ${point.average.toFixed(1)} mph average, ` +
                    `best ${point.best?.toFixed(1) ?? "—"} — ` +
                    `${point.bucket.batted_balls} batted ball${
                      point.bucket.batted_balls === 1 ? "" : "s"
                    } in ${point.bucket.sessions} session${
                      point.bucket.sessions === 1 ? "" : "s"
                    }`}
                </title>
              </circle>
            ) : (
              // An empty bucket is marked on the axis, not on the line.
              <circle
                cx={point.x}
                cy={HEIGHT - PAD.bottom}
                r={1.5}
                className="fill-muted-foreground/40"
              >
                <title>{`${point.bucket.label}: no session`}</title>
              </circle>
            )}
          </g>
        ))}

        {points.map((point, index) =>
          index % labelEvery === 0 || index === points.length - 1 ? (
            <text
              key={`label-${point.bucket.start}`}
              x={point.x}
              y={HEIGHT - 8}
              textAnchor="middle"
              className="fill-muted-foreground text-[9px]"
            >
              {point.bucket.label}
            </text>
          ) : null,
        )}
      </svg>

      <figcaption className="flex flex-wrap items-center gap-4 text-[11px] text-muted-foreground">
        <span className="flex items-center gap-1.5">
          <span className="h-0.5 w-4 rounded bg-primary" />
          Typical ball
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-0.5 w-4 rounded bg-primary/35" />
          Hardest ball
        </span>
        <span>
          Exit velocity in mph, {grainLabel}. A break in the line is a period with no
          session.
        </span>
      </figcaption>
    </figure>
  );
}
