import { afterEach, describe, expect, it } from "vitest";
import { act, cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter, useLocation, useNavigate } from "react-router-dom";
import { usePanelParam } from "../src/hooks/usePanelParam";

function Probe() {
  const panel = usePanelParam();
  const { pathname, search } = useLocation();
  const navigate = useNavigate();
  return (
    <div>
      <p data-testid="tab">{String(panel.page)}</p>
      <p data-testid="where">{pathname + search}</p>
      <p data-testid="href">{panel.hrefFor("library")}</p>
      <p data-testid="closed">{panel.hrefFor(null)}</p>
      <button onClick={() => panel.open()}>open</button>
      <button onClick={() => panel.select("computer")}>select</button>
      <button onClick={() => panel.close()}>close</button>
      <button onClick={() => navigate(-1)}>back</button>
    </div>
  );
}

const renderAt = (path: string) => render(<MemoryRouter initialEntries={[path]}><Probe /></MemoryRouter>);
const click = (name: string) => act(() => { screen.getByRole("button", { name }).click(); });

afterEach(() => cleanup());

describe("usePanelParam", () => {
  it("maps the old tab URLs to the new pages", () => {
    for (const [old, page] of [["info", "settings"], ["documents", "library"], ["links", "library"], ["plan", "plan"], ["computer", "computer"], ["settings", "settings"]]) {
      renderAt(`/bots/b1?panel=${old}`);
      expect(screen.getByTestId("tab"), old).toHaveTextContent(page);
      cleanup();
    }
  });

  it("reads the page from ?panel= and an unknown one as the profile", () => {
    renderAt("/bots/b1?panel=computer");
    expect(screen.getByTestId("tab")).toHaveTextContent("computer");
    cleanup();
    renderAt("/bots/b1?panel=nonsense");
    expect(screen.getByTestId("tab")).toHaveTextContent("profile");
    cleanup();
    renderAt("/bots/b1");
    expect(screen.getByTestId("tab")).toHaveTextContent("null");
  });

  it("opens with a new history entry, switches and closes in place", () => {
    renderAt("/bots/b1");
    click("open");
    expect(screen.getByTestId("where")).toHaveTextContent("/bots/b1?panel=profile");
    click("select");
    expect(screen.getByTestId("where")).toHaveTextContent("/bots/b1?panel=computer");
    click("close");
    expect(screen.getByTestId("where")).toHaveTextContent(/^\/bots\/b1$/);
    click("back"); // close and select replaced entries: back goes to the page before the open
    expect(screen.getByTestId("where")).toHaveTextContent(/^\/bots\/b1$/);
  });

  it("keeps ?thread= while it opens and closes", () => {
    renderAt("/bots/b1?thread=t-9");
    expect(screen.getByTestId("href")).toHaveTextContent("/bots/b1?thread=t-9&panel=library");
    click("open");
    expect(screen.getByTestId("where")).toHaveTextContent("/bots/b1?thread=t-9&panel=profile");
    click("close");
    expect(screen.getByTestId("where")).toHaveTextContent("/bots/b1?thread=t-9");
    expect(screen.getByTestId("closed")).toHaveTextContent("/bots/b1?thread=t-9");
  });
});
