// Live WS store for `/api/events` (contract: server->client frames
// snapshot/bot_status/message/text_delta/message_done/bot_removed/bot_updated,
// the Board's tasks_changed/money_changed/notes_changed/documents_changed,
// and the Stuck cards' stuck_card; client->server `resume`). Two parts, deliberately split:
//
//   - `applyFrame` is a pure reducer (old state in, new state out, never
//     mutated — see the immutability rule) so it's testable with plain
//     objects and no WebSocket at all.
//   - `LiveStore` is the stateful shell: owns the socket, replays
//     `applyFrame` over incoming frames, and reconnects with backoff,
//     resuming from the last cursor it saw so a drop never re-fetches
//     events the UI already applied.
//
// The socket is created through an injected factory (`WebSocketFactory`)
// rather than `new WebSocket(...)` directly, so tests can hand it a fake
// socket and drive `onopen`/`onmessage`/`onclose` by hand instead of
// standing up a real server.

import type {
  ApprovalCardOut, BotOut, BotStatusFrame, ComputerPointerFrame, MessageDoneFrame, MessageOut, ServerFrame, StuckCardOut,
} from "../api/types";
import { withComputerStep, withSnapshotSteps, type ComputerRuns } from "./computerRuns";
import { withRunStep, withSnapshotRunSteps, type ActivityRuns } from "./activityRuns";

// C3: where a bot last acted on its computer (screen pixels, no text). `n` counts the bot's pointers, so the ring
// shows once per new one.
export interface PointerMark {
  readonly x: number;
  readonly y: number;
  readonly kind: ComputerPointerFrame["kind"];
  readonly n: number;
}

export interface LiveState {
  readonly cursor: number;
  readonly bots: Readonly<Record<string, BotOut>>;
  readonly messagesByThread: Readonly<Record<string, readonly MessageOut[]>>;
  // Accumulated text_delta chunks, keyed by message_id, cleared once the
  // matching message_done frame arrives and the text is folded into
  // messagesByThread.
  readonly streaming: Readonly<Record<string, string>>;
  // Bumped by tasks_changed / money_changed / notes_changed / documents_changed: the Board reloads on a change.
  readonly boardVersion: Readonly<{ tasks: number; money: number; notes: number; documents: number; memories: number; dayNotes: number }>;
  // Bumped by routines_changed / questions_changed / proposals_changed (routines plan): Info's cards and My turn reload.
  readonly routineVersion: Readonly<{ routines: number; questions: number; proposals: number }>;
  // The newest Plan revision each bot has announced (plan_changed), keyed by bot id: the Plan tab reloads when it is newer.
  readonly planRevisions: Readonly<Record<string, number>>;
  // Bumped by skills_changed / skill_proposals_changed (Skills): the Skills fold, the card and My turn reload.
  readonly skillVersion: Readonly<{ skills: number; proposals: number }>;
  // Bumped by instruction_proposals_changed (replies track): an "Update my instructions?" card reloads.
  readonly instructionVersion: number;
  // Bumped by connector_requests_changed (Connectors): the Add a key cards, the fold and My turn reload.
  readonly connectorVersion: number;
  // Each Stuck card as its latest stuck_card frame left it, keyed by card id, open or closed:
  // the chat folds a card that is no longer open, and Home's My turn lists the open ones.
  readonly stuckCards: Readonly<Record<string, StuckCardOut>>;
  // Each Ask or Proposal card as its latest approval_card frame left it, keyed by card id, open or closed.
  readonly approvalCards: Readonly<Record<string, ApprovalCardOut>>;
  // What each reply's bot did while writing it (redesign P2): the bot_status activities ("adding a task")
  // seen while the reply's placeholder was open, oldest first, keyed by the reply's message id. Live
  // only: a reload starts empty, and P4's stored record cards take over.
  readonly toolLines: Readonly<Record<string, readonly string[]>>;
  // C3: each bot's newest computer_pointer, keyed by bot id (the live screen's ring).
  readonly pointers: Readonly<Record<string, PointerMark>>;
  // The computer card: each run's screen steps, by run id (store/computerRuns.ts). Live only.
  readonly computerRuns: ComputerRuns;
  // The activity pill: each run's steps in plain words, by run id (store/activityRuns.ts). Live only.
  readonly activityRuns: ActivityRuns;
  // Call mode (contract B): how many parts of a reply's speech can be heard, keyed by the reply's message id.
  readonly speechReady: Readonly<Record<string, SpeechReady>>;
}

export interface SpeechReady {
  readonly parts: number;
  readonly done: boolean;
}

