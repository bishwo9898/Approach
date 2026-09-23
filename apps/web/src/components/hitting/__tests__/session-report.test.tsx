import { render, screen, within } from "@testing-library/react";
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
  taken: 32,
  swings: 34,
  whiffs: 13,
  whiff_rate: 38.2,
  swing_rate: 51.5,
  batted_balls: 16,
  best_exit_velocity_mph: 87.8,
  average_exit_velocity_mph: 73.0,
  average_launch_angle_deg: 12.0,
  sweet_spot_count: 10,
  sweet_spot_rate: 62.5,
  groups: [
    {
      group: "FASTBALL",
      label: "Fastballs",
      seen: 40,
      swings: 22,
      whiffs: 8,
      whiff_rate: 36.4,
      batted_balls: 9,
      average_pitch_velocity_mph: 78.4,
      average_exit_velocity_mph: 70.9,
      best_exit_velocity_mph: 87.8,
      enough_to_judge: true,
    },
    {
      group: "OFFSPEED",
      label: "Breaking / offspeed",
      seen: 19,
      swings: 7,
      whiffs: 3,
      whiff_rate: 42.9,
      batted_balls: 4,
      average_pitch_velocity_mph: 69.7,
      average_exit_velocity_mph: 78.4,
      best_exit_velocity_mph: 87.3,
      enough_to_judge: false,
    },
  ],
  contact: [
    {
      event_number: 1,
      exit_velocity_mph: 87.8,
      launch_angle_deg: 10.4,
      in_sweet_spot: true,
    },
    {
      event_number: 13,
      exit_velocity_mph: 43.2,
      launch_angle_deg: 40.4,
      in_sweet_spot: false,
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
      headline: "13 of your 34 swings missed (38%)",
      detail: "Contact first.",
    },
  ],
  videos: [],
};

describe("HittingSessionReport", () => {
  it("leads with the session and who it was against", () => {
    render(<HittingSessionReport report={base} />);

    expect(screen.getByText(/Live at-bats · vs Pete Nolan/)).toBeInTheDocument();
    expect(screen.getByText(/66 pitches faced/)).toBeInTheDocument();
  });

  it("shows measurements with their units", () => {
    render(<HittingSessionReport report={base} />);

    const units = screen.getAllByText("mph");
    expect(units.length).toBeGreaterThan(0);
    expect(screen.getByText("87.8")).toBeInTheDocument();
  });

  it("keeps the sample size attached to every rate", () => {
    render(<HittingSessionReport report={base} />);

    expect(screen.getByText("10 of 16 balls, 8°–32°")).toBeInTheDocument();
    expect(screen.getByText("13 of 34 swings")).toBeInTheDocument();
    expect(screen.getByText("across 16 batted balls")).toBeInTheDocument();
  });

  it("marks a pitch group that cannot be judged", () => {
    render(<HittingSessionReport report={base} />);

    const row = screen.getByText("Breaking / offspeed").closest("tr");
    expect(row).not.toBeNull();
    expect(within(row as HTMLElement).getByText("too few to judge")).toBeInTheDocument();
  });

  it("puts strengths before the caveats", () => {
    render(<HittingSessionReport report={base} />);

    const labels = screen
      .getAllByText(/^(Strength|Work on|Keep in mind)$/)
      .map((n) => n.textContent);
    expect(labels).toEqual(["Strength", "Work on", "Keep in mind"]);
  });

  it("says the pitch grouping is derived, not reported", () => {
    render(<HittingSessionReport report={base} />);

    expect(
      screen.getByText(
        /did not label pitch types.*grouped by measured vertical movement/i,
      ),
    ).toBeInTheDocument();
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

    expect(screen.getByText("No video for this session yet")).toBeInTheDocument();
  });

  it("lists attached video with the pitch it belongs to", () => {
    render(
      <HittingSessionReport
        report={{
          ...base,
          videos: [
            {
              id: "v1",
              title: "Hardest ball",
              url: "https://example.com/clip.mp4",
              external_event_id: "1",
              note: null,
            },
          ],
        }}
      />,
    );

    const link = screen.getByRole("link", { name: "Hardest ball" });
    expect(link).toHaveAttribute("href", "https://example.com/clip.mp4");
    // Opened in a new tab, without handing the target window a reference back.
    expect(link).toHaveAttribute("rel", expect.stringContaining("noopener"));
    expect(screen.getByText("Pitch #1")).toBeInTheDocument();
  });
});
