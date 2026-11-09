import * as RadixDialog from "@radix-ui/react-dialog";
import { useRef, useState, type ReactNode } from "react";
import { CloseIcon } from "../components/icons";
import { cx } from "./cx";
import { IconButton } from "./IconButton";
import { PortalContainer } from "./portalContainer";

export interface SheetProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: string; // a line under the title
  children: ReactNode;
  footer?: ReactNode; // actions, pinned to the bottom
  // `bare` drops the header and its Close, the scrim click and Escape: the caller draws its own bar and
  // Escape belongs to the page behind (Take control's full screen). The title stays for screen readers.
  bare?: boolean;
  size?: "default" | "full" | "bottom"; // "full" fills the screen (the bot's profile on a phone); "bottom" rises from the bottom edge
}

// A drawer from the right edge (redesign P1, Radix Dialog): modal, focus kept inside, Escape and
// the scrim close it, and focus goes back to what opened it. The kit's overlays inside it (Select,
// Popover, Menu) draw inside its panel (redesign P3, ui/portalContainer.ts).
export function Sheet({ open, onOpenChange, title, description, children, footer, size = "default", bare = false }: SheetProps) {
  const opener = useRef<HTMLElement | null>(null);
  const [panel, setPanel] = useState<HTMLDivElement | null>(null);
  // Remembered as it opens, before focus moves in: a sheet opened from code has no Radix trigger.
  const remember = () => {
    opener.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
  };
  const giveBack = (event: Event) => {
    event.preventDefault();
    if (opener.current?.isConnected) opener.current.focus();
  };
  const hold = (event: Event) => event.preventDefault();
  const held = bare ? { onEscapeKeyDown: hold, onInteractOutside: hold, onPointerDownOutside: hold } : {};
  return (
    <RadixDialog.Root open={open} onOpenChange={onOpenChange}>
      <RadixDialog.Portal>
        <RadixDialog.Overlay className="ui-sheet__scrim" />
        <RadixDialog.Content ref={setPanel} className={cx("ui-sheet", size === "full" && "ui-sheet--full", size === "bottom" && "ui-sheet--bottom")} onOpenAutoFocus={remember} onCloseAutoFocus={giveBack} {...held}
          {...(description ? {} : { "aria-describedby": undefined })}>
          <PortalContainer.Provider value={panel}>
            {bare ? <RadixDialog.Title className="sr-only">{title}</RadixDialog.Title> : (
              <header className="ui-sheet__head">
                <RadixDialog.Title className="ui-sheet__title">{title}</RadixDialog.Title>
                <RadixDialog.Close asChild>
                  <IconButton label="Close" icon={<CloseIcon />} tooltip={false} />
                </RadixDialog.Close>
              </header>
            )}
            {description ? <RadixDialog.Description className="ui-sheet__description">{description}</RadixDialog.Description> : null}
            <div className={cx("ui-sheet__body", bare && "ui-sheet__body--bare")}>{children}</div>
            {footer ? <footer className="ui-sheet__foot">{footer}</footer> : null}
          </PortalContainer.Provider>
        </RadixDialog.Content>
      </RadixDialog.Portal>
    </RadixDialog.Root>
  );
}
