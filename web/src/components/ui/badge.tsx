import { cva, type VariantProps } from "class-variance-authority";
import type { HTMLAttributes } from "react";
import { cn } from "@/lib/utils";

const badgeVariants = cva("inline-flex items-center rounded px-2 py-0.5 text-xs font-semibold", {
  variants: {
    tone: {
      neutral: "bg-zinc-100 text-zinc-800",
      info: "bg-blue-100 text-blue-900",
      warning: "bg-amber-100 text-amber-900",
      danger: "bg-red-100 text-red-900",
      success: "bg-green-100 text-green-900",
    },
  },
  defaultVariants: { tone: "neutral" },
});

export interface BadgeProps
  extends HTMLAttributes<HTMLSpanElement>, VariantProps<typeof badgeVariants> {}

export function Badge({ className, tone, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ tone }), className)} {...props} />;
}
