import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MentionComposer, insertMention, mentionQuery, withReplyMention } from "../src/components/MentionComposer";

afterEach(() => cleanup());

const MEMBERS = [{ id: "c", name: "Chief" }, { id: "s", name: "Scout" }, { id: "q", name: "Quill" }];

describe("mention helpers", () => {
  it("finds the @word being typed", () => {
    expect(mentionQuery("ask @Sc")).toBe("Sc");
    expect(mentionQuery("@")).toBe("");
    expect(mentionQuery("mail me@scout")).toBeNull();
    expect(mentionQuery("no mention")).toBeNull();
  });

  it("replaces the partial mention with the full name", () => {
    expect(insertMention("ask @Sc now", 7, "Scout")).toEqual({ text: "ask @Scout  now", caret: 11 });
  });

  it("puts a reply's mention in front of the draft once", () => {
    expect(withReplyMention("thanks", "Chief")).toBe("@Chief thanks");
    expect(withReplyMention("@Chief thanks", "Chief")).toBe("@Chief thanks");
  });
});

describe("MentionComposer", () => {
  function setup() {
    const onSend = vi.fn().mockResolvedValue(undefined);
    render(<MentionComposer members={MEMBERS} onSend={onSend} placeholder="Message the room… (@ to mention)" />);
    return { onSend, box: screen.getByPlaceholderText("Message the room… (@ to mention)") };
  }

  it("suggests members and @everyone while typing @, and inserts the pick with Enter", async () => {
    const { box, onSend } = setup();
    await userEvent.type(box, "@");
    expect(screen.getAllByRole("option").map((o) => o.textContent)).toEqual(["@Chief", "@Scout", "@Quill", "@everyone"]);
    await userEvent.type(box, "Sc{Enter}");
    expect(box).toHaveValue("@Scout ");
    expect(onSend).not.toHaveBeenCalled();
  });

  it("moves through options with the arrow keys and closes with Escape", async () => {
    const { box } = setup();
    await userEvent.type(box, "@{ArrowDown}");
    expect(screen.getAllByRole("option")[1]).toHaveAttribute("aria-selected", "true");
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
  });

  it("puts the caret right after a mention picked mid-text, so typing goes on from there", async () => {
    const { box } = setup();
    await userEvent.type(box, "ask now{ArrowLeft}{ArrowLeft}{ArrowLeft}@Sc{Enter}x");
    expect(box).toHaveValue("ask @Scout xnow");
  });

  it("sends with Enter when no list is open and clears after a successful send", async () => {
    const { box, onSend } = setup();
    await userEvent.type(box, "plan Saturday{Enter}");
    expect(onSend).toHaveBeenCalledWith("plan Saturday");
    expect(box).toHaveValue("");
  });

  it("never sends on the Enter that confirms an IME candidate, and grows with its text", () => {
    const { box, onSend } = setup();
    Object.assign(box.style, { lineHeight: "21px", paddingTop: "7px", paddingBottom: "7px" });
    Object.defineProperty(box, "scrollHeight", { configurable: true, get: () => 21 * (box as HTMLTextAreaElement).value.split("\n").length + 14 });
    fireEvent.change(box, { target: { value: "にほんご\nです" } });
    fireEvent.keyDown(box, { key: "Enter", isComposing: true });
    expect(onSend).not.toHaveBeenCalled();
    expect(box.style.height).toBe("56px");
  });

  it("a reply puts the mention in front of the draft and focuses the box", async () => {
    const onSend = vi.fn().mockResolvedValue(undefined);
    const { rerender } = render(<MentionComposer members={MEMBERS} onSend={onSend} placeholder="p" />);
    const box = screen.getByPlaceholderText("p");
    await userEvent.type(box, "thanks");
    box.blur();
    rerender(<MentionComposer members={MEMBERS} onSend={onSend} placeholder="p" replyTo={{ name: "Scout", nonce: 1 }} />);
    expect(box).toHaveValue("@Scout thanks");
    expect(box).toHaveFocus();
  });
});
