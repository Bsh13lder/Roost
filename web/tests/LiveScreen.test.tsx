import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { LiveScreen } from "../src/components/computer/LiveScreen";
import { makeBot } from "./fixtures";

afterEach(cleanup);

describe("LiveScreen", () => {
  it("shows the live canvas named for the bot", async () => {
    const socket = { addEventListener: vi.fn(), removeEventListener: vi.fn(), close: vi.fn() };
    const loadRfb = vi.fn(async () => class { viewOnly = false; addEventListener() {} disconnect() {} } as never);
    render(<LiveScreen bot={makeBot({ name: "Scout" })} mode="view" onAsleep={() => {}}
      openSocket={() => socket as unknown as WebSocket} loadRfb={loadRfb} />);
    expect(screen.getByLabelText("Scout’s screen, live")).toBeInTheDocument();
    await waitFor(() => expect(loadRfb).toHaveBeenCalled());
  });
});
