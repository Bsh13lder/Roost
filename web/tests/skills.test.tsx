import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { FOLD_STORAGE_PREFIX } from "../src/ui/Fold";
import { SettingsPage } from "../src/components/profile/SettingsPage";
import SkillsSection from "../src/components/skills/SkillsSection";
import { fieldOf } from "../src/components/skills/SkillEditor";
import { RevisionConflictError } from "../src/api/conflict";
import type { SkillOut } from "../src/api/skills";
import { makeBot } from "./fixtures";

const api = {
  listSkills: vi.fn(), addSkill: vi.fn(), saveSkill: vi.fn(), deleteSkill: vi.fn(), setSkillOn: vi.fn(),
};
vi.mock("../src/api/skills", () => ({
  listSkills: (...a: unknown[]) => api.listSkills(...a), addSkill: (...a: unknown[]) => api.addSkill(...a),
  saveSkill: (...a: unknown[]) => api.saveSkill(...a), deleteSkill: (...a: unknown[]) => api.deleteSkill(...a),
  setSkillOn: (...a: unknown[]) => api.setSkillOn(...a),
}));
vi.mock("../src/hooks/useLiveStore", () => ({ useLiveState: () => ({ skillVersion: { skills: 0, proposals: 0 } }) }));
vi.mock("../src/components/memory/MemoryPanel", () => ({ MemoryPanel: () => null }));
vi.mock("../src/components/profile/DecisionsCard", () => ({ DecisionsCard: () => null }));
vi.mock("../src/components/profile/ModelPicker", () => ({ ModelPicker: () => null }));
vi.mock("../src/components/profile/NotifySwitch", () => ({ NotifySwitch: () => null }));
vi.mock("../src/components/profile/FoldersCard", () => ({ FoldersCard: () => null }));
vi.mock("../src/components/profile/ApprovalModeCard", () => ({ ApprovalModeCard: () => null }));
vi.mock("../src/components/routines/RoutinesSection", () => ({ default: () => null }));

export function skill(overrides: Partial<SkillOut> = {}): SkillOut {
  return {
    id: "s-1", name: "Post on X", use_when: "the user wants a post on X", body: "1. Open X\n2. Write it",
    origin: "user", tainted: false, created_by_bot: null, revision: 1, created_at: "x", updated_at: "x", on: true,
    ...overrides,
  };
}

const section = () => render(<MemoryRouter><SkillsSection botId="bot-1" /></MemoryRouter>);

beforeEach(() => { api.listSkills.mockResolvedValue([skill()]); });
afterEach(() => {
  cleanup();
  Object.values(api).forEach((mock) => mock.mockReset());
  window.localStorage.clear();
});

describe("Skills fold", () => {
  it("renders the fold closed and loads the section only when opened", async () => {
    api.listSkills.mockResolvedValue([skill(), skill({ id: "s-2", name: "Weekly SEO", on: false })]);
    render(<MemoryRouter><SettingsPage bot={makeBot()} onChange={() => undefined} onShare={() => undefined} /></MemoryRouter>);
    const head = screen.getByRole("button", { name: /Skills/ });
    expect(head).toHaveAttribute("aria-expanded", "false");
    expect(await within(head).findByText("1 on")).toBeInTheDocument();
    expect(screen.queryByText("Post on X")).not.toBeInTheDocument();
    await userEvent.click(head);
    expect(await screen.findByText("Post on X")).toBeInTheDocument();
    expect(window.localStorage.getItem(`${FOLD_STORAGE_PREFIX}skills`)).toBe("1");
  });
});

