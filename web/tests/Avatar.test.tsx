import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render, screen } from "@testing-library/react";
import { Avatar } from "../src/components/Avatar";
import { StatusLabel } from "../src/components/StatusLabel";
import { AVATAR_SHAPES, LENSBOT_SHAPES } from "../src/components/robot/look";
import { publishRobotEvents, resetRobotEventsForTests, setThinkingBots } from "../src/hooks/useRobotEvents";
import { resetLookAtForTests } from "../src/components/robot/lookAt";
import type { AvatarOut, BotStatus } from "../src/api/types";
import { installObserverStub, type ObserverStub } from "./lookAtStub";

let observer: ObserverStub;
beforeEach(() => { resetLookAtForTests(); observer = installObserverStub(); resetRobotEventsForTests(); });
afterEach(() => { cleanup(); observer.restore(); vi.useRealTimers(); mockReducedMotion(false); });

const AVATAR: AvatarOut = { shape: "classic", color: "#8b5cf6", badge: "none", screen: "pixel" };

const STATUSES: Array<[BotStatus, string, string, string]> = [
  ["resting", "Resting", "rest", "open"],
  ["on_it", "On it", "onit", "open"],
  ["asking_you", "Asking you", "ask", "wide"],
  ["stuck", "Stuck", "stuck", "sad"],
  ["off_duty", "Off duty", "off", "closed"],
];

function mockReducedMotion(reduce: boolean) {
  window.matchMedia = ((query: string) => ({
    matches: reduce && query.includes("prefers-reduced-motion"),
    media: query,
    addEventListener: () => {},
    removeEventListener: () => {},
  })) as unknown as typeof window.matchMedia;
}

describe("Avatar", () => {
  it.each(STATUSES)("shows %s in the robot's eyes and posture, and in words", (status, label, moment, face) => {
    render(<Avatar avatar={AVATAR} status={status} />);
    const svg = document.querySelector("svg.avatar");
    expect(svg).toHaveClass(`avatar--${status}`);
    expect(svg?.getAttribute("data-moment")).toBe(moment);
    expect(svg?.getAttribute("data-face")).toBe(face);
    expect(svg?.getAttribute("data-screen")).toBeNull(); // a Lensbot has no screen
    expect(screen.getByText(label)).toBeInTheDocument();
  });

  it("draws every stored shape, old ghosts, heads and birds included, as one of the eighteen Lensbots", () => {
    for (const shape of AVATAR_SHAPES) {
      const { container, unmount } = render(<Avatar avatar={{ ...AVATAR, shape }} status="resting" />);
      const drawn = container.querySelector("svg.avatar")?.getAttribute("data-shape");
      expect(LENSBOT_SHAPES, shape).toContain(drawn);
      expect(container.querySelectorAll(".robot__eye"), shape).toHaveLength(2);
      unmount();
    }
    const { container } = render(<Avatar avatar={{ ...AVATAR, shape: "egg" }} status="resting" />);
    expect(container.querySelector("svg.avatar")?.getAttribute("data-shape")).toBe("cub");
  });

  it("wears its role's emblem, and an old avatar with no role wears none", () => {
    const { container, rerender } = render(<Avatar avatar={{ ...AVATAR, role: "money" }} status="resting" size={64} />);
    expect(container.querySelector(".robot__emblem--money")).not.toBeNull();
    rerender(<Avatar avatar={AVATAR} status="resting" size={64} />);
    expect(container.querySelector(".robot__emblem")).toBeNull();
    rerender(<Avatar avatar={{ ...AVATAR, role: "money" }} status="resting" size={24} />);
    expect(container.querySelector(".robot__emblem")).toBeNull();
  });

  it.each(STATUSES)("a bot with a picture still shows %s, in its posture and its name", (status, label, moment) => {
    render(<Avatar avatar={{ ...AVATAR, picture: "/api/bots/b1/picture?v=0123456789ab" }} status={status} />);
    const svg = document.querySelector("svg.avatar");
    expect(svg?.querySelector("image.robot__picture")).not.toBeNull();
    expect(svg?.getAttribute("data-moment")).toBe(moment);
    expect(svg?.querySelectorAll(".robot__eye")).toHaveLength(0);
    expect(screen.getByText(label)).toBeInTheDocument();
    expect(screen.getByRole("img", { name: label })).toBeInTheDocument();
  });

  it("shows a moment in place of its status when asked", () => {
    render(<Avatar avatar={AVATAR} status="on_it" moment="off" />);
    expect(document.querySelector("svg.avatar")?.getAttribute("data-moment")).toBe("off");
  });

  it("renders the live activity line when present", () => {
    render(<Avatar avatar={AVATAR} status="on_it" activity="opening a page" />);
    expect(screen.getByText("opening a page")).toBeInTheDocument();
  });

  it("moves when the OS has no preference, and is still when it asks for reduced motion", () => {
    mockReducedMotion(false);
    const { unmount } = render(<Avatar avatar={AVATAR} status="on_it" />);
    expect(document.querySelector("svg.avatar")).not.toHaveClass("avatar--reduced-motion");
    expect(document.querySelector("svg.avatar")).not.toHaveClass("robot--still");
    expect(observer.observed).toHaveLength(1);
    unmount();
    mockReducedMotion(true);
    render(<Avatar avatar={AVATAR} status="on_it" />);
    expect(document.querySelector("svg.avatar")).toHaveClass("avatar--reduced-motion", "robot--still");
    expect(observer.observed).toHaveLength(0);
  });

  it("plays its bot's live events and thinks while its bot's run has no text yet", () => {
    vi.useFakeTimers();
    render(<Avatar avatar={AVATAR} status="on_it" botId="scout" size={64} label={false} />);
    const svg = document.querySelector("svg.avatar");
    act(() => publishRobotEvents([{ botId: "scout", name: "created" }, { botId: "other", name: "done" }]));
    expect(svg).toHaveClass("robot--ev-created");
    expect(svg).not.toHaveClass("robot--ev-done");
    act(() => setThinkingBots(new Set(["scout"])));
    expect(svg).toHaveClass("robot--ev-think");
    act(() => setThinkingBots(new Set()));
    expect(svg).not.toHaveClass("robot--ev-think");
  });

  it("leaves out the words when label={false} but keeps the status as the image's name", () => {
    render(<Avatar avatar={AVATAR} status="stuck" label={false} />);
    expect(screen.queryByText("Stuck")).toBeNull();
    expect(screen.getByRole("img", { name: "Stuck" })).toBeInTheDocument();
  });

  it("only the main bot wears the star", () => {
    const { container, rerender } = render(<Avatar avatar={AVATAR} status="resting" />);
    expect(container.querySelector(".robot__star")).toBeNull();
    rerender(<Avatar avatar={AVATAR} status="resting" star />);
    expect(container.querySelector(".robot__star")).not.toBeNull();
  });

  it("is hidden from assistive tech when decorative", () => {
    render(<Avatar avatar={AVATAR} status="resting" label={false} decorative />);
    expect(document.querySelector("svg.avatar")?.getAttribute("aria-hidden")).toBe("true");
    expect(screen.queryByRole("img")).toBeNull();
  });
});

describe("StatusLabel", () => {
  it.each(STATUSES)("tags the %s label with its status so the dot can take the status color", (status, label) => {
    render(<StatusLabel status={status} />);
    const wrapper = screen.getByText(label).closest(".status-label");
    expect(wrapper).toHaveClass(`status-label--${status}`);
    expect(wrapper?.querySelector(".status-label__dot")).not.toBeNull();
  });
});
