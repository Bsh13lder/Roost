import * as RadixTabs from "@radix-ui/react-tabs";
import type { ReactNode } from "react";
import { cx } from "./cx";

export interface TabItem<T extends string> {
  id: T;
  label: string;
  count?: number; // drawn after the label, hidden from the accessible name; 0 or none draws nothing
  countTone?: "danger";
}

export interface TabsProps<T extends string> {
  label: string; // the tab list's accessible name
  tabs: ReadonlyArray<TabItem<T>>;
  value: T;
  onChange: (value: T) => void;
  children: ReactNode; // the selected tab's panel
  panelClassName?: string;
  variant?: "pill" | "line"; // line: an underline on the selected tab (the Board)
  head?: ReactNode; // sits above the list, in the same sticky block (the Board's title row)
  headClassName?: string;
}

// One tab style everywhere (redesign P1, Radix Tabs): arrow keys move and select, Home and End jump.
// The caller keeps the selected tab (in the URL) and renders only its panel.
export function Tabs<T extends string>({
  label, tabs, value, onChange, children, panelClassName, variant = "pill", head, headClassName,
}: TabsProps<T>) {
  const list = (
    <RadixTabs.List className="tabs__list" aria-label={label}>
      {tabs.map((tab) => (
        <RadixTabs.Trigger key={tab.id} value={tab.id} className="tabs__tab">
          {tab.label}
          {tab.count ? (
            <span className={cx("tabs__count", tab.countTone === "danger" && "tabs__count--danger")} aria-hidden="true">
              {tab.count}
            </span>
          ) : null}
        </RadixTabs.Trigger>
      ))}
    </RadixTabs.List>
  );
  return (
    <RadixTabs.Root className={cx("tabs", variant === "line" && "tabs--line")} value={value}
      onValueChange={(next) => onChange(next as T)}>
      {head ? <header className={cx("tabs__head", headClassName)}>{head}{list}</header> : list}
      <RadixTabs.Content value={value} className={cx("tabs__panel", panelClassName)}>{children}</RadixTabs.Content>
    </RadixTabs.Root>
  );
}
