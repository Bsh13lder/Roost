// The bot's profile (restructure slice 3): no tabs. The panel opens on the profile itself, a card of rows, and each
// row swaps the panel to its own page. The page lives in the chat's URL as ?panel=<page>.
export type PanelPage = "profile" | "plan" | "computer" | "library" | "settings";

export const PANEL_PAGES: ReadonlyArray<{ id: Exclude<PanelPage, "profile">; label: string }> = [
  { id: "plan", label: "Plan & routines" }, { id: "computer", label: "Computer" },
  { id: "library", label: "Library" }, { id: "settings", label: "Settings" },
];

// The old tabs' URLs keep working: Info's rows moved to Settings, Documents and Links are the Library.
const OLD_TABS: Readonly<Record<string, PanelPage>> = { info: "settings", documents: "library", links: "library" };

// The breakpoint every stylesheet already uses for a phone.
export const PHONE_QUERY = "(max-width: 768px)";
export const PANEL_PARAM = "panel";

export const pageLabel = (page: PanelPage): string =>
  PANEL_PAGES.find((one) => one.id === page)?.label ?? "Profile";

// null (no ?panel=) is closed; an old tab is mapped; anything else unknown opens the profile.
export function panelPage(value: string | null): PanelPage | null {
  if (value === null) return null;
  if (Object.hasOwn(OLD_TABS, value)) return OLD_TABS[value];
  if (value === "profile") return "profile";
  return PANEL_PAGES.find((page) => page.id === value)?.id ?? "profile";
}
