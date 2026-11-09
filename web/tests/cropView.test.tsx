import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { CropView, buttonLabel } from "../src/components/approvals/CropView";
import { StepRow } from "../src/components/approvals/StepRow";
import { applyFrame, initialLiveState } from "../src/store/live";
import type { ServerFrame } from "../src/api/types";
import { makeApprovalCard, makeStep } from "./fixtures";

const getApprovalMock = vi.fn();
vi.mock("../src/api/approvals", () => ({ getApproval: (id: string, full: boolean) => getApprovalMock(id, full) }));
afterEach(() => { cleanup(); getApprovalMock.mockReset(); });

const CROP = "/9j/4AAQSkZJRg==";
const buyStep = makeStep({
  tool: "click", topic: "browsing", title: "Click 'Buy now'", detail: "", floor: "commit_click",
  rows: [{ label: "Site", value: "shop.test", truncated: false }] as never,
});

describe("the button's picture on an Ask card (C3)", () => {
  it("draws the crop as a JPEG named for the button", () => {
    render(<CropView crop={CROP} label="Buy now" />);
    const img = screen.getByRole("img", { name: "The button: Buy now" });
    expect(img).toHaveAttribute("src", `data:image/jpeg;base64,${CROP}`);
  });

  it("refuses a crop that is not base64", () => {
    const { container } = render(<CropView crop={'x" onerror="y'} label="Buy now" />);
    expect(container.querySelector("img")).toBeNull();
  });

  it("names the button from the card's title", () => {
    expect(buttonLabel("Click 'Buy now'")).toBe("Buy now");
    expect(buttonLabel("Press Enter")).toBe("Press Enter");
  });

  it("test_crop_shows_above_rows_with_alt", async () => {
    getApprovalMock.mockResolvedValue(makeApprovalCard({ steps: [{ ...buyStep, crop: CROP }] }));
    const { container } = render(<StepRow cardId="card-a" index={0} step={buyStep} />);
    const img = await screen.findByRole("img", { name: "The button: Buy now" });
    expect(getApprovalMock).toHaveBeenCalledWith("card-a", true);
    const rows = container.querySelector(".arg-rows, dl, table, ul.rows") ?? screen.getByText("shop.test");
    expect(img.compareDocumentPosition(rows) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("fetches nothing for a step that is not a screen act", () => {
    render(<StepRow cardId="card-a" index={0} step={makeStep()} />);
    expect(getApprovalMock).not.toHaveBeenCalled();
  });

  it("test_live_frames_never_carry_the_crop", () => {
    const card = makeApprovalCard({ steps: [{ ...buyStep, crop: CROP }] });
    const state = applyFrame(initialLiveState(), { type: "approval_card", seq: 3, card } as ServerFrame);
    expect(state.approvalCards["card-a"].steps[0].crop).toBeNull();
  });
});
