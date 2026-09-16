import { Card, CardContent } from "@/components/ui/card";
import { Icon, type IconName } from "@/components/ui/icons";
import { cn } from "@/lib/utils";

/** A single headline count on the coach dashboard. */
export function StatTile({
  label,
  value,
  hint,
  icon = "activity",
  tone = "blue",
}: {
  label: string;
  value: string | number;
  hint?: string;
  icon?: IconName;
  tone?: "blue" | "green" | "amber" | "violet";
}) {
  const toneClass = {
    blue: "bg-blue-50 text-blue-600 ring-blue-100",
    green: "bg-emerald-50 text-emerald-600 ring-emerald-100",
    amber: "bg-amber-50 text-amber-600 ring-amber-100",
    violet: "bg-violet-50 text-violet-600 ring-violet-100",
  }[tone];

  return (
    <Card className="overflow-hidden">
      <CardContent className="relative p-5">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-xs font-medium text-muted-foreground">{label}</p>
            <p className="tabular mt-2 text-[28px] font-semibold leading-none tracking-[-0.035em]">
              {value}
            </p>
          </div>
          <span
            className={cn("grid size-10 place-items-center rounded-xl ring-1", toneClass)}
          >
            <Icon name={icon} className="size-[18px]" />
          </span>
        </div>
        {hint ? (
          <p className="mt-3 text-[11px] leading-relaxed text-muted-foreground">{hint}</p>
        ) : null}
      </CardContent>
    </Card>
  );
}
