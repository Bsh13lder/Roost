import { describe, expect, it, vi, afterEach } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Composer } from "../src/components/Composer";

// The mic, stubbed: one tap puts fixed words in the box, the way a transcription does.
vi.mock("../src/components/chat/MicButton", () => ({
  MicButton: ({ onText }: { onText: (text: string) => void }) => (
    <button type="button" onClick={() => onText("I goed home")}>Speak</button>
  ),
}));

afterEach(() => {
  cleanup();
});

describe("Composer", () => {
  it("sends on Enter and clears the box", async () => {
    const user = userEvent.setup();
    const onSend = vi.fn();
    render(<Composer onSend={onSend} />);

    const box = screen.getByRole("textbox");
    await user.type(box, "hello{Enter}");

    expect(onSend).toHaveBeenCalledWith("hello", { spoken: false });
    expect(box).toHaveValue("");
  });

  it("inserts a newline on Shift+Enter instead of sending", async () => {
    const user = userEvent.setup();
    const onSend = vi.fn();
    render(<Composer onSend={onSend} />);

    const box = screen.getByRole("textbox");
    await user.type(box, "line one{Shift>}{Enter}{/Shift}line two");

    expect(onSend).not.toHaveBeenCalled();
    expect(box).toHaveValue("line one\nline two");
  });

  it("does not send an empty or whitespace-only message", async () => {
    const user = userEvent.setup();
    const onSend = vi.fn();
    render(<Composer onSend={onSend} />);

    const box = screen.getByRole("textbox");
    await user.type(box, "   {Enter}");

    expect(onSend).not.toHaveBeenCalled();
  });

  it("keeps the typed text in the box when onSend rejects, instead of losing it", async () => {
    // Regression: a transient send failure (dropped connection, momentary
    // 5xx) must not force the user to retype the message from memory —
    // the box only clears once onSend actually succeeds.
    const user = userEvent.setup();
    const onSend = vi.fn().mockRejectedValue(new Error("network down"));
    render(<Composer onSend={onSend} />);

    const box = screen.getByRole("textbox");
    await user.type(box, "hello{Enter}");

    await waitFor(() => expect(onSend).toHaveBeenCalledWith("hello", { spoken: false }));
    expect(box).toHaveValue("hello");
  });

  it("clears the box once a pending onSend resolves successfully", async () => {
    const user = userEvent.setup();
    const onSend = vi.fn().mockResolvedValue(undefined);
    render(<Composer onSend={onSend} />);

    const box = screen.getByRole("textbox");
    await user.type(box, "hello{Enter}");

    await waitFor(() => expect(box).toHaveValue(""));
  });

  // Review Focus 3: Japanese, Chinese and Korean input confirm a word with Enter.
  it("never sends on the Enter that confirms an IME candidate", () => {
    const onSend = vi.fn();
    render(<Composer onSend={onSend} />);
    const box = screen.getByRole("textbox");
    fireEvent.change(box, { target: { value: "にほんご" } });
    fireEvent.keyDown(box, { key: "Enter", isComposing: true });
    fireEvent.keyDown(box, { key: "Enter", keyCode: 229 }); // Safari, while the IME holds the key
    expect(onSend).not.toHaveBeenCalled();
    fireEvent.keyDown(box, { key: "Enter" });
    expect(onSend).toHaveBeenCalledWith("にほんご", { spoken: false });
  });

  it("grows with its text in any browser, up to eight lines, then scrolls", () => {
    render(<Composer onSend={vi.fn()} />);
    const box = screen.getByRole("textbox") as HTMLTextAreaElement;
    Object.assign(box.style, { lineHeight: "21px", paddingTop: "7px", paddingBottom: "7px" });
    Object.defineProperty(box, "scrollHeight", { configurable: true, get: () => 21 * box.value.split("\n").length + 14 });
    fireEvent.change(box, { target: { value: "one\ntwo\nthree" } });
    expect(box.style.height).toBe("77px");
    expect(box.style.overflowY).toBe("hidden");
    fireEvent.change(box, { target: { value: Array.from({ length: 12 }, (_, line) => `line ${line}`).join("\n") } });
    expect(box.style.height).toBe(`${21 * 8 + 14}px`);
    expect(box.style.overflowY).toBe("auto");
  });

  it("holds the leading + inside the pill, before the text", () => {
    const { container } = render(<Composer onSend={vi.fn()} leading={<button type="button">More</button>} />);
    const pill = container.querySelector(".composer") as HTMLElement;
    const more = screen.getByRole("button", { name: "More" });
    expect(pill).toContainElement(more);
    expect(more.compareDocumentPosition(screen.getByRole("textbox")) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(pill).toHaveClass("composer--leading");
  });

  // Spoken messages (English correction): a message whose words came from the voice service is sent with
  // `spoken`, unless you edited it after the transcription landed.
  describe("the spoken flag", () => {
    it("a dictated message sent untouched is spoken", async () => {
      const onSend = vi.fn();
      render(<Composer onSend={onSend} voice={{ onError: vi.fn() }} />);
      await userEvent.click(screen.getByRole("button", { name: "Speak" }));
      expect(screen.getByRole("textbox")).toHaveValue("I goed home");
      await userEvent.click(screen.getByRole("button", { name: "Send" }));
      expect(onSend).toHaveBeenCalledWith("I goed home", { spoken: true });
    });

    it("a keystroke after the transcription makes it typed", async () => {
      const onSend = vi.fn();
      render(<Composer onSend={onSend} voice={{ onError: vi.fn() }} />);
      await userEvent.click(screen.getByRole("button", { name: "Speak" }));
      await userEvent.type(screen.getByRole("textbox"), " now{Enter}");
      expect(onSend).toHaveBeenCalledWith("I goed home now", { spoken: false });
    });

    it("the flag does not outlive the message: the next typed one is not spoken", async () => {
      const onSend = vi.fn();
      render(<Composer onSend={onSend} voice={{ onError: vi.fn() }} />);
      await userEvent.click(screen.getByRole("button", { name: "Speak" }));
      await userEvent.click(screen.getByRole("button", { name: "Send" }));
      await userEvent.type(screen.getByRole("textbox"), "typed{Enter}");
      expect(onSend).toHaveBeenLastCalledWith("typed", { spoken: false });
    });
  });
});