export function initialLiveState(): LiveState {
  return {
    cursor: 0, bots: {}, messagesByThread: {}, streaming: {},
    boardVersion: { tasks: 0, money: 0, notes: 0, documents: 0, memories: 0, dayNotes: 0 },
    routineVersion: { routines: 0, questions: 0, proposals: 0 }, planRevisions: {}, skillVersion: { skills: 0, proposals: 0 }, instructionVersion: 0, connectorVersion: 0, stuckCards: {}, approvalCards: {}, toolLines: {},
    pointers: {}, computerRuns: {}, activityRuns: {}, speechReady: {},
  };
}

function withoutKey<T>(record: Readonly<Record<string, T>>, key: string): Record<string, T> {
  const next = { ...record };
  delete next[key];
  return next;
}

// The thread's messages once `frame` closes a reply. The server stores
// every reply that has text, a cut-short one too (Stop, the wall-time
// cap, an error), and sends it as a `message` frame with its real
// per-thread seq BEFORE this frame, so by now it has replaced the
// placeholder and nothing changes. A placeholder still here means the
// server kept nothing (nothing streamed, or storing failed): drop it, as a
// reload would. Fix round 2: never give a message `frame.seq` here — that
// is the hub's per-user event cursor, not a position in this thread.
function closeMessage(state: LiveState, frame: MessageDoneFrame): readonly MessageOut[] {
  const existing = state.messagesByThread[frame.thread_id] ?? [];
  const stored = existing.find((message) => message.id === frame.message_id);
  if (!stored || stored.seq !== 0) return existing;
  return existing.filter((message) => message.id !== frame.message_id);
}

// A working bot's new activity joins the trail of the reply it is writing: its open placeholder (seq 0),
// whatever the thread. The same activity twice in a row is one line.
function withToolLine(state: LiveState, frame: BotStatusFrame): LiveState["toolLines"] {
  const activity = frame.activity;
  if (frame.status !== "on_it" || !activity) return state.toolLines;
  const open = Object.values(state.messagesByThread).flat()
    .filter((message) => message.seq === 0 && message.role === "bot" && message.author_bot_id === frame.bot_id);
  return open.reduce((lines, message) => {
    const trail = lines[message.id] ?? [];
    return trail.at(-1) === activity ? lines : { ...lines, [message.id]: [...trail, activity] };
  }, state.toolLines);
}

// The bot's newest pointer, or null when it has not acted on its computer since this page opened.
export function pointerFor(state: LiveState, botId: string): PointerMark | null {
  return state.pointers[botId] ?? null;
}

function withPointer(state: LiveState, frame: ComputerPointerFrame): LiveState["pointers"] {
  const n = (state.pointers[frame.bot_id]?.n ?? 0) + 1;
  return { ...state.pointers, [frame.bot_id]: { x: frame.x, y: frame.y, kind: frame.kind, n } };
}

// A live card never holds the button's picture: only GET /api/approvals/{id}?full=1 serves it (the server already
// sends null; this keeps it so whatever arrives).
function withoutCrops(card: ApprovalCardOut): ApprovalCardOut {
  return { ...card, steps: card.steps.map((step) => ({ ...step, crop: null })) };
}

type BoardVersion = LiveState["boardVersion"];
type MoneyChange = Extract<ServerFrame, { type: "money_changed" }>["change"];

// money_changed reloads the money (H10). A deleted project also unlinks its tasks, notes and
// documents in one go (H9), with no frame of their own, so those tabs reload too.
export function bumpMoney(version: BoardVersion, change: MoneyChange): BoardVersion {
  const money = { ...version, money: version.money + 1 };
  if (change !== "project_deleted") return money;
  return { ...money, tasks: version.tasks + 1, notes: version.notes + 1, documents: version.documents + 1 };
}

