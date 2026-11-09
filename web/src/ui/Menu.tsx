import * as RadixMenu from "@radix-ui/react-dropdown-menu";
import { createContext, useContext, useRef, type ReactNode, type RefObject } from "react";
import { Link } from "react-router-dom";
import { usePortalContainer } from "./portalContainer";

export interface MenuProps {
  label: string; // names the button and the menu
  trigger: ReactNode; // what the button shows (an icon, initials)
  children: ReactNode; // MenuItem, MenuSwitch, MenuLink and MenuNote
  side?: "top" | "bottom";
  align?: "start" | "end";
  open?: boolean; // controlled when given, with onOpenChange (a long-press opens a row's menu)
  onOpenChange?: (open: boolean) => void;
  triggerClassName?: string; // the button's look; a round icon button unless given (the chat mode pill)
}

// The menu's own button, for its items (MenuItem).
const MenuButton = createContext<RefObject<HTMLButtonElement | null> | null>(null);

// Radix gives focus back to the button when the menu closes. When the chosen item has already put
// focus somewhere (New room focuses the dialog's name field), leave it there.
function keepFocusAnItemMoved(event: Event) {
  const active = document.activeElement;
  const moved = active instanceof HTMLElement && active !== document.body && active.isConnected
    && !active.closest("[role='menu']");
  if (moved) event.preventDefault();
}

// A pop-up menu (redesign P1, Radix DropdownMenu): arrow keys, typeahead, Escape, and focus back to
// its button. Picking an item closes it. Not modal: an item may open a dialog that takes the focus.
export function Menu({
  label, trigger, children, side = "bottom", align = "end", open, onOpenChange, triggerClassName = "icon-btn",
}: MenuProps) {
  const button = useRef<HTMLButtonElement>(null);
  const container = usePortalContainer();
  return (
    <div className="menu">
      <MenuButton.Provider value={button}>
        <RadixMenu.Root modal={false} open={open} onOpenChange={onOpenChange}>
          <RadixMenu.Trigger ref={button} className={triggerClassName} aria-label={label}>{trigger}</RadixMenu.Trigger>
          <RadixMenu.Portal container={container}>
            <RadixMenu.Content className="menu__list" side={side} align={align} sideOffset={6}
              onCloseAutoFocus={keepFocusAnItemMoved}>
              {children}
            </RadixMenu.Content>
          </RadixMenu.Portal>
        </RadixMenu.Root>
      </MenuButton.Provider>
    </div>
  );
}

// Focus goes back to the menu's button before the item acts (redesign P3). The item is gone once the
// menu closes, so a Sheet it opens remembers the button as its opener and gives focus back to it; a
// dialog that focuses its own field keeps that focus (keepFocusAnItemMoved).
export function MenuItem({ onSelect, disabled = false, title, danger = false, children }: {
  onSelect: () => void; disabled?: boolean; title?: string; danger?: boolean; children: ReactNode;
}) {
  const button = useContext(MenuButton);
  const select = () => {
    button?.current?.focus();
    onSelect();
  };
  return (
    <RadixMenu.Item className={danger ? "menu__item menu__item--danger" : "menu__item"} disabled={disabled} title={title}
      onSelect={select}>
      {children}
    </RadixMenu.Item>
  );
}

// A setting in the menu (Calm robots): a checkbox item, so its state is read aloud and shown with a tick.
export function MenuSwitch({ checked, onCheckedChange, children }: {
  checked: boolean; onCheckedChange: (checked: boolean) => void; children: ReactNode;
}) {
  return (
    <RadixMenu.CheckboxItem className="menu__item menu__item--switch" checked={checked} onCheckedChange={onCheckedChange}>
      <span className="menu__switch-box" aria-hidden="true">
        <RadixMenu.ItemIndicator className="menu__switch-tick">✓</RadixMenu.ItemIndicator>
      </span>
      {children}
    </RadixMenu.CheckboxItem>
  );
}

// One choice of several (the chat mode): radio items, so the chosen one is read aloud as checked and shown with a dot.
export function MenuRadioGroup<T extends string>({ value, onValueChange, children }: {
  value: T; onValueChange: (value: T) => void; children: ReactNode;
}) {
  return (
    <RadixMenu.RadioGroup value={value} onValueChange={(next) => onValueChange(next as T)}>
      {children}
    </RadixMenu.RadioGroup>
  );
}

export function MenuRadioItem({ value, disabled = false, children }: { value: string; disabled?: boolean; children: ReactNode }) {
  return (
    <RadixMenu.RadioItem className="menu__item menu__item--radio" value={value} disabled={disabled}>
      <span className="menu__radio-dot" aria-hidden="true">
        <RadixMenu.ItemIndicator className="menu__radio-fill" />
      </span>
      {children}
    </RadixMenu.RadioItem>
  );
}

export function MenuLink({ to, children }: { to: string; children: ReactNode }) {
  return (
    <RadixMenu.Item asChild className="menu__item">
      <Link to={to}>{children}</Link>
    </RadixMenu.Item>
  );
}

export function MenuSeparator() {
  return <RadixMenu.Separator className="menu__sep" />;
}

export function MenuNote({ children }: { children: ReactNode }) {
  return <RadixMenu.Label className="menu__note">{children}</RadixMenu.Label>;
}
