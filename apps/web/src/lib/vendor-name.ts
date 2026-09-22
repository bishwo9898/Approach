/**
 * Split a vendor-supplied display name into first and last.
 *
 * This produces a *suggestion* for a human to confirm, and nothing more. It
 * never establishes identity and is never used to match an athlete -- the only
 * thing that maps a TrackMan id to a player is a person choosing one.
 *
 * Handles the two shapes seen in practice: "Jones, Ryan" and "Ryan Jones".
 */
export function splitVendorName(raw: string | null | undefined): {
  firstName: string;
  lastName: string;
} {
  const name = (raw ?? "").trim();
  if (!name) return { firstName: "", lastName: "" };

  if (name.includes(",")) {
    const [last = "", first = ""] = name.split(",", 2);
    return { firstName: first.trim(), lastName: last.trim() };
  }

  const parts = name.split(/\s+/);
  if (parts.length === 1) return { firstName: "", lastName: parts[0] ?? "" };

  // Everything after the first token is the surname, so "Juan de la Cruz"
  // keeps its surname intact rather than losing two thirds of it.
  return { firstName: parts[0] ?? "", lastName: parts.slice(1).join(" ") };
}
