import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter, Outlet, useLocation } from "react-router-dom";
import { AppRoutes } from "../src/App";

vi.mock("../src/hooks/useAuth", () => ({
  AuthProvider: ({ children }: { children: unknown }) => children,
  useAuth: () => ({ user: { id: "u1" }, loading: false }),
}));
vi.mock("../src/components/Layout", () => ({ Layout: () => <Outlet /> }));
vi.mock("../src/pages/Chat", () => {
  const Where = () => {
    const { pathname, search } = useLocation();
    return <p data-testid="chat">{pathname + search}</p>;
  };
  return { Chat: Where };
});
vi.mock("../src/pages/Login", () => ({ Login: () => null }));
vi.mock("../src/pages/PickAChat", () => ({ PickAChat: () => null }));
vi.mock("../src/pages/NewBot", () => ({ NewBot: () => <p data-testid="page">new bot</p> }));
vi.mock("../src/pages/Room", () => ({ Room: () => <p data-testid="page">room</p> }));
vi.mock("../src/pages/Board", () => {
  const Board = () => {
    const { pathname, search } = useLocation();
    return <p data-testid="page">{`board ${pathname + search}`}</p>;
  };
  return { Board };
});
vi.mock("../src/pages/Instructions", () => ({ Instructions: () => <p data-testid="page">instructions</p> }));
vi.mock("../src/pages/Project", () => ({ Project: () => <p data-testid="page">project</p> }));

const at = (path: string) => render(<MemoryRouter initialEntries={[path]}><AppRoutes /></MemoryRouter>);
afterEach(() => cleanup());

describe("the old addresses", () => {
  it("the old profile address opens the panel on its tab's new page", () => {
    at("/bots/b1/profile?tab=documents");
    expect(screen.getByTestId("chat")).toHaveTextContent("/bots/b1?panel=library");
  });

  it("an unknown or missing tab opens the profile", () => {
    at("/bots/b1/profile?tab=nonsense");
    expect(screen.getByTestId("chat")).toHaveTextContent("/bots/b1?panel=profile");
    cleanup();
    at("/bots/b1/profile");
    expect(screen.getByTestId("chat")).toHaveTextContent("/bots/b1?panel=profile");
  });

  it("the old desk address opens the Computer tab", () => {
    at("/bots/b1/desk");
    expect(screen.getByTestId("chat")).toHaveTextContent("/bots/b1?panel=computer");
  });
});

// Lead task 03: the big pages are their own chunks. Each route shows a calm "Loading…" while its chunk
// arrives, then the page.
describe("the lazy pages", () => {
  it.each([
    ["/board", "board /board"],
    ["/board/projects/p1", "project"],
    ["/bots/new", "new bot"],
    ["/rooms/r1", "room"],
    ["/bots/b1/instructions", "instructions"],
  ])("%s shows the loading line, then its page", async (path, text) => {
    at(path);
    expect(screen.getByRole("status")).toHaveTextContent("Loading…");
    expect(await screen.findByTestId("page")).toHaveTextContent(text);
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("/board/projects opens the Tasks area on All tasks (lead task 15: no Projects tab)", async () => {
    at("/board/projects");
    expect(await screen.findByTestId("page")).toHaveTextContent("board /board?tab=tasks&project=all");
  });
});
