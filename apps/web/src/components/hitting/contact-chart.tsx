"use client";

import type { BattedBall } from "@/lib/types";

const SWEET_MIN = 8;
const SWEET_MAX = 32;

/**
 * Every batted ball plotted as exit velocity against launch angle.
 *
 * The shaded band is the 8-32 degree line-drive window. A hitter can see at a
 * glance whether their weak contact is on the ground or in the air, which is
 * the most actionable thing a batted-ball chart can show -- and far more useful
 * than another row of averages.
 *
 * Plain SVG: sixteen points do not need a charting library.
 */
export function ContactChart({ contact }: { contact: BattedBall[] }) {
  const points = contact.filter((c) => c.launch_angle_deg !== null);
  if (points.length === 0) return null;

  const width = 520;
  const height = 260;
  const pad = { top: 16, right: 16, bottom: 34, left: 44 };

  const angles = points.map((p) => p.launch_angle_deg as number);
  const velocities = points.map((p) => p.exit_velocity_mph);

  const angleMin = Math.min(-25, Math.floor(Math.min(...angles) / 10) * 10);
  const angleMax = Math.max(50, Math.ceil(Math.max(...angles) / 10) * 10);
  const veloMin = Math.floor((Math.min(...velocities) - 5) / 5) * 5;
  const veloMax = Math.ceil((Math.max(...velocities) + 5) / 5) * 5;

  const x = (angle: number) =>
    pad.left +
    ((angle - angleMin) / (angleMax - angleMin)) * (width - pad.left - pad.right);
  const y = (velocity: number) =>
    height -
    pad.bottom -
    ((velocity - veloMin) / (veloMax - veloMin)) * (height - pad.top - pad.bottom);

  const veloTicks = [veloMin, (veloMin + veloMax) / 2, veloMax];
  const angleTicks = [angleMin, 0, SWEET_MIN, SWEET_MAX, angleMax];

  return (
    <figure className="space-y-2">
      <div className="overflow-x-auto">
        <svg
          viewBox={`0 0 ${width} ${height}`}
          className="h-auto w-full min-w-[420px]"
          role="img"
          aria-label={`${points.length} batted balls plotted by launch angle and exit velocity`}
        >
          <rect
            x={x(SWEET_MIN)}
            y={pad.top}
            width={x(SWEET_MAX) - x(SWEET_MIN)}
            height={height - pad.top - pad.bottom}
            className="fill-positive/10"
          />
          <text
            x={(x(SWEET_MIN) + x(SWEET_MAX)) / 2}
            y={pad.top + 12}
            textAnchor="middle"
            className="fill-positive text-[10px] font-medium"
          >
            line-drive window
          </text>

          {veloTicks.map((tick) => (
            <g key={tick}>
              <line
                x1={pad.left}
                x2={width - pad.right}
                y1={y(tick)}
                y2={y(tick)}
                className="stroke-border"
                strokeWidth={1}
              />
              <text
                x={pad.left - 8}
                y={y(tick) + 3}
                textAnchor="end"
                className="fill-muted-foreground text-[10px]"
              >
                {Math.round(tick)}
              </text>
            </g>
          ))}

          {angleTicks.map((tick) => (
            <text
              key={tick}
              x={x(tick)}
              y={height - pad.bottom + 14}
              textAnchor="middle"
              className="fill-muted-foreground text-[10px]"
            >
              {tick}°
            </text>
          ))}

          {points.map((point, index) => (
            <circle
              key={index}
              cx={x(point.launch_angle_deg as number)}
              cy={y(point.exit_velocity_mph)}
              r={5}
              className={
                point.in_sweet_spot
                  ? "fill-positive/80 stroke-positive"
                  : "fill-muted stroke-muted-foreground"
              }
              strokeWidth={1.5}
            >
              <title>
                {`${point.exit_velocity_mph.toFixed(1)} mph at ${(point.launch_angle_deg as number).toFixed(1)}°`}
              </title>
            </circle>
          ))}
        </svg>
      </div>
      <figcaption className="text-[11px] text-muted-foreground">
        Exit velocity (mph, vertical) against launch angle (horizontal). {points.length}{" "}
        batted balls. Filled points landed in the line-drive window.
      </figcaption>
    </figure>
  );
}
