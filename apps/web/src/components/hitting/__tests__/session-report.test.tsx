import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { HittingSessionReport } from "@/components/hitting/session-report";
import type { HittingReport } from "@/lib/types";

const base: HittingReport = {
  player: {
    id: "p1",
    display_name: "Mateo Rivera",
    full_name: "Mateo Rivera",
    first_name: "Mateo",
    last_name: "Rivera",
    preferred_name: null,
    position: "OF",
    graduation_year: null,
    bats: "R",
    throws: "R",
    active: true,
  },
  session_id: "s1",
  session_date: "2026-09-22",
  session_type: "LIVE_AT_BAT",
  opponent_name: "Pete Nolan",
  pitches_faced: 66,
  batted_balls: 16,
  measured_rate: 24.2,
  best_exit_velocity_mph: 87.8,
  average_exit_velocity_mph: 73.0,
  average_launch_angle_deg: 12.0,
  hardest_ball_launch_angle_deg: 10.4,
  sweet_spot_count: 10,
  sweet_spot_rate: 62.5,
  average_pitch_velocity_mph: 72.1,
  contact: [
    {
      event_number: 1,
      exit_velocity_mph: 87.8,
      launch_angle_deg: 10.4,
      in_sweet_spot: true,
      pitch_velocity_mph: 78.2,
    },
    {
      event_number: 13,
      exit_velocity_mph: 43.2,
      launch_angle_deg: 40.4,
      in_sweet_spot: false,
      pitch_velocity_mph: 74.5,
    },
  ],
  insights: [
    { kind: "NOTE", headline: "This is one session", detail: "A single day." },
    {
      kind: "STRENGTH",
      headline: "Your hardest ball left the bat at 87.8 mph",
      detail: "Ceiling.",
    },
    {
      kind: "WORK_ON",
      headline: "10 of 16 measured balls were in the line-drive window",
      detail: "Contact first.",
    },
  ],
  videos: [],
};

describe("HittingSessionReport", () => {
  it("leads with the session and who it was against", () => {
    render(<HittingSessionReport report={base} />);

    expect(screen.getByText(/Live at-bats · vs Pete Nolan/)).toBeInTheDocument();
    expect(
      screen.getByText(/66 pitches recorded · 16 with a measured batted ball/),
    ).toBeInTheDocument();
  });

  it("shows measurements with their units", () => {
    render(<HittingSessionReport report={base} />);

    const units = screen.getAllByText("mph");
    expect(units.length).toBeGreaterThan(0);
    expect(screen.getByText("87.8")).toBeInTheDocument();
  });

  it("keeps the sample size attached to every rate", () => {
    render(<HittingSessionReport report={base} />);

    // Rates are denominated in measured balls, and say so.
    expect(screen.getByText("10 of 16 balls, 8°–32°")).toBeInTheDocument();
    expect(screen.getAllByText("across 16 batted balls")).toHaveLength(2);
  });

  it("puts strengths before the caveats", () => {
    render(<HittingSessionReport report={base} />);

    const labels = screen
      .getAllByText(/^(Strength|Work on|Keep in mind)$/)
      .map((n) => n.textContent);
    expect(labels).toEqual(["Strength", "Work on", "Keep in mind"]);
  });

  it("never uses injury or risk language", () => {
    const { container } = render(<HittingSessionReport report={base} />);

    const text = (container.textContent ?? "").toLowerCase();
    for (const word of ["injur", "risk", "fatigue", "medical"]) {
      expect(text).not.toContain(word);
    }
  });

  it("shows an em dash rather than zero when a measurement is missing", () => {
    render(
      <HittingSessionReport
        report={{
          ...base,
          batted_balls: 0,
          best_exit_velocity_mph: null,
          average_exit_velocity_mph: null,
          sweet_spot_count: 0,
          sweet_spot_rate: null,
          contact: [],
        }}
      />,
    );

    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
  });

  it("invites video rather than pretending there is none to have", () => {
    render(<HittingSessionReport report={base} />);

    expect(screen.getByText("No video yet")).toBeInTheDocument();
  });

  it("plays attached video in place, next to the pitch it belongs to", () => {
    render(
      <HittingSessionReport
        report={{
          ...base,
          videos: [
            {
              id: "v1",
              title: "Swing on pitch 1",
              url: "https://example.com/clip.mp4",
              external_event_id: "1",
              note: null,
            },
          ],
        }}
      />,
    );

    // Played in place rather than linked out: the URL is minted per request
    // and can expire, so it is not something to hand to another tab.
    expect(screen.getByText("Swing on pitch 1")).toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: "Swing on pitch 1" }),
    ).not.toBeInTheDocument();
    const player = document.querySelector("video");
    expect(player).toHaveAttribute("src", "https://example.com/clip.mp4");
    expect(screen.getByText("Pitch #1")).toBeInTheDocument();
  });
});
