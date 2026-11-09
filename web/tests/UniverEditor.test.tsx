import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { UniverEditor } from "../src/components/documents/univer/UniverEditor";
import { DOCUMENT_AUTOSAVE_MS } from "../src/components/documents/univer/useUniverAutosave";
import { disposeAfterCommit, mountHost, type UniverKit } from "../src/components/documents/univer/kit";
import { RevisionConflictError } from "../src/api/conflict";
import type { DocumentDetailOut, DocumentOut } from "../src/api/types";

const saveDocumentMock = vi.fn();
vi.mock("../src/api/documents", () => ({ saveDocument: (...a: unknown[]) => saveDocumentMock(...a) }));

type Snapshot = Record<string, unknown>;
interface Mount { payload: Snapshot; change: () => void; disposed: boolean }

// A stand-in for Univer: the "editor" holds one snapshot the test edits.
function fakeKit() {
  const mounts: Mount[] = [];
  let current: Snapshot | null = null;
  const kit: UniverKit = {
    mount(_container, payload, onChange) {
      const mount: Mount = { payload, change: onChange, disposed: false };
      mounts.push(mount);
      current = payload;
      return { snapshot: () => current, dispose: () => { mount.disposed = true; } };
    },
  };
  const edit = (next: Snapshot) => {
    current = next;
    mounts[mounts.length - 1].change();
  };
  return { kit, mounts, edit };
}

function detail(overrides: Partial<DocumentDetailOut> = {}): DocumentDetailOut {
  return {
    id: "d1", kind: "doc", title: "My tasks", pages: null, revision: 1, created_at: "x", updated_at: "x",
    created_by_bot: null, tainted: false, payload: { body: { dataStream: "a\r\n" } }, ...overrides,
  };
}

function meta(revision: number): DocumentOut {
  const { payload: _payload, ...rest } = detail({ revision });
  return rest;
}

const mine = { body: { dataStream: "mine\r\n" } };
const pause = () => act(async () => { await vi.advanceTimersByTimeAsync(DOCUMENT_AUTOSAVE_MS + 10); });

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  saveDocumentMock.mockReset();
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe("UniverEditor", () => {
  it("saves an edit after a pause, against the revision it opened", async () => {
    saveDocumentMock.mockResolvedValue(meta(2));
    const fake = fakeKit();
    render(<UniverEditor kit={fake.kit} document={detail()} />);
    expect(fake.mounts[0].payload).toEqual({ body: { dataStream: "a\r\n" } });
    act(() => fake.edit(mine));
    await pause();
    expect(saveDocumentMock).toHaveBeenCalledWith("d1", { payload: mine, base_revision: 1 });
    expect(await screen.findByText("Saved")).toBeInTheDocument();
  });

  it("never sends an unchanged snapshot, and saves a pending edit when closed", async () => {
    saveDocumentMock.mockResolvedValue(meta(2));
    const fake = fakeKit();
    const { unmount } = render(<UniverEditor kit={fake.kit} document={detail()} />);
    act(() => fake.mounts[0].change());   // e.g. a selection change: the same snapshot
    await pause();
    expect(saveDocumentMock).not.toHaveBeenCalled();
    act(() => fake.edit(mine));
    unmount();
    expect(saveDocumentMock).toHaveBeenCalledWith("d1", { payload: mine, base_revision: 1 });
    expect(fake.mounts[0].disposed).toBe(true);
  });

  it("never saves a document the editor only normalized on opening (a bot-made one, say)", async () => {
    saveDocumentMock.mockResolvedValue(meta(2));
    const normalized = { body: { dataStream: "a\r\n" }, documentStyle: {} };
    let onChange = () => {};
    const kit: UniverKit = {
      mount(_container, _payload, change) {
        onChange = change;
        return { snapshot: () => normalized, dispose: () => {} };
      },
    };
    const { unmount } = render(<UniverEditor kit={kit} document={detail()} />);
    act(() => onChange());   // Univer reports its own loading as a change
    await pause();
    unmount();
    expect(saveDocumentMock).not.toHaveBeenCalled();
  });

  it("on a stale revision, Load the latest remounts their copy and saves nothing of mine", async () => {
    const theirs = detail({ revision: 3, payload: { body: { dataStream: "theirs\r\n" } } });
    saveDocumentMock.mockRejectedValueOnce(new RevisionConflictError(theirs));
    const fake = fakeKit();
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(<UniverEditor kit={fake.kit} document={detail()} />);
    act(() => fake.edit(mine));
    await pause();
    await user.click(await screen.findByRole("button", { name: "Load the latest" }));
    expect(fake.mounts).toHaveLength(2);
    expect(fake.mounts[1].payload).toEqual({ body: { dataStream: "theirs\r\n" } });
    expect(saveDocumentMock).toHaveBeenCalledTimes(1);
  });

  it("on a stale revision, Keep mine saves my copy over the latest revision", async () => {
    saveDocumentMock.mockRejectedValueOnce(new RevisionConflictError(detail({ revision: 3 }))).mockResolvedValue(meta(4));
    const fake = fakeKit();
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(<UniverEditor kit={fake.kit} document={detail()} />);
    act(() => fake.edit(mine));
    await pause();
    await user.click(await screen.findByRole("button", { name: "Keep mine" }));
    expect(saveDocumentMock).toHaveBeenLastCalledWith("d1", { payload: mine, base_revision: 3 });
    expect(fake.mounts).toHaveLength(1);
  });
});

describe("Univer host", () => {
  it("gives every mount its own host and tears the old one down after the commit", async () => {
    const container = document.createElement("div");
    const first = mountHost(container);
    const second = mountHost(container);
    expect(first).not.toBe(second);
    expect(Array.from(container.children)).toEqual([first, second]);
    const dispose = vi.fn();
    disposeAfterCommit(first, dispose);
    expect(dispose).not.toHaveBeenCalled();
    expect(first.isConnected || container.contains(first)).toBe(true);
    await vi.advanceTimersByTimeAsync(1);
    expect(dispose).toHaveBeenCalledTimes(1);
    expect(Array.from(container.children)).toEqual([second]);
  });
});
