import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ShareTemplateDialog } from "../src/components/ShareTemplateDialog";
import { ApiError } from "../src/api/client";
import { makeBot } from "./fixtures";

const downloadMock = vi.fn();
vi.mock("../src/api/templates", () => ({
  downloadTemplate: (id: string) => downloadMock(id),
  templateFileName: (name: string) => `${name}.roost-bot.json`,
}));

afterEach(() => { cleanup(); downloadMock.mockReset(); vi.restoreAllMocks(); });

describe("ShareTemplateDialog", () => {
  it("lists exactly what the file holds and what it never holds", () => {
    render(<ShareTemplateDialog bot={makeBot({ name: "Scout", instructions: "Be brief." })} onClose={vi.fn()} />);
    const dialog = screen.getByRole("dialog", { name: "Share as Template" });
    expect(dialog).toHaveTextContent("Name: Scout");
    expect(dialog).toHaveTextContent("Instructions (9 characters)");
    expect(dialog).toHaveTextContent("never holds chats");
  });

  it("Save file downloads it", async () => {
    downloadMock.mockResolvedValue({ blob: new Blob(["{}"]), filename: "Scout.roost-bot.json" });
    URL.createObjectURL = vi.fn(() => "blob:x");
    URL.revokeObjectURL = vi.fn();
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
    render(<ShareTemplateDialog bot={makeBot({ name: "Scout" })} onClose={vi.fn()} />);
    await userEvent.click(screen.getByRole("button", { name: "Save file" }));
    expect(downloadMock).toHaveBeenCalledWith("bot-1");
    expect(click).toHaveBeenCalled();
    expect(await screen.findByText("Saved Scout.roost-bot.json.")).toBeInTheDocument();
  });

  it("a refused share says why", async () => {
    downloadMock.mockRejectedValue(new ApiError(422, "Not shared: an API key or token seems to be in the instructions. Remove it, then share again."));
    render(<ShareTemplateDialog bot={makeBot()} onClose={vi.fn()} />);
    await userEvent.click(screen.getByRole("button", { name: "Save file" }));
    expect(await screen.findByText(/Remove it, then share again/)).toBeInTheDocument();
  });
});
