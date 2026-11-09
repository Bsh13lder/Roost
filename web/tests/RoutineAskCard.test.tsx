import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { RoutineAskCard } from "../src/components/chat/RoutineAskCard";
import { ApiError } from "../src/api/client";
import type { ProposalOut } from "../src/api/proposals";

const api = { listProposals: vi.fn(), approveProposal: vi.fn(), declineProposal: vi.fn() };
vi.mock("../src/api/proposals", () => ({
  listProposals: (...a: unknown[]) => api.listProposals(...a), approveProposal: (...a: unknown[]) => api.approveProposal(...a),
  declineProposal: (...a: unknown[]) => api.declineProposal(...a),
}));
vi.mock("../src/hooks/useLiveStore", () => ({ useLiveState: () => ({ routineVersion: { proposals: 0 } }) }));

const proposal = (over: Partial<ProposalOut> = {}): ProposalOut => ({
  id: "p-1", bot_id: "bot-1", action: "create", routine_id: null, routine_name: null, state: "open",
  payload: { name: "Morning digest", instructions: "Read the news.", schedule: { kind: "times", days: [1], times: ["10:07"] } },
  words: "Mondays at 10:07", next: ["2026-10-26T10:07:00+01:00", "2026-11-02T10:07:00+01:00", "2026-11-09T10:07:00+01:00", "2026-11-16T10:07:00+01:00"],
  diff: [], tainted: false, from_routine: false, created_at: "2026-10-21T08:00:00Z", ...over,
});

beforeEach(() => { api.listProposals.mockResolvedValue([proposal()]); });
afterEach(() => { cleanup(); Object.values(api).forEach((mock) => mock.mockReset()); });

describe("RoutineAskCard", () => {
  it("shows every field of a new routine: name, words, the next three times and the instructions", async () => {
    render(<RoutineAskCard proposalId="p-1" />);
    expect(await screen.findByText("Morning digest")).toBeInTheDocument();
    expect(screen.getByText("Mondays at 10:07")).toBeInTheDocument();
    expect(screen.getByText("Mon 26 Oct 10:07")).toBeInTheDocument();
    expect(screen.getByText("Mon 9 Nov 10:07")).toBeInTheDocument();
    expect(screen.queryByText("Mon 16 Nov 10:07")).not.toBeInTheDocument();
    expect(screen.getByText("Read the news.")).toBeInTheDocument();
  });

  it("a change card shows before and after", async () => {
    api.listProposals.mockResolvedValue([proposal({
      action: "change", routine_id: "r-1", routine_name: "Morning digest",
      diff: [{ field: "schedule", before: "Mondays at 10:07", after: "Daily at 08:00" }],
    })]);
    render(<RoutineAskCard proposalId="p-1" />);
    expect(await screen.findByText("Mondays at 10:07")).toBeInTheDocument();
    expect(screen.getByText("Daily at 08:00")).toBeInTheDocument();
    expect(screen.getByText("Schedule")).toBeInTheDocument();
  });

  it("a change card names a new page watch", async () => {
    api.listProposals.mockResolvedValue([proposal({
      action: "change", routine_id: "r-1", routine_name: "Physio",
      diff: [{ field: "watch", before: "Runs on its schedule", after: "Only when https://web.whatsapp.com/ changes (the physio chat), checked every 5 min" }],
    })]);
    render(<RoutineAskCard proposalId="p-1" />);
    expect(await screen.findByText("Runs when")).toBeInTheDocument();
    expect(screen.getByText("Runs on its schedule")).toBeInTheDocument();
  });

  it("wears the marks for outside content and for a routine asking", async () => {
    api.listProposals.mockResolvedValue([proposal({ tainted: true, from_routine: true })]);
    render(<RoutineAskCard proposalId="p-1" />);
    expect(await screen.findByText("This run read outside content.")).toBeInTheDocument();
    expect(screen.getByText("A routine asked to change a routine.")).toBeInTheDocument();
  });

  it("approve and decline call the routes and the card settles", async () => {
    api.approveProposal.mockResolvedValue(proposal({ state: "approved" }));
    render(<RoutineAskCard proposalId="p-1" />);
    await userEvent.click(await screen.findByRole("button", { name: "Approve" }));
    expect(api.approveProposal).toHaveBeenCalledWith("p-1");
    expect(await screen.findByText("Approved")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();
    cleanup();
    api.declineProposal.mockResolvedValue(proposal({ state: "declined" }));
    render(<RoutineAskCard proposalId="p-1" />);
    await userEvent.click(await screen.findByRole("button", { name: "Decline" }));
    expect(api.declineProposal).toHaveBeenCalledWith("p-1");
    expect(await screen.findByText("Declined")).toBeInTheDocument();
  });

  it("says the server's sentence when another press already decided it", async () => {
    api.approveProposal.mockRejectedValue(new ApiError(409, "Try again: that proposal was already decided."));
    render(<RoutineAskCard proposalId="p-1" />);
    await userEvent.click(await screen.findByRole("button", { name: "Approve" }));
    expect(await screen.findByText("Try again: that proposal was already decided.")).toBeInTheDocument();
  });

  it("a proposal that is no longer open shows as decided, with no buttons", async () => {
    api.listProposals.mockResolvedValue([]);
    render(<RoutineAskCard proposalId="p-1" />);
    await waitFor(() => expect(screen.getByText("Already decided")).toBeInTheDocument());
    expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();
  });

  it("a proposed standing permission shows in words and Approve keeps it unless switched off", async () => {
    const permission = { host: "x.com", action: "post" as const, max_per_day: 1, until: "2026-11-01" };
    const base = proposal();
    api.listProposals.mockResolvedValue([proposal({ payload: { ...base.payload!, permission } })]);
    api.approveProposal.mockResolvedValue(proposal({ state: "approved" }));
    render(<RoutineAskCard proposalId="p-1" />);
    const toggle = await screen.findByRole("switch", { name: /Let it post on x.com up to 1 a day until Sun 1 Nov/ });
    expect(toggle).toHaveAttribute("aria-checked", "true");
    await userEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-checked", "false");
    await userEvent.click(screen.getByRole("button", { name: "Approve" }));
    await waitFor(() => expect(api.approveProposal).toHaveBeenCalledWith("p-1", { permission: null }));
  });
});
