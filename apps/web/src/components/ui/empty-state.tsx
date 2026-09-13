import { cn } from "@/lib/utils";

/**
 * Says why there is nothing, not just that there is nothing.
 *
 * "No data" and "a value of zero" are different claims, and the UI must never
 * let a reader confuse them.
 */
export function EmptyState({
  title,
  description,
  className,
}: {
  title: string;
  description?: string;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center gap-1 rounded-md border border-dashed border-border px-4 py-8 text-center",
        className,
      )}
    >
      <p className="text-sm font-medium text-foreground">{title}</p>
      {description ? (
        <p className="max-w-sm text-xs text-muted-foreground">{description}</p>
      ) : null}
    </div>
  );
}
