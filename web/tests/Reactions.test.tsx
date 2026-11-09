import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { MemoryRouter } from "react-router-dom";
import { MessageList } from "../src/components/MessageList";
import type { MessageOut } from "../src/api/types";

import { makeMessage } from "./fixtures";

afterEach(cleanup);

const REPLY = makeMessage({ id: "m1", seq: 1, body: "All done.", author_bot_id: "bot-1" });

// A stand-in for Chat: a pick adds the reaction message the server would store.
function Harness() {
  const [messages, setMessages] = useState<MessageOut[]>([REPLY]);
  const onReact = (id: string, key: string | null) => setMessages((prev) => [...prev, makeMessage({
    id: `r${prev.length}`, seq: prev.length + 1, kind: "reaction", role: "user", body: JSON.stringify({ target_id: id, key }),
  })]);
  return <MemoryRouter><MessageList messages={messages} botName="Scout" onReact={onReact} /></MemoryRouter>;
}

describe("tapbacks", () => {
  it("pick a tapback and see it under the message", async () => {
    render(<Harness />);
    expect(screen.queryByLabelText(/^Reaction:/)).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "React" }));
    await userEvent.click(screen.getByRole("button", { name: "Heart" }));
    expect(screen.getByLabelText("Reaction: Heart")).toBeInTheDocument();
    expect(screen.getAllByRole("listitem")).toHaveLength(1);                       // the reaction row itself is hidden
    await userEvent.click(screen.getByRole("button", { name: "React" }));
    await userEvent.click(screen.getByRole("button", { name: "Heart" }));            // the same one again clears it
    expect(screen.queryByLabelText(/^Reaction:/)).toBeNull();
  });

  it("the chip has a text label", async () => {
    render(<Harness />);
    await userEvent.click(screen.getByRole("button", { name: "React" }));

    await userEvent.click(screen.getByRole("button", { name: "Thumbs up" }));
    expect(screen.getByLabelText("Reaction: Thumbs up")).toHaveTextContent("👍");
  });
});
