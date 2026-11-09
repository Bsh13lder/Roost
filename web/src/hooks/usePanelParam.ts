import { useCallback } from "react";
import { useLocation, useSearchParams } from "react-router-dom";
import { PANEL_PARAM, panelPage, type PanelPage } from "../components/panel/panelTabs";

// The bot panel's page lives in the chat's URL as ?panel=. Opening pushes a history entry, moving between pages
// and closing replace it, and every other param (?thread=) is kept.
export function usePanelParam() {
  const [params, setParams] = useSearchParams();
  const { pathname } = useLocation();
  const page = panelPage(params.get(PANEL_PARAM));

  const withPanel = useCallback((next: PanelPage | null): URLSearchParams => {
    const copy = new URLSearchParams(params);
    if (next === null) copy.delete(PANEL_PARAM);
    else copy.set(PANEL_PARAM, next);
    return copy;
  }, [params]);

  const hrefFor = useCallback((next: PanelPage | null): string => {
    const query = withPanel(next).toString();
    return query ? `${pathname}?${query}` : pathname;
  }, [pathname, withPanel]);

  const open = useCallback((next: PanelPage = "profile") => setParams(withPanel(next)), [setParams, withPanel]);
  const select = useCallback((next: PanelPage) => setParams(withPanel(next), { replace: true }), [setParams, withPanel]);
  const close = useCallback(() => setParams(withPanel(null), { replace: true }), [setParams, withPanel]);
  return { page, open, select, close, hrefFor };
}
