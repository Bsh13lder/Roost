import { afterEach, describe, expect, it, vi } from "vitest";
import { useState, type ReactElement } from "react";
import { act, cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AvatarPicker } from "../src/components/AvatarPicker";
import { AvatarEditor } from "../src/components/profile/AvatarEditor";
import type { AvatarOut } from "../src/api/types";
import { makeBot } from "./fixtures";

const updateBotMock = vi.fn();
const uploadPictureMock = vi.fn();
const removePictureMock = vi.fn();
vi.mock("../src/api/bots", () => ({
  updateBot: (id: string, p: unknown) => updateBotMock(id, p),
  uploadPicture: (id: string, picture: Blob) => uploadPictureMock(id, picture),
  removePicture: (id: string) => removePictureMock(id),
}));
const shrinkMock = vi.fn();
vi.mock("../src/lib/picture", async (original) => ({
  ...(await original<typeof import("../src/lib/picture")>()),
  shrinkPicture: (file: Blob) => shrinkMock(file),
}));
vi.mock("../src/hooks/useTemplates", () => ({
  useTemplates: () => ({ templates: [{ id: "chief", label: "Main bot", name: "Chief", job: "", instructions: "",
    avatar: { shape: "tall", color: "#eab308", badge: "none" } }], error: null }),
}));

afterEach(() => {
  cleanup();
  for (const mock of [updateBotMock, uploadPictureMock, removePictureMock, shrinkMock]) mock.mockReset();
});

const PNG = new File([new Uint8Array([137, 80, 78, 71])], "me.png", { type: "image/png" });

async function renderOpen(ui: ReactElement) {
  const result = render(ui);
  await userEvent.click(screen.getByRole("button", { name: "Edit look" }));
  return result;
}

async function openUpload() {
  await userEvent.click(screen.getByRole("tab", { name: "Upload" }));
}

