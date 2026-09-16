import { cva, type VariantProps } from "class-variance-authority";
import type { HTMLAttributes } from "react";

import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.04em]",
  {
    variants: {
      variant: {
        default: "border-border bg-muted text-muted-foreground",
        outline: "border-border text-foreground",
        positive: "border-transparent bg-positive/10 text-positive",
        negative: "border-transparent bg-negative/10 text-negative",
        warning: "border-transparent bg-warning/10 text-warning",
        record: "border-transparent bg-primary text-primary-foreground",
      },
    },
    defaultVariants: { variant: "default" },
  },
);

export type BadgeProps = HTMLAttributes<HTMLSpanElement> &
  VariantProps<typeof badgeVariants>;

export function Badge({ className, variant, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />;
}
