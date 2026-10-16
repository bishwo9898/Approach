import { Card, CardContent } from "@/components/ui/card";

/**
 * Shared between the session report and the period summary.
 *
 * Extracted rather than copied because the rule they both follow is easy to
 * break in one place and not the other: **a number that cannot be rendered
 * shows as an em dash, never as zero.** "No measurement" and "a measurement of
 * zero" are different claims, and an athlete who did not bat did not hit 0 mph.
 */
export function value(n: number | null | undefined, digits = 1): string {
  return n === null || n === undefined ? "—" : n.toFixed(digits);
}

export function percent(n: number | null | undefined): string {
  return n === null || n === undefined ? "—" : `${n.toFixed(0)}%`;
}

export function Tile({
  label,
  figure,
  unit,
  sub,
  trend,
}: {
  label: string;
  figure: string;
  unit?: string;
  sub: string;
  /** Optional change against a previous window, already formatted. */
  trend?: React.ReactNode;
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
        {/* What the number is, then how it moved. The other order reads as
            though the comparison belongs to the figure above it. */}
        <p className="mt-2 text-[11px] text-muted-foreground">{sub}</p>
        {trend ? <div className="mt-1">{trend}</div> : null}
      </CardContent>
    </Card>
  );
}

export function Section({
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
