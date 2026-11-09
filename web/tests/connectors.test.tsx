import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ConnectorAskCard from "../src/components/connectors/ConnectorAskCard";
import ConnectorsSection from "../src/components/connectors/ConnectorsSection";
import { fieldsOf } from "../src/components/connectors/ConnectorEditor";
import { ApiError } from "../src/api/client";
import type { ConnectorOut, KeyRequestOut } from "../src/api/connectors";
import { parseKeyRequestMessage } from "../src/lib/keyRequests";
import { askRows } from "../src/lib/myTurn";
import type { BotOut } from "../src/api/types";

const api = {
  getKeyRequest: vi.fn(), saveKeyRequest: vi.fn(), declineKeyRequest: vi.fn(), listConnectors: vi.fn(),
  addConnector: vi.fn(), changeConnector: vi.fn(), deleteConnector: vi.fn(),
};
vi.mock("../src/api/connectors", () => ({
  getKeyRequest: (...a: unknown[]) => api.getKeyRequest(...a),
  saveKeyRequest: (...a: unknown[]) => api.saveKeyRequest(...a),
  declineKeyRequest: (...a: unknown[]) => api.declineKeyRequest(...a),
  listConnectors: (...a: unknown[]) => api.listConnectors(...a),
  addConnector: (...a: unknown[]) => api.addConnector(...a),
  changeConnector: (...a: unknown[]) => api.changeConnector(...a),
  deleteConnector: (...a: unknown[]) => api.deleteConnector(...a),
}));
vi.mock("../src/hooks/useLiveStore", () => ({ useLiveState: () => ({ connectorVersion: 0 }) }));

const KEY = "sk-live-typed-by-the-user";

function request(overrides: Partial<KeyRequestOut> = {}): KeyRequestOut {
  return { id: "kr-1", bot_id: "bot-1", thread_id: "t-1", service: "Ahrefs", base_url: "https://api.ahrefs.com/v3",
    host: "api.ahrefs.com", why: "to read keyword volumes", auth_style: "bearer", auth_name: "Authorization",
    tainted: false, state: "open", connector_id: null, created_at: "x", ...overrides };
}

function connector(overrides: Partial<ConnectorOut> = {}): ConnectorOut {
  return { id: "c-1", name: "Search", purpose: "keywords", base_url: "https://api.example.com/v1",
    host: "api.example.com", auth_style: "bearer", auth_name: "Authorization", key_hint: "key set ••••WXYZ",
    allowed_prefixes: [], bot_ids: null, created_at: "x", updated_at: "x", ...overrides };
}

afterEach(() => { cleanup(); Object.values(api).forEach((mock) => mock.mockReset()); });

describe("ConnectorAskCard", () => {
  it("shows the service, site and reason, and Save sends the key once and clears it", async () => {
    api.getKeyRequest.mockResolvedValue(request());
    api.saveKeyRequest.mockResolvedValue(request({ state: "saved", connector_id: "c-9" }));
    render(<ConnectorAskCard requestId="kr-1" />);
    expect(await screen.findByText("Ahrefs")).toBeInTheDocument();
    expect(screen.getByText("api.ahrefs.com")).toBeInTheDocument();
    expect(screen.getByText("to read keyword volumes")).toBeInTheDocument();
    const field = screen.getByLabelText("Key");
    expect(field).toHaveAttribute("type", "password");
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
    await userEvent.type(field, KEY);
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(api.saveKeyRequest).toHaveBeenCalledWith("kr-1", KEY);
    expect(await screen.findByText("Key added · Ahrefs")).toBeInTheDocument();
    expect(document.body.innerHTML).not.toContain(KEY);
  });

  it("Not now declines, and a marked request shows the badge", async () => {
    api.getKeyRequest.mockResolvedValue(request({ tainted: true }));
    api.declineKeyRequest.mockResolvedValue(request({ state: "declined" }));
    render(<ConnectorAskCard requestId="kr-1" />);
    expect(await screen.findByText("from web content")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Not now" }));
    expect(api.declineKeyRequest).toHaveBeenCalledWith("kr-1");
    expect(await screen.findByText("Not now")).toBeInTheDocument();
  });

  it("a 422 shows the sentence and keeps the card; a 404 says it is gone", async () => {
    api.getKeyRequest.mockResolvedValue(request());
    api.saveKeyRequest.mockRejectedValue(new ApiError(422, "There is already a connector with that name."));
    render(<ConnectorAskCard requestId="kr-1" />);
    await userEvent.type(await screen.findByLabelText("Key"), KEY);
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("There is already a connector with that name.");
    cleanup();
    api.getKeyRequest.mockRejectedValue(new ApiError(404, "Key request not found"));
    render(<ConnectorAskCard requestId="kr-2" />);
    expect(await screen.findByText("This request is gone.")).toBeInTheDocument();
  });
});

describe("ConnectorsSection", () => {
  it("lists connectors with their site and key hint, never a key field value", async () => {
    api.listConnectors.mockResolvedValue([connector(), connector({ id: "c-2", name: "Mail", bot_ids: ["bot-1"] })]);
    render(<ConnectorsSection botId="bot-1" />);
    expect(await screen.findByText("Search")).toBeInTheDocument();
    expect(screen.getByText("api.example.com · key set ••••WXYZ · Every bot")).toBeInTheDocument();
    expect(screen.getByText(/Only this bot/)).toBeInTheDocument();
  });

  it("the editor opens with an empty key field and adds a connector", async () => {
    api.listConnectors.mockResolvedValue([]);
    api.addConnector.mockResolvedValue(connector({ id: "c-3", name: "New" }));
    render(<ConnectorsSection botId="bot-1" />);
    await userEvent.click(await screen.findByRole("button", { name: "Add connector" }));
    await userEvent.type(screen.getByLabelText("Name"), "New");
    await userEvent.type(screen.getByLabelText("Address"), "https://api.example.com/v1");
    await userEvent.type(screen.getByLabelText("Key"), KEY);
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(api.addConnector).toHaveBeenCalledWith(expect.objectContaining({ name: "New", secret: KEY }));
    expect(await screen.findByText("New")).toBeInTheDocument();
  });
});

describe("connector helpers", () => {
  it("fieldsOf sends the key only when typed, and who may use it", () => {
    const form = { name: "S", purpose: "", base_url: "https://a.example.com", auth_style: "bearer" as const,
      auth_name: "", prefixes: " /a \n\n/b", secret: "", who: "this" as const };
    expect(fieldsOf(form, "bot-1")).toEqual({ name: "S", purpose: "", base_url: "https://a.example.com",
      auth_style: "bearer", auth_name: "", allowed_prefixes: ["/a", "/b"], bot_ids: ["bot-1"] });
    expect(fieldsOf({ ...form, secret: "k", who: "all" }, "bot-1")).toMatchObject({ secret: "k", all_bots: true });
  });

  it("parses the card message and lists open requests in My turn", () => {
    expect(parseKeyRequestMessage('{"request_id":"kr-1","service":"A","host":"h"}')).toBe("kr-1");
    expect(parseKeyRequestMessage("not json")).toBeNull();
    expect(parseKeyRequestMessage('{"other":1}')).toBeNull();
    const bots = { "bot-1": { name: "Scout" } as BotOut };
    expect(askRows([], [], bots, [], [request(), request({ id: "kr-2", bot_id: "gone" })])).toEqual([
      { key: "key-request-kr-1", to: "/bots/bot-1", text: "Scout · Add a key · Ahrefs" },
    ]);
  });
});
