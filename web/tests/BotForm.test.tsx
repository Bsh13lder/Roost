import { describe, expect, it, vi, afterEach } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { BotForm, newBotValues } from "../src/components/BotForm";

afterEach(() => cleanup());

describe("BotForm", () => {
  it("has Name, Job, Instructions and the look picker, and no roles, badge or main-bot box", () => {
    render(<BotForm submitLabel="Create bot" onSubmit={vi.fn()} />);
    expect(screen.getByLabelText("Name")).toBeInTheDocument();
    expect(screen.getByLabelText("Job")).toBeInTheDocument();
    expect(screen.getByLabelText("Instructions")).toBeInTheDocument();
    expect(screen.getAllByRole("radio", {
      name: /^(Mochi|Loaf|Gumdrop|Pebble|Bun|Acorn|Marshmallow|Dumpling|Muffs|Squish|Cub|Sprout|Cheeky|Tower|Helmet|Bell|Puck|Pod)$/,
    })).toHaveLength(18);
    expect(screen.getByRole("radio", { name: "White" })).toBeInTheDocument();
    expect(screen.queryByRole("radio", { name: "Finance" })).not.toBeInTheDocument();
    expect(screen.queryByRole("checkbox", { name: /Main bot/ })).not.toBeInTheDocument();
    expect(screen.queryByText(/Roles/)).not.toBeInTheDocument();
  });

  it("updates the live preview when a shape is chosen", async () => {
    const user = userEvent.setup();
    render(<BotForm submitLabel="Create bot" onSubmit={vi.fn()} />);
    expect(screen.getByRole("radio", { name: "Mochi" })).toBeChecked();
    await user.click(screen.getByRole("radio", { name: "Bell" }));
    expect(screen.getByRole("radio", { name: "Bell" })).toBeChecked();
    expect(screen.getByRole("radio", { name: "Mochi" })).not.toBeChecked();
    expect(document.querySelector(".bot-form__preview svg.avatar")?.getAttribute("data-shape")).toBe("bell");
  });

  it("Surprise me changes the shape and the colour, and a new bot has no Upload yet", async () => {
    const user = userEvent.setup();
    render(<BotForm submitLabel="Create bot" onSubmit={vi.fn()} />);
    await user.click(screen.getByRole("button", { name: "Surprise me" }));
    expect(screen.getByRole("radio", { name: "Mochi" })).not.toBeChecked();
    expect(screen.getByRole("radio", { name: "Violet" })).not.toBeChecked();
    expect(screen.queryByLabelText("Upload a picture")).not.toBeInTheDocument();
  });

  it("a new bot wears the first colour no teammate wears", () => {
    expect(newBotValues([]).avatar).toEqual({ shape: "mochi", color: "#8b5cf6", badge: "none" });
    expect(newBotValues(["#8b5cf6", "#3b82f6"]).avatar.color).toBe("#14b8a6");
  });

  it("shows the typed name under the preview", async () => {
    const user = userEvent.setup();
    render(<BotForm submitLabel="Create bot" onSubmit={vi.fn()} />);
    expect(screen.getByText("Your new bot")).toBeInTheDocument();
    await user.type(screen.getByLabelText("Name"), "Quill");
    expect(screen.getByText("Quill", { selector: ".bot-form__preview-name" })).toBeInTheDocument();
  });

  it("submits name, job, instructions, look and template, with no badge", async () => {
    const onSubmit = vi.fn();
    const user = userEvent.setup();
    render(<BotForm submitLabel="Create bot" onSubmit={onSubmit} />);
    await user.type(screen.getByLabelText("Name"), "Quill");
    await user.type(screen.getByLabelText("Job"), "Drafts notes");
    await user.click(screen.getByRole("radio", { name: "Squish" }));
    await user.click(screen.getByRole("radio", { name: "Orange" }));
    await user.click(screen.getByRole("button", { name: "Create bot" }));
    expect(onSubmit).toHaveBeenCalledWith({
      name: "Quill",
      job: "Drafts notes",
      instructions: "",
      avatar: { shape: "squish", color: "#f97316", badge: "none" },
      template_id: null,
    });
  });

  it("refuses a name that breaks the rules without submitting", async () => {
    const onSubmit = vi.fn();
    const user = userEvent.setup();
    render(<BotForm submitLabel="Create bot" onSubmit={onSubmit} />);
    await user.type(screen.getByLabelText("Name"), " bad");
    await user.type(screen.getByLabelText("Job"), "Drafts notes");
    await user.click(screen.getByRole("button", { name: "Create bot" }));
    expect(screen.getByText("Use letters, numbers, spaces, . or - (up to 40).")).toBeInTheDocument();
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("counts instructions near the limit and never submits an over-limit draft", async () => {
    const onSubmit = vi.fn();
    const user = userEvent.setup();
    render(<BotForm submitLabel="Create bot" onSubmit={onSubmit}
      initial={{ name: "Quill", job: "Drafts notes", instructions: "", template_id: null,
        avatar: { shape: "round", color: "#10b981", badge: "none" } }} />);
    await user.click(screen.getByLabelText("Instructions"));
    await user.paste("x".repeat(4002));
    expect(screen.getByText("2 characters over the limit — shorten it to save.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Create bot" }));
    expect(onSubmit).not.toHaveBeenCalled();
  });
});
