import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import SkillAskCard from "../src/components/skills/SkillAskCard";
import { ApiError } from "../src/api/client";
import type { SkillProposalOut } from "../src/api/skills";

const api = { getSkillProposal: vi.fn(), saveSkillProposal: vi.fn(), declineSkillProposal: vi.fn() };
vi.mock("../src/api/skills", () => ({
  getSkillProposal: (...a: unknown[]) => api.getSkillProposal(...a),
  saveSkillProposal: (...a: unknown[]) => api.saveSkillProposal(...a),
  declineSkillProposal: (...a: unknown[]) => api.declineSkillProposal(...a),
}));
vi.mock("../src/hooks/useLiveStore", () => ({ useLiveState: () => ({ skillVersion: { skills: 0, proposals: 0 } }) }));
// The markdown chunk is not under test here: the steps show as their text.
vi.mock("../src/components/chat/RichText", () => ({ RichText: ({ text }: { text: string }) => <div>{text}</div> }));

const LONG = Array.from({ length: 60 }, (_, i) => `${i + 1}. step number ${i + 1}`).join("\n");

function proposal(overrides: Partial<SkillProposalOut> = {}): SkillProposalOut {
  return { id: "sp-1", bot_id: "bot-1", skill_id: null, action: "create",
    payload: { name: "Post on X", use_when: "the user wants a post on X", body: LONG }, skill_name: "Post on X",
    diff: [], tainted: false, from_routine: false, state: "open", created_at: "x", ...overrides };
}

afterEach(() => { cleanup(); Object.values(api).forEach((mock) => mock.mockReset()); });

describe("SkillAskCard", () => {
  it("the card shows the full steps and saves", async () => {
    api.getSkillProposal.mockResolvedValue(proposal());
    api.saveSkillProposal.mockResolvedValue(proposal({ state: "saved" }));
    render(<SkillAskCard proposalId="sp-1" />);
    expect(await screen.findByText("Post on X")).toBeInTheDocument();
    expect(screen.getByText(/the user wants a post on X/)).toBeInTheDocument();
    expect(screen.getByText(/60\. step number 60/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Save skill" }));
    expect(api.saveSkillProposal).toHaveBeenCalledWith("sp-1");
    expect(await screen.findByText("Saved")).toBeInTheDocument();
  });

  it("Not now declines", async () => {
    api.getSkillProposal.mockResolvedValue(proposal());
    api.declineSkillProposal.mockResolvedValue(proposal({ state: "declined" }));
    render(<SkillAskCard proposalId="sp-1" />);
    await userEvent.click(await screen.findByRole("button", { name: "Not now" }));
    expect(await screen.findByText("Not saved")).toBeInTheDocument();
  });

  it("a change card shows before and after", async () => {
    api.getSkillProposal.mockResolvedValue(proposal({ action: "change", skill_id: "s-1", skill_name: "Weekly SEO",
      payload: { name: null, use_when: null, body: "new steps" },
      diff: [{ field: "body", before: "old steps", after: "new steps" }] }));
    render(<SkillAskCard proposalId="sp-1" />);
    expect(await screen.findByText("Weekly SEO")).toBeInTheDocument();
    expect(screen.getByText("Steps")).toBeInTheDocument();
    expect(screen.getByLabelText("Before")).toHaveTextContent("old steps");
    expect(screen.getByLabelText("After")).toHaveTextContent("new steps");
  });

  it("a marked proposal shows the badge", async () => {
    api.getSkillProposal.mockResolvedValue(proposal({ tainted: true, from_routine: true }));
    render(<SkillAskCard proposalId="sp-1" />);
    expect(await screen.findByText("from web content")).toBeInTheDocument();
    expect(screen.getByText("A routine proposed this")).toBeInTheDocument();
  });

  it("a 409 reloads the card and a 422 shows its sentence", async () => {
    api.getSkillProposal.mockResolvedValueOnce(proposal()).mockResolvedValueOnce(proposal({ state: "saved" }));
    api.saveSkillProposal.mockRejectedValueOnce(new ApiError(409, "Try again: that proposal was already decided."));
    render(<SkillAskCard proposalId="sp-1" />);
    await userEvent.click(await screen.findByRole("button", { name: "Save skill" }));
    expect(await screen.findByText("Saved")).toBeInTheDocument();
    expect(api.getSkillProposal).toHaveBeenCalledTimes(2);

    cleanup();
    api.getSkillProposal.mockResolvedValue(proposal());
    api.saveSkillProposal.mockRejectedValueOnce(new ApiError(422, "That skill changed or is gone, so this proposal no longer fits."));
    render(<SkillAskCard proposalId="sp-1" />);
    await userEvent.click(await screen.findByRole("button", { name: "Save skill" }));
    expect(await screen.findByText(/no longer fits/)).toBeInTheDocument();
  });

  it("a proposal that is gone says so", async () => {
    api.getSkillProposal.mockRejectedValue(new ApiError(404, "Skill proposal not found"));
    render(<SkillAskCard proposalId="sp-1" />);
    await waitFor(() => expect(screen.getByText("This proposal is gone.")).toBeInTheDocument());
  });
});
