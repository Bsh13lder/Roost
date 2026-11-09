import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { Layout } from "../src/components/Layout";

vi.mock("../src/pages/Home", () => ({ Home: () => <p>Chat list</p> }));
vi.mock("../src/hooks/useAttention", () => ({ useAttentionNotifications: () => undefined }));

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<p>Pick a chat</p>} />
          <Route path="/bots/:botId" element={<p>A chat</p>} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

afterEach(cleanup);

describe("Layout", () => {
  it("is the list view on / and the detail view on a chat (phones show one pane)", () => {
    const { container } = renderAt("/");
    expect(container.querySelector(".app-shell")).toHaveAttribute("data-view", "list");
    expect(screen.getByText("Chat list")).toBeInTheDocument();
    cleanup();
    const second = renderAt("/bots/bot-1");
    expect(second.container.querySelector(".app-shell")).toHaveAttribute("data-view", "detail");
    expect(screen.getByText("A chat")).toBeInTheDocument();
  });
});
