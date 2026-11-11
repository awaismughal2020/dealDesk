import type { HTMLAttributes, TdHTMLAttributes, ThHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

/** A table in a keyboard-focusable scroll region (wide tables scroll on small screens). */
export function Table({ className, ...props }: HTMLAttributes<HTMLTableElement>) {
  return (
    <div
      className="w-full overflow-x-auto"
      role="region"
      aria-label={
        props["aria-label"] ? `${props["aria-label"]} (scrollable)` : "Table (scrollable)"
      }
      tabIndex={0}
    >
      <table className={cn("w-full border-collapse text-sm", className)} {...props} />
    </div>
  );
}

export function Th({ className, ...props }: ThHTMLAttributes<HTMLTableCellElement>) {
  return (
    <th
      scope="col"
      className={cn("border-border border-b px-3 py-2 text-left font-semibold", className)}
      {...props}
    />
  );
}

export function Td({ className, ...props }: TdHTMLAttributes<HTMLTableCellElement>) {
  return (
    <td className={cn("border-b border-zinc-100 px-3 py-2 align-top", className)} {...props} />
  );
}
