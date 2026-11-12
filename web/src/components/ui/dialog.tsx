"use client";

import { Dialog as Primitive } from "radix-ui";
import type { ReactNode } from "react";

export const Dialog = Primitive.Root;
export const DialogTrigger = Primitive.Trigger;
export const DialogClose = Primitive.Close;

export function DialogContent({
  title,
  description,
  children,
}: {
  title: string;
  description?: string;
  children: ReactNode;
}) {
  return (
    <Primitive.Portal>
      <Primitive.Overlay className="fixed inset-0 bg-black/40" />
      <Primitive.Content className="fixed top-1/2 left-1/2 w-[min(32rem,92vw)] -translate-x-1/2 -translate-y-1/2 rounded-lg bg-white p-6 shadow-xl focus-visible:outline-2">
        <Primitive.Title className="text-lg font-semibold">{title}</Primitive.Title>
        {description ? (
          <Primitive.Description className="text-muted-foreground mt-1 text-sm">
            {description}
          </Primitive.Description>
        ) : null}
        <div className="mt-4">{children}</div>
      </Primitive.Content>
    </Primitive.Portal>
  );
}
