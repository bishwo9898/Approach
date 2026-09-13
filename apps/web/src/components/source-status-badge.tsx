import { Badge } from "@/components/ui/badge";
import type { SourceStatus } from "@/lib/types";

/**
 * Labels whether a number is provisional.
 *
 * TrackMan can republish a session with corrected values, which can move a
 * metric and even revoke a record. A coach reading a preliminary number needs
 * to know that before they act on it, so this badge appears wherever such a
 * value is shown.
 */
export function SourceStatusBadge({
  status,
  className,
}: {
  status: SourceStatus | null | undefined;
  className?: string;
}) {
  if (!status) return null;
  const verified = status === "VERIFIED";
  return (
    <Badge
      variant={verified ? "positive" : "warning"}
      className={className}
      title={
        verified
          ? "TrackMan has published verified data for this session."
          : "Preliminary TrackMan data. Values may change when the session is verified."
      }
    >
      {verified ? "Verified" : "Preliminary"}
    </Badge>
  );
}
