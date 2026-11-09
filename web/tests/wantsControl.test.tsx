import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render } from "@testing-library/react";
import { wantsControl } from "../src/lib/wantsControl";
import { RobotFace } from "../src/components/robot/RobotFace";
import { makeBot, makeStuckCard } from "./fixtures";

afterEach(cleanup);

describe("the hand on a bot's face (C3)", () => {
  it("test_wants_control_follows_open_stuck_cards", () => {
    const bot = makeBot({ id: "bot-1", status: "stuck" });
    const open = makeStuckCard({ id: "s-1", bot_id: "bot-1", state: "open" });
    expect(wantsControl(bot, [open])).toBe(true);
    expect(wantsControl(bot, { "s-1": open })).toBe(true);
    expect(wantsControl(bot, [{ ...open, state: "cleared" }])).toBe(false);
    expect(wantsControl(bot, [{ ...open, bot_id: "bot-2" }])).toBe(false);
    expect(wantsControl(bot, [])).toBe(false);
  });

  it("test_ctrl_glyph_is_a_hand", () => {
    const { container } = render(<RobotFace shape="mochi" color="#3b82f6" size={64} moment="stuck" control />);
    expect(container.querySelector("svg.robot")?.getAttribute("data-g")).toBe("ctrl");
    expect(container.querySelector(".robot__g--hand")).not.toBeNull();
    expect(container.querySelector(".robot__g--cur")).toBeNull();
  });
});
