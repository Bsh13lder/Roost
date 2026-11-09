import * as RadixTooltip from "@radix-ui/react-tooltip";
import type { ReactElement, ReactNode } from "react";
import { TOOLTIP_DELAY_MS } from "./constants";

export interface TooltipProps {
  content: ReactNode;
  children: ReactElement; // the element it explains; it keeps its own accessible name
  side?: "top" | "bottom" | "left" | "right";
}

// A short hint on hover or keyboard focus (redesign P1, Radix Tooltip). Each tooltip brings its own
// provider, so nothing has to wrap the app.
export function Tooltip({ content, children, side = "top" }: TooltipProps) {
  return (
    <RadixTooltip.Provider delayDuration={TOOLTIP_DELAY_MS}>
      <RadixTooltip.Root>
        <RadixTooltip.Trigger asChild>{children}</RadixTooltip.Trigger>
        <RadixTooltip.Portal>
          <RadixTooltip.Content className="tooltip" side={side} sideOffset={6}>{content}</RadixTooltip.Content>
        </RadixTooltip.Portal>
      </RadixTooltip.Root>
    </RadixTooltip.Provider>
  );
}
