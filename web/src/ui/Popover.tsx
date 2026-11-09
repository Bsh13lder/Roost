import * as RadixPopover from "@radix-ui/react-popover";
import type { ReactElement, ReactNode } from "react";
import { usePortalContainer } from "./portalContainer";

export interface PopoverProps {
  trigger?: ReactElement; // one element that opens it, such as an IconButton
  anchor?: ReactElement; // or one element it opens beside with no button of its own (a calendar day), opened from `open`
  label: string; // the panel's accessible name
  children: ReactNode;
  open?: boolean; // controlled when given, with onOpenChange
  onOpenChange?: (open: boolean) => void;
  side?: "top" | "bottom";
  align?: "start" | "center" | "end";
}

// A small panel beside its button (redesign P1, Radix Popover): Escape and a click outside close it,
// and focus goes back to the button. With an `anchor` and no trigger the panel sits beside that element and its
// owner opens it through `open`/`onOpenChange` (a day cell, a "+N more", a drop).
export function Popover({ trigger, anchor, label, children, open, onOpenChange, side = "bottom", align = "end" }: PopoverProps) {
  const container = usePortalContainer();
  return (
    <RadixPopover.Root open={open} onOpenChange={onOpenChange}>
      {trigger ? <RadixPopover.Trigger asChild>{trigger}</RadixPopover.Trigger> : null}
      {anchor ? <RadixPopover.Anchor asChild>{anchor}</RadixPopover.Anchor> : null}
      <RadixPopover.Portal container={container}>
        <RadixPopover.Content className="popover" aria-label={label} side={side} align={align} sideOffset={6}>
          {children}
        </RadixPopover.Content>
      </RadixPopover.Portal>
    </RadixPopover.Root>
  );
}
