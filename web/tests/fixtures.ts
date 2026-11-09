import type { ApprovalCardOut, ApprovalStepOut, BotOut, MessageOut, StuckCardOut } from "../src/api/types";

export function makeBot(overrides: Partial<BotOut> = {}): BotOut {
  return {
    id: "bot-1",
    name: "Scout",
    job: "Finds things on the web",
    instructions: "",
    avatar: { shape: "round", color: "#10b981", badge: "none" },
    template_id: null,
    status: "resting",
    activity: null,
    model_override: null,
    model: "claude-sonnet-5-5",
    model_label: "Sonnet 5.5",
    effort: null,
    off_duty: false,
    is_primary: false,
    notify: true,
    full_limit_until: null,
    workspace_internet: false,
    computer: "mac_brave",
    approval: { mode: "ask", ask_topics: [], locked_topics: ["posting"] },
    voice: { speaker: "aiden", tone: "natural", speed: 1, read_aloud: false, correct_english: false },
    group: null,
    pinned: overrides.is_primary === true,
    pinned_at: null,
    roles: [],
    created_at: "x",
    updated_at: "x",
    ...overrides,
  };
}

export function makeMessage(overrides: Partial<MessageOut> = {}): MessageOut {
  return {
    id: "m-1",
    thread_id: "t-1",
    role: "bot",
    body: "hi",
    tainted: false,
    seq: 1,
    created_at: "x",
    kind: "text",
    author_bot_id: null,
    ...overrides,
  };
}

// What roost/stuck/texts.py stuck_line says for a sign-in page (stuck flow, Task 3).
export const STUCK_LINE = "I'm stuck on shop.example: a sign-in page. Take control to clear it, then give it back.";

export function makeStuckCard(overrides: Partial<StuckCardOut> = {}): StuckCardOut {
  return {
    id: "card-1",
    bot_id: "bot-1",
    thread_id: "t-1",
    reason: "login",
    host: "shop.example",
    url: "https://shop.example/login",
    note: "",
    suggest_main_browser: false,
    tainted: false,
    main_opened: false,
    state: "open",
    created_at: "2026-10-14T10:00:00Z",
    closed_at: null,
    ...overrides,
  };
}

// A kind "stuck" message's body, shaped like roost/stuck/texts.py stuck_message_body.
export function stuckBody(card: StuckCardOut, line = STUCK_LINE): string {
  return JSON.stringify({
    card_id: card.id, bot_id: card.bot_id, reason: card.reason, host: card.host, url: card.url,
    note: card.note, suggest_main_browser: card.suggest_main_browser, line,
  });
}

// An Ask card as roost/approvals/models.py ApprovalCardOut sends it (approval modes, Task 8).
export function makeStep(overrides: Partial<ApprovalStepOut> = {}): ApprovalStepOut {
  return {
    tool: "mac_edit", topic: "files", title: "Edit grtasks.md in MySpace", detail: "Changes 2 lines.", floor: null,
    tainted_basis: false, session_offer: false, rows: [], diff: null, ...overrides,
  };
}

export function makeApprovalCard(overrides: Partial<ApprovalCardOut> = {}): ApprovalCardOut {
  return {
    id: "card-a", bot_id: "bot-1", thread_id: "t-1", kind: "ask", state: "open", tainted: false, session_offer: false,
    created_at: "2026-10-22T10:00:00Z", closed_at: null, steps: [makeStep()], ...overrides,
  };
}
