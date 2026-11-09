import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import InstructionsAskCard from "../src/components/chat/InstructionsAskCard";
import { ApiError } from "../src/api/client";
import type { InstructionProposalOut } from "../src/api/instructions";

const api = { getInstructionProposal: vi.fn(), acceptInstructionProposal: vi.fn(), declineInstructionProposal: vi.fn() };
vi.mock("../src/api/instructions", () => ({
  getInstructionProposal: (...a: unknown[]) => api.getInstructionProposal(...a),
  acceptInstructionProposal: (...a: unknown[]) => api.acceptInstructionProposal(...a),
  declineInstructionProposal: (...a: unknown[]) => api.declineInstructionProposal(...a),
}));
vi.mock("../src/hooks/useLiveStore", () => ({ useLiveState: () => ({ instructionVersion: 0 }) }));

function proposal(overrides: Partial<InstructionProposalOut> = {}): InstructionProposalOut {
  return { id: "ip-1", bot_id: "b", before: "Old.", after: "## What you do\n\nNew.", why: "You asked for it.",
    diff: [{ op: "del", text: "Old." }, { op: "add", text: "New." }], stale: false, tainted: false,
    from_routine: false, state: "open", created_at: "x", decided_at: null, ...overrides };
}

afterEach(() => { cleanup(); Object.values(api).forEach((mock) => mock.mockReset()); });

describe("InstructionsAskCard", () => {
  it("shows why and the changed lines, and Accept writes them", async () => {
    api.getInstructionProposal.mockResolvedValue(proposal());
    api.acceptInstructionProposal.mockResolvedValue(proposal({ state: "accepted" }));
    render(<InstructionsAskCard proposalId="ip-1" />);
    expect(await screen.findByText("You asked for it.")).toBeInTheDocument();
    expect(screen.getByLabelText("Removed")).toHaveTextContent("Old.");
    expect(screen.getByLabelText("Added")).toHaveTextContent("New.");
    await userEvent.click(screen.getByRole("button", { name: "Accept" }));
    expect(api.acceptInstructionProposal).toHaveBeenCalledWith("ip-1", undefined);
    expect(await screen.findByText("Instructions updated")).toBeInTheDocument();
  });

  it("Edit sends your own version", async () => {
    api.getInstructionProposal.mockResolvedValue(proposal());
    api.acceptInstructionProposal.mockResolvedValue(proposal({ state: "accepted" }));
    render(<InstructionsAskCard proposalId="ip-1" />);
    await userEvent.click(await screen.findByRole("button", { name: "Edit" }));
    const box = screen.getByLabelText("Your version");
    await userEvent.clear(box);
    await userEvent.type(box, "Mine.");
    await userEvent.click(screen.getByRole("button", { name: "Accept" }));
    expect(api.acceptInstructionProposal).toHaveBeenCalledWith("ip-1", "Mine.");
  });

  it("Decline keeps them, and marks and staleness show", async () => {
    api.getInstructionProposal.mockResolvedValue(proposal({ tainted: true, stale: true }));
    api.declineInstructionProposal.mockResolvedValue(proposal({ state: "declined" }));
    render(<InstructionsAskCard proposalId="ip-1" />);
    expect(await screen.findByText("from web content")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Accept" })).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: "Decline" }));
    expect(await screen.findByText("Instructions kept")).toBeInTheDocument();
  });

  it("a card that is gone says so", async () => {
    api.getInstructionProposal.mockRejectedValue(new ApiError(404, "Instructions card not found"));
    render(<InstructionsAskCard proposalId="ip-1" />);
    expect(await screen.findByText("This card is gone.")).toBeInTheDocument();
  });
});