describe("SkillsSection", () => {
  it("lists skills with the on switch", async () => {
    api.listSkills.mockResolvedValue([skill(), skill({ id: "s-2", name: "Weekly SEO", use_when: "weekly", on: false })]);
    section();
    expect(await screen.findByText("Post on X")).toBeInTheDocument();
    expect(screen.getByText("the user wants a post on X")).toBeInTheDocument();
    expect(screen.getByRole("switch", { name: "On for this bot: Post on X" })).toHaveAttribute("aria-checked", "true");
    expect(screen.getByRole("switch", { name: "On for this bot: Weekly SEO" })).toHaveAttribute("aria-checked", "false");
    expect(api.listSkills).toHaveBeenCalledWith("bot-1");
  });

  it("says how to start when there are none", async () => {
    api.listSkills.mockResolvedValue([]);
    section();
    expect(await screen.findByText(/No skills yet/)).toBeInTheDocument();
  });

  it("switching off calls the route", async () => {
    api.setSkillOn.mockResolvedValue({ on: false });
    section();
    await userEvent.click(await screen.findByRole("switch", { name: "On for this bot: Post on X" }));
    expect(api.setSkillOn).toHaveBeenCalledWith("bot-1", "s-1", false);
    await waitFor(() => expect(screen.getByRole("switch", { name: /Post on X/ })).toHaveAttribute("aria-checked", "false"));
  });

  it("a marked skill shows the badge", async () => {
    api.listSkills.mockResolvedValue([skill({ tainted: true, origin: "file" })]);
    section();
    expect(await screen.findByText("from web content")).toBeInTheDocument();
  });

  it("the editor saves and shows a conflict with both choices", async () => {
    const newer = skill({ body: "their steps", revision: 2 });
    api.saveSkill.mockRejectedValueOnce(new RevisionConflictError<SkillOut>(newer));
    api.saveSkill.mockResolvedValueOnce(skill({ body: "my steps", revision: 3 }));
    section();
    await userEvent.click(await screen.findByText("Post on X"));
    const steps = await screen.findByLabelText("Steps");
    await userEvent.clear(steps);
    await userEvent.type(steps, "my steps");
    await userEvent.click(screen.getByRole("button", { name: "Save skill" }));
    expect(api.saveSkill).toHaveBeenCalledWith("s-1", { name: "Post on X", use_when: "the user wants a post on X", body: "my steps" }, 1);
    expect(await screen.findByText("This skill changed since you opened it.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Load the latest" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Keep mine" }));
    await waitFor(() => expect(api.saveSkill).toHaveBeenLastCalledWith("s-1", expect.objectContaining({ body: "my steps" }), 2));
  });

  it("load the latest shows the newer copy", async () => {
    api.saveSkill.mockRejectedValueOnce(new RevisionConflictError<SkillOut>(skill({ body: "their steps", revision: 2 })));
    section();
    await userEvent.click(await screen.findByText("Post on X"));
    await userEvent.click(screen.getByRole("button", { name: "Save skill" }));
    await userEvent.click(await screen.findByRole("button", { name: "Load the latest" }));
    expect(screen.getByLabelText("Steps")).toHaveValue("their steps");
  });

  it("a new skill is added and a server sentence shows under its field", async () => {
    const { ApiError } = await import("../src/api/client");
    api.addSkill.mockRejectedValueOnce(new ApiError(422, "There is already a skill called “Post on X”."));
    section();
    await userEvent.click(await screen.findByRole("button", { name: "New skill" }));
    await userEvent.type(screen.getByLabelText("Name"), "post on x");
    await userEvent.click(screen.getByRole("button", { name: "Save skill" }));
    expect(await screen.findByText("There is already a skill called “Post on X”.")).toBeInTheDocument();
    expect(fieldOf("Not saved: an API key or token seems to be in the steps. Remove it, then save again.")).toBe("body");
    expect(fieldOf("Use when must be 1 to 200 characters on one line.")).toBe("use_when");
    expect(fieldOf("Something else")).toBe("form");
  });

  it("delete asks first", async () => {
    api.deleteSkill.mockResolvedValue(undefined);
    section();
    await userEvent.click(await screen.findByText("Post on X"));
    await userEvent.click(screen.getByRole("button", { name: "Delete" }));
    expect(api.deleteSkill).not.toHaveBeenCalled();
    expect(screen.getByText("Delete this skill for every bot?")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Yes, delete it" }));
    expect(api.deleteSkill).toHaveBeenCalledWith("s-1");
    await waitFor(() => expect(screen.queryByText("Post on X")).not.toBeInTheDocument());
  });
});
