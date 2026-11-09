import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { EnglishFixRow, EnglishFixText, YOU_SAID_LABEL } from "../src/components/chat/EnglishFixRow";
import { makeMessage } from "./fixtures";

const FIX = {
  message_id: "u1",
  said: "I goed to the shop and buyed milk",
  corrected: "I went to the shop and bought milk",
  fixes: [{ wrong: "goed", right: "went" }, { wrong: "buyed", right: "bought" }],
};
const line = (body: unknown) => makeMessage({ id: "f1", role: "activity", kind: "english_fix", body: JSON.stringify(body) });

afterEach(() => cleanup());

describe("EnglishFixRow", () => {
  it("is a quiet card: the corrected sentence, each fix struck through and set right, then what you said", () => {
    const { container } = render(<ul><EnglishFixRow message={line(FIX)} /></ul>);
    const row = container.querySelector("li");
    expect(row).toHaveClass("message", "message--english-fix");
    expect(row).toHaveAttribute("data-message-id", "f1");
    const sentence = container.querySelector(".english-fix__sentence");
    expect(sentence).toHaveTextContent("I goedwent to the shop and buyedbought milk");
    expect(screen.getByText("goed").tagName).toBe("DEL");
    expect(screen.getByText("goed")).toHaveClass("english-fix__wrong");
    expect(screen.getByText("went").tagName).toBe("INS");
    expect(screen.getByText("went")).toHaveClass("english-fix__right");
    expect(screen.getByText(`${YOU_SAID_LABEL} I goed to the shop and buyed milk`)).toHaveClass("english-fix__said");
  });

  it("a fix that is not in the sentence trails as wrong → right", () => {
    render(<ul><EnglishFixRow message={line({ ...FIX, fixes: [{ wrong: "purchased", right: "bought" }] })} /></ul>);
    const trail = screen.getByText("purchased").closest(".english-fix__trail");
    expect(trail).toHaveTextContent("purchased → bought");
    expect(screen.getByText("purchased").tagName).toBe("DEL");
  });

  it("a body that is not an english_fix draws nothing", () => {
    const { container } = render(<ul><EnglishFixRow message={line("x")} /></ul>);
    expect(container.querySelector("li")).toBeNull();
  });

  it("EnglishFixText alone serves the call screen's caption", () => {
    render(<EnglishFixText fix={FIX} />);
    expect(screen.getByText("bought").tagName).toBe("INS");
    expect(screen.getByText(/You said:/)).toBeInTheDocument();
  });
});