export function applyFrame(state: LiveState, frame: ServerFrame): LiveState {
  switch (frame.type) {
    case "snapshot": {
      const bots: Record<string, BotOut> = {};
      for (const bot of frame.bots) bots[bot.id] = bot;
      return {
        ...state, cursor: frame.cursor, bots, computerRuns: withSnapshotSteps(state.computerRuns, frame.computer_steps),
        activityRuns: withSnapshotRunSteps(state.activityRuns, frame.run_steps),
      };
    }

    case "bot_status": {
      const existing = state.bots[frame.bot_id];
      const updated: BotOut | undefined = existing
        ? { ...existing, status: frame.status, activity: frame.activity }
        : existing;
      return {
        ...state,
        cursor: frame.seq,
        bots: updated ? { ...state.bots, [frame.bot_id]: updated } : state.bots,
        toolLines: withToolLine(state, frame),
      };
    }

    case "message": {
      const existing = state.messagesByThread[frame.thread_id] ?? [];
      // Final review, finding 2: Ruling 15 publishes an empty-bodied
      // placeholder `message` frame before streaming starts, then the
      // real reply under the SAME id once the turn ends. Upsert by id
      // instead of always appending, or the placeholder and the final
      // reply land as two separate bubbles sharing one React key.
      const index = existing.findIndex((message) => message.id === frame.message.id);
      // A placeholder (seq 0) replaced by the stored reply moves to the end:
      // handoff lines published while it streamed must stay above the answer.
      const replacesPlaceholder = index !== -1 && existing[index].seq === 0 && frame.message.seq > 0;
      const next =
        index === -1
          ? [...existing, frame.message]
          : replacesPlaceholder
            ? [...existing.slice(0, index), ...existing.slice(index + 1), frame.message]
            : existing.map((message, i) => (i === index ? frame.message : message));
      return {
        ...state,
        cursor: frame.seq,
        messagesByThread: { ...state.messagesByThread, [frame.thread_id]: next },
      };
    }

    case "text_delta": {
      const previous = state.streaming[frame.message_id] ?? "";
      return {
        ...state,
        cursor: frame.seq,
        streaming: { ...state.streaming, [frame.message_id]: previous + frame.delta },
      };
    }

    case "message_done": {
      const kept = closeMessage(state, frame);
      // A reply closed with nothing stored is gone, and so are its lines.
      const gone = !kept.some((message) => message.id === frame.message_id);
      return {
        ...state,
        cursor: frame.seq,
        streaming: withoutKey(state.streaming, frame.message_id),
        messagesByThread: { ...state.messagesByThread, [frame.thread_id]: kept },
        toolLines: gone ? withoutKey(state.toolLines, frame.message_id) : state.toolLines,
      };
    }

    case "speech_ready": {
      const known = state.speechReady[frame.message_id] ?? { parts: 0, done: false };
      const ready = { parts: Math.max(known.parts, frame.part + 1), done: known.done || frame.done };
      return { ...state, cursor: frame.seq, speechReady: { ...state.speechReady, [frame.message_id]: ready } };
    }

    case "bot_removed": {
      return { ...state, cursor: frame.seq, bots: withoutKey(state.bots, frame.bot_id) };
    }

    case "bot_updated": {
      return { ...state, cursor: frame.seq, bots: { ...state.bots, [frame.bot.id]: frame.bot } };
    }

    case "tasks_changed":
      return { ...state, cursor: frame.seq, boardVersion: { ...state.boardVersion, tasks: state.boardVersion.tasks + 1 } };

    case "money_changed":
      return { ...state, cursor: frame.seq, boardVersion: bumpMoney(state.boardVersion, frame.change) };

    case "day_notes_changed":
      return { ...state, cursor: frame.seq, boardVersion: { ...state.boardVersion, dayNotes: state.boardVersion.dayNotes + 1 } };

    case "notes_changed":
      return { ...state, cursor: frame.seq, boardVersion: { ...state.boardVersion, notes: state.boardVersion.notes + 1 } };

    case "documents_changed":
      return { ...state, cursor: frame.seq, boardVersion: { ...state.boardVersion, documents: state.boardVersion.documents + 1 } };

    case "memories_changed":
      return { ...state, cursor: frame.seq, boardVersion: { ...state.boardVersion, memories: state.boardVersion.memories + 1 } };

    // Every state change of a card (open, cleared, given up, blocked, opened in the main
    // Brave) replaces the copy kept here. Advancing the cursor means a resume never replays it.
    case "stuck_card":
      return { ...state, cursor: frame.seq, stuckCards: { ...state.stuckCards, [frame.card.id]: frame.card } };

    // Like stuck_card: the newest frame of a card replaces the copy kept here.
    case "approval_card":
      return { ...state, cursor: frame.seq, approvalCards: { ...state.approvalCards, [frame.card.id]: withoutCrops(frame.card) } };

    case "computer_pointer":
      return { ...state, cursor: frame.seq, pointers: withPointer(state, frame) };

    case "computer_step":
      return { ...state, cursor: frame.seq, computerRuns: withComputerStep(state.computerRuns, frame, state.messagesByThread) };

    case "run_step":
      return { ...state, cursor: frame.seq, activityRuns: withRunStep(state.activityRuns, frame, state.messagesByThread) };

    case "routines_changed":
      return { ...state, cursor: frame.seq, routineVersion: { ...state.routineVersion, routines: state.routineVersion.routines + 1 } };

    case "questions_changed":
      return { ...state, cursor: frame.seq, routineVersion: { ...state.routineVersion, questions: state.routineVersion.questions + 1 } };

    case "proposals_changed":
      return { ...state, cursor: frame.seq, routineVersion: { ...state.routineVersion, proposals: state.routineVersion.proposals + 1 } };

    case "skills_changed":
      return { ...state, cursor: frame.seq, skillVersion: { ...state.skillVersion, skills: state.skillVersion.skills + 1 } };

    case "skill_proposals_changed":
      return { ...state, cursor: frame.seq, skillVersion: { ...state.skillVersion, proposals: state.skillVersion.proposals + 1 } };

    case "instruction_proposals_changed":
      return { ...state, cursor: frame.seq, instructionVersion: state.instructionVersion + 1 };
    case "connector_requests_changed":
      return { ...state, cursor: frame.seq, connectorVersion: state.connectorVersion + 1 };

    case "plan_changed":
      return {
        ...state, cursor: frame.seq,
        planRevisions: { ...state.planRevisions, [frame.bot_id]: Math.max(frame.revision, state.planRevisions[frame.bot_id] ?? 0) },
      };

    default:
      return state;
  }
}