describe("AvatarEditor (the hero robot)", () => {
  it("shows only the robot until you click it: no pickers, a pencil and the name Edit look", () => {
    render(<AvatarEditor bot={makeBot({ name: "Scout" })} onChange={vi.fn()} />);
    const trigger = screen.getByRole("button", { name: "Edit look" });
    expect(trigger.querySelector("svg.avatar")).not.toBeNull();
    expect(trigger.querySelector(".look-trigger__pencil")).not.toBeNull();
    expect(screen.queryByRole("radio")).not.toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("opens a compact card with Robot and Upload tabs, Surprise me and Reset; Escape closes it and gives focus back", async () => {
    render(<AvatarEditor bot={makeBot()} onChange={vi.fn()} />);
    const trigger = screen.getByRole("button", { name: "Edit look" });
    await userEvent.click(trigger);
    expect(screen.getByRole("dialog", { name: "Edit look" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Robot" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: "Upload" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Surprise me" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reset" })).toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "Reset" })).not.toBeInTheDocument();
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });
});

describe("AvatarEditor", () => {
  it("offers eighteen Lensbot shapes and twelve colours, no screen row, and the hero robot showing the bot's status", async () => {
    await renderOpen(<AvatarEditor bot={makeBot({ status: "on_it", is_primary: true })} onChange={vi.fn()} />);
    expect(screen.getAllByRole("radio", {
      name: /^(Mochi|Loaf|Gumdrop|Pebble|Bun|Acorn|Marshmallow|Dumpling|Muffs|Squish|Cub|Sprout|Cheeky|Tower|Helmet|Bell|Puck|Pod)$/,
    })).toHaveLength(18);
    expect(screen.getByRole("radio", { name: "White" })).toBeInTheDocument();
    expect(screen.queryByRole("radio", { name: /^(Glow icons|Pixel icons|Signals)$/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("group", { name: "Screen" })).not.toBeInTheDocument();
    const hero = screen.getByRole("button", { name: "Edit look" });
    expect(hero.querySelector("svg.avatar")?.getAttribute("data-moment")).toBe("onit");
    expect(hero.querySelector(".robot__star")).not.toBeNull();
  });

  it("an old bird shape shows as its Lensbot, and a new shape saves at once, with no badge and the stored screen", async () => {
    const onChange = vi.fn();
    const saved = makeBot({ avatar: { shape: "helmet", color: "#10b981", badge: "none", screen: "glow" } });
    let land: (bot: typeof saved) => void = () => {};
    updateBotMock.mockReturnValue(new Promise((resolve) => { land = resolve; }));
    await renderOpen(<AvatarEditor bot={makeBot()} onChange={onChange} />); // makeBot wears "round", a bird name and a ghost name
    expect(screen.getByRole("radio", { name: "Bun" })).toBeChecked();
    await userEvent.click(screen.getByRole("radio", { name: "Helmet" }));
    expect(updateBotMock).toHaveBeenCalledWith("bot-1", { avatar: { shape: "helmet", color: "#10b981", badge: "none", screen: "glow" } });
    // The hero shows the pick before the save lands.
    expect(screen.getByRole("button", { name: "Edit look" }).querySelector("svg.avatar")?.getAttribute("data-shape")).toBe("helmet");
    await act(async () => { land(saved); });
    await vi.waitFor(() => expect(onChange).toHaveBeenCalledWith(saved));
  });

  it("an old head and an old ghost show as their Lensbots", async () => {
    await renderOpen(<AvatarEditor bot={makeBot({ avatar: { shape: "monitor", color: "#10b981", badge: "none" } })} onChange={vi.fn()} />);
    expect(screen.getByRole("radio", { name: "Bell" })).toBeChecked();
    cleanup();
    await renderOpen(<AvatarEditor bot={makeBot({ avatar: { shape: "comet", color: "#10b981", badge: "none" } })} onChange={vi.fn()} />);
    expect(screen.getByRole("radio", { name: "Pebble" })).toBeChecked();
  });

  it("a drag across the tiles morphs the hero through each shape and saves the one it is released on", async () => {
    updateBotMock.mockResolvedValue(makeBot());
    await renderOpen(<AvatarEditor bot={makeBot({ avatar: { shape: "mochi", color: "#8b5cf6", badge: "none" } })} onChange={vi.fn()} />);
    const hero = () => screen.getByRole("button", { name: "Edit look" }).querySelector("svg.avatar");
    const tiles = screen.getByRole("group", { name: "Shape" });
    const tile = (name: string) => screen.getByRole("radio", { name }).closest("label")!;
    let under: Element = tile("Mochi");
    document.elementFromPoint = () => under;
    // jsdom has no PointerEvent: a MouseEvent of the pointer's name carries the button and the place.
    const pointer = (type: string, x: number) => act(() => {
      tiles.dispatchEvent(new MouseEvent(type, { bubbles: true, clientX: x, clientY: 10, buttons: 1 }));
    });
    pointer("pointerdown", 10);
    under = tile("Acorn");
    pointer("pointermove", 60);
    expect(hero()?.getAttribute("data-shape")).toBe("acorn");
    expect(screen.getByRole("radio", { name: "Acorn" })).toBeChecked();
    expect(updateBotMock).not.toHaveBeenCalled();
    under = tile("Cub");
    pointer("pointermove", 110);
    expect(hero()?.getAttribute("data-shape")).toBe("cub");
    act(() => { window.dispatchEvent(new MouseEvent("pointerup", { bubbles: true })); });
    expect(updateBotMock).toHaveBeenCalledTimes(1);
    expect(updateBotMock).toHaveBeenCalledWith("bot-1", { avatar: { shape: "cub", color: "#8b5cf6", badge: "none", screen: "glow" } });
    expect(hero()?.getAttribute("data-shape")).toBe("cub");
  });

  it("Surprise me saves a new shape and a new colour", async () => {
    updateBotMock.mockResolvedValue(makeBot());
    await renderOpen(<AvatarEditor bot={makeBot({ avatar: { shape: "mochi", color: "#8b5cf6", badge: "none", screen: "glow" } })} onChange={vi.fn()} />);
    await userEvent.click(screen.getByRole("button", { name: "Surprise me" }));
    const [, patch] = updateBotMock.mock.calls[0] as [string, { avatar: { shape: string; color: string } }];
    expect(patch.avatar.shape).not.toBe("mochi");
    expect(patch.avatar.color).not.toBe("#8b5cf6");
  });

  it("Reset to default uses the bot's template look", async () => {
    updateBotMock.mockResolvedValue(makeBot());
    await renderOpen(<AvatarEditor bot={makeBot({ template_id: "chief" })} onChange={vi.fn()} />);
    await userEvent.click(screen.getByRole("button", { name: "Reset" }));
    expect(updateBotMock).toHaveBeenCalledWith("bot-1", { avatar: { shape: "tall", color: "#eab308", badge: "none", screen: "glow" } });
  });

  it("uploads a picture, shrunk first, and shows it inside the robot", async () => {
    const small = new Blob(["webp"], { type: "image/webp" });
    shrinkMock.mockResolvedValue(small);
    const withPicture = makeBot({ avatar: { shape: "round", color: "#10b981", badge: "none", screen: "glow", picture: "/api/bots/bot-1/picture?v=abc123def456" } });
    uploadPictureMock.mockResolvedValue(withPicture);
    const onChange = vi.fn();
    const { rerender } = await renderOpen(<AvatarEditor bot={makeBot()} onChange={onChange} />);
    await openUpload();
    await userEvent.upload(screen.getByLabelText("Upload a picture"), PNG);
    expect(shrinkMock).toHaveBeenCalledWith(PNG);
    expect(uploadPictureMock).toHaveBeenCalledWith("bot-1", small);
    await vi.waitFor(() => expect(onChange).toHaveBeenCalledWith(withPicture));
    rerender(<AvatarEditor bot={withPicture} onChange={onChange} />);
    const preview = screen.getByRole("button", { name: "Edit look" });
    expect(preview.querySelector("image.robot__picture")?.getAttribute("href")).toBe("/api/bots/bot-1/picture?v=abc123def456");
  });

  it("Remove picture takes it out of the robot", async () => {
    removePictureMock.mockResolvedValue(makeBot());
    await renderOpen(<AvatarEditor bot={makeBot({ avatar: { shape: "soft", color: "#14b8a6", badge: "none", picture: "/api/bots/bot-1/picture?v=1" } })} onChange={vi.fn()} />);
    await openUpload();
    await userEvent.click(screen.getByRole("button", { name: "Remove picture" }));
    expect(removePictureMock).toHaveBeenCalledWith("bot-1");
  });

  it("says why a picture can't be used, in plain words", async () => {
    const { PictureError } = await import("../src/lib/picture");
    shrinkMock.mockRejectedValue(new PictureError("Roost could not read that picture. Try another one."));
    await renderOpen(<AvatarEditor bot={makeBot()} onChange={vi.fn()} />);
    await openUpload();
    await userEvent.upload(screen.getByLabelText("Upload a picture"), PNG);
    expect(await screen.findByRole("alert")).toHaveTextContent("Roost could not read that picture. Try another one.");
    expect(uploadPictureMock).not.toHaveBeenCalled();
  });

  it("shows the gateway's refusal of a picture", async () => {
    const { ApiError } = await import("../src/api/client");
    shrinkMock.mockResolvedValue(new Blob(["x"], { type: "image/webp" }));
    uploadPictureMock.mockRejectedValue(new ApiError(413, "That picture is too big (512 KB at most). Try a smaller one."));
    await renderOpen(<AvatarEditor bot={makeBot()} onChange={vi.fn()} />);
    await openUpload();
    await userEvent.upload(screen.getByLabelText("Upload a picture"), PNG);
    expect(await screen.findByRole("alert")).toHaveTextContent("That picture is too big");
  });
});

describe("AvatarEditor, the Role row", () => {
  const roleRow = () => within(screen.getByRole("group", { name: "Role" }));
  const ROLES = ["General", "Tasks", "Code", "SEO", "Money", "Social", "Research", "Writer"];

  it("offers the eight roles as chips, with the bot's own pressed", async () => {
    await renderOpen(<AvatarEditor bot={makeBot({ avatar: { shape: "marsh", color: "#3b82f6", badge: "none", role: "code" } })} onChange={vi.fn()} />);
    expect(roleRow().getAllByRole("button").map((chip) => chip.textContent)).toEqual(ROLES);
    expect(roleRow().getByRole("button", { name: "Code" })).toHaveAttribute("aria-pressed", "true");
    expect(roleRow().getByRole("button", { name: "SEO" })).toHaveAttribute("aria-pressed", "false");
    expect(screen.queryByText(/Suggested from its job/)).not.toBeInTheDocument();
  });

  it("with no role set, suggests one from the job and never saves it on its own; one click confirms it", async () => {
    updateBotMock.mockResolvedValue(makeBot());
    await renderOpen(<AvatarEditor bot={makeBot({ job: "Improves HiMap's SEO", avatar: { shape: "pod", color: "#3b82f6", badge: "none" } })}
      onChange={vi.fn()} />);
    expect(screen.getByText(/Suggested from its job/)).toHaveTextContent("Suggested from its job: SEO");
    const seo = roleRow().getByRole("button", { name: "SEO" });
    expect(seo).toHaveClass("chip--suggested");
    expect(seo).toHaveAttribute("aria-pressed", "false");
    expect(updateBotMock).not.toHaveBeenCalled();
    await userEvent.click(seo);
    expect(updateBotMock).toHaveBeenCalledWith("bot-1", {
      avatar: { shape: "pod", color: "#3b82f6", badge: "none", screen: "glow", role: "seo" } });
  });

  it("suggests nothing when the job names no role", async () => {
    await renderOpen(<AvatarEditor bot={makeBot()} onChange={vi.fn()} />); // "Finds things on the web"
    expect(screen.queryByText(/Suggested from its job/)).not.toBeInTheDocument();
    expect(roleRow().getAllByRole("button").filter((chip) => chip.classList.contains("chip--suggested"))).toHaveLength(0);
  });

  it("a shape pick keeps the role", async () => {
    updateBotMock.mockResolvedValue(makeBot());
    await renderOpen(<AvatarEditor bot={makeBot({ avatar: { shape: "pod", color: "#3b82f6", badge: "none", role: "writer" } })} onChange={vi.fn()} />);
    await userEvent.click(screen.getByRole("radio", { name: "Loaf" }));
    expect(updateBotMock).toHaveBeenCalledWith("bot-1", {
      avatar: { shape: "loaf", color: "#3b82f6", badge: "none", screen: "glow", role: "writer" } });
  });
});

describe("AvatarEditor, a colour from before the new palette", () => {
  const colourRow = () => within(screen.getByRole("group", { name: "Colour" }));

  it.each(["#10b981", "#a855f7"])("shows %s as its own checked swatch at the start of the row", async (old) => {
    await renderOpen(<AvatarEditor bot={makeBot({ avatar: { shape: "classic", color: old, badge: "none", screen: "glow" } })} onChange={vi.fn()} />);
    const swatches = colourRow().getAllByRole("radio");
    expect(swatches).toHaveLength(13);   // its own, then the twelve
    expect(swatches[0]).toHaveAccessibleName("Current colour");
    expect(swatches[0]).toBeChecked();
    expect(swatches.filter((swatch) => (swatch as HTMLInputElement).checked)).toHaveLength(1);
    expect(swatches[0].closest("label")?.style.background).not.toBe("");
  });

  it("picking a palette colour saves it, and the old colour's swatch stays in the row so it can be picked again", async () => {
    const old = makeBot({ avatar: { shape: "classic", color: "#a855f7", badge: "none", screen: "glow" } });
    updateBotMock.mockResolvedValue(makeBot({ avatar: { shape: "classic", color: "#3b82f6", badge: "none", screen: "glow" } }));
    const { rerender } = await renderOpen(<AvatarEditor bot={old} onChange={vi.fn()} />);
    await userEvent.click(colourRow().getByRole("radio", { name: "Blue" }));
    expect(updateBotMock).toHaveBeenCalledWith("bot-1", { avatar: { shape: "classic", color: "#3b82f6", badge: "none", screen: "glow" } });
    rerender(<AvatarEditor bot={makeBot({ avatar: { shape: "classic", color: "#3b82f6", badge: "none", screen: "glow" } })} onChange={vi.fn()} />);
    expect(colourRow().getByRole("radio", { name: "Blue" })).toBeChecked();
    const previous = colourRow().getByRole("radio", { name: "Previous colour" });
    expect(colourRow().getAllByRole("radio")).toHaveLength(13);
    expect(previous).not.toBeChecked();
    expect(previous.closest("label")?.style.background).not.toBe("");
    updateBotMock.mockClear();
    await userEvent.click(previous);
    expect(updateBotMock).toHaveBeenCalledWith("bot-1", { avatar: { shape: "classic", color: "#a855f7", badge: "none", screen: "glow" } });
  });

  it("an arrow-key move off the old colour leaves its swatch in the row, and an arrow key goes back to it", async () => {
    const Harness = () => {
      const [look, setLook] = useState<AvatarOut>({ shape: "classic", color: "#a855f7", badge: "none", screen: "glow" });
      return <AvatarPicker value={look} onChange={setLook} />;
    };
    render(<Harness />);
    const current = colourRow().getByRole("radio", { name: "Current colour" });
    current.focus();
    await userEvent.keyboard("{ArrowRight}");
    expect(colourRow().getAllByRole("radio")).toHaveLength(13);
    const previous = colourRow().getByRole("radio", { name: "Previous colour" });
    expect(previous).not.toBeChecked();
    expect(colourRow().getAllByRole("radio").filter((radio) => (radio as HTMLInputElement).checked)).toHaveLength(1);
    await userEvent.keyboard("{ArrowLeft}");
    expect(colourRow().getByRole("radio", { name: "Current colour" })).toBeChecked();
    expect(colourRow().queryByRole("radio", { name: "Previous colour" })).not.toBeInTheDocument();
  });

  it("adds no extra swatch for a colour in the palette, whatever its case", async () => {
    await renderOpen(<AvatarEditor bot={makeBot({ avatar: { shape: "classic", color: "#8B5CF6", badge: "none", screen: "glow" } })} onChange={vi.fn()} />);
    expect(colourRow().getAllByRole("radio")).toHaveLength(12);
    expect(colourRow().getByRole("radio", { name: "Violet" })).toBeChecked();
  });
});