// ---------------------------------------------------------------------------
// Stateful shell
// ---------------------------------------------------------------------------

export interface MinimalSocket {
  onopen: (() => void) | null;
  onmessage: ((event: { data: string }) => void) | null;
  onclose: (() => void) | null;
  send(data: string): void;
  close(): void;
}

export type WebSocketFactory = (url: string) => MinimalSocket;

export const MIN_RECONNECT_DELAY_MS = 1000;
export const MAX_RECONNECT_DELAY_MS = 15000;

export class LiveStore {
  private state: LiveState = initialLiveState();
  private readonly listeners = new Set<(state: LiveState) => void>();
  private readonly frameListeners = new Set<(frame: ServerFrame, state: LiveState) => void>();
  private socket: MinimalSocket | null = null;
  private reconnectDelayMs = MIN_RECONNECT_DELAY_MS;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private closedByCaller = false;
  // Final review, finding 3: set once the first socket has opened, so
  // `openSocket` can tell a reconnect apart from the very first
  // connection -- only a reconnect needs to `resume`, since a fresh
  // connection's `snapshot` frame is already the starting point. Sending
  // `resume` with cursor 0 on every first connection instead made the
  // server replay the user's ENTIRE stored event history on every page
  // load.
  private hasConnectedOnce = false;

  constructor(
    private readonly url: string,
    private readonly createSocket: WebSocketFactory,
  ) {}

  getState(): LiveState {
    return this.state;
  }

  subscribe(listener: (state: LiveState) => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  // Every incoming frame, with the state it arrives on (before it is applied):
  // used by the attention notifier (S1.10).
  onFrame(listener: (frame: ServerFrame, state: LiveState) => void): () => void {
    this.frameListeners.add(listener);
    return () => this.frameListeners.delete(listener);
  }

  connect(): void {
    this.closedByCaller = false;
    this.openSocket();
  }

  close(): void {
    this.closedByCaller = true;
    if (this.reconnectTimer !== null) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this.socket?.close();
    this.socket = null;
  }

  private setState(next: LiveState): void {
    this.state = next;
    for (const listener of this.listeners) listener(this.state);
  }

  private openSocket(): void {
    const socket = this.createSocket(this.url);
    this.socket = socket;

    socket.onopen = () => {
      this.reconnectDelayMs = MIN_RECONNECT_DELAY_MS;
      if (this.hasConnectedOnce) {
        socket.send(JSON.stringify({ type: "resume", cursor: this.state.cursor }));
      }
      this.hasConnectedOnce = true;
    };

    socket.onmessage = (event) => {
      const frame = JSON.parse(event.data) as ServerFrame;
      for (const listener of this.frameListeners) listener(frame, this.state);
      this.setState(applyFrame(this.state, frame));
    };

    socket.onclose = () => {
      if (this.closedByCaller) return;
      this.scheduleReconnect();
    };
  }

  private scheduleReconnect(): void {
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      this.reconnectDelayMs = Math.min(this.reconnectDelayMs * 2, MAX_RECONNECT_DELAY_MS);
      this.openSocket();
    }, this.reconnectDelayMs);
  }
}

export function createLiveStore(): LiveStore {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const url = `${protocol}//${window.location.host}/api/events`;
  const factory: WebSocketFactory = (socketUrl) => new WebSocket(socketUrl) as unknown as MinimalSocket;
  return new LiveStore(url, factory);
}
