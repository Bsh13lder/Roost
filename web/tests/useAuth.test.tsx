import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AuthProvider, useAuth } from "../src/hooks/useAuth";
import { appTimeZone, browserTimeZone, setAppTimeZone } from "../src/lib/timeZone";

const { resetLiveStoreMock } = vi.hoisted(() => ({ resetLiveStoreMock: vi.fn() }));
vi.mock("../src/hooks/useLiveStore", () => ({
  resetLiveStore: resetLiveStoreMock,
}));

const meMock = vi.fn();
const loginMock = vi.fn();
const logoutMock = vi.fn();
const registerMock = vi.fn();
const putTimeZoneMock = vi.fn();
vi.mock("../src/api/timeZone", () => ({ putTimeZone: (zone: string) => putTimeZoneMock(zone) }));
vi.mock("../src/api/auth", () => ({
  me: (...args: unknown[]) => meMock(...args),
  login: (...args: unknown[]) => loginMock(...args),
  logout: (...args: unknown[]) => logoutMock(...args),
  register: (...args: unknown[]) => registerMock(...args),
}));

function Probe() {
  const { user, login, logout } = useAuth();
  return (
    <div>
      <span data-testid="user">{user?.username ?? "none"}</span>
      <button onClick={() => void login("alice", "pw-123456")}>do-login</button>
      <button onClick={() => void logout()}>do-logout</button>
    </div>
  );
}

beforeEach(() => {
  resetLiveStoreMock.mockReset();
  meMock.mockReset().mockResolvedValue(null);
  loginMock.mockReset();
  logoutMock.mockReset();
  registerMock.mockReset();
  putTimeZoneMock.mockReset().mockResolvedValue({ timezone: "x" });
  setAppTimeZone("Europe/Madrid");
});

afterEach(() => cleanup());

// Regression for the review finding: the live WS store is a module
// singleton `AuthProvider` never tore down, so a second user logging in
// on the same tab could briefly see the previous user's cached state.
describe("AuthProvider — live store reset on auth transitions", () => {
  it("resets the live store on logout", async () => {
    logoutMock.mockResolvedValue(undefined);
    const user = userEvent.setup();
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );
    await waitFor(() => expect(screen.getByTestId("user")).toHaveTextContent("none"));

    await user.click(screen.getByText("do-logout"));

    await waitFor(() => expect(logoutMock).toHaveBeenCalled());
    expect(resetLiveStoreMock).toHaveBeenCalledTimes(1);
  });

  it("resets the live store on a fresh login", async () => {
    loginMock.mockResolvedValue({ id: "u1", username: "alice" });
    const user = userEvent.setup();
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );
    await waitFor(() => expect(screen.getByTestId("user")).toHaveTextContent("none"));

    await user.click(screen.getByText("do-login"));

    await waitFor(() => expect(screen.getByTestId("user")).toHaveTextContent("alice"));
    expect(resetLiveStoreMock).toHaveBeenCalledTimes(1);
  });
});

// Auto-detect (owner, 2026-11-09): the account's zone is the one every time is shown on.
describe("AuthProvider — the account's time zone", () => {
  it("saves this device's zone silently when the account has none", async () => {
    meMock.mockResolvedValue({ id: "u1", username: "alice", timezone: null });
    render(<AuthProvider><Probe /></AuthProvider>);
    await waitFor(() => expect(screen.getByTestId("user")).toHaveTextContent("alice"));
    await waitFor(() => expect(putTimeZoneMock).toHaveBeenCalledWith(browserTimeZone()));
    expect(appTimeZone()).toBe(browserTimeZone());
  });

  it("uses the account's zone, and saves nothing, when it is set", async () => {
    meMock.mockResolvedValue({ id: "u1", username: "alice", timezone: "America/New_York" });
    render(<AuthProvider><Probe /></AuthProvider>);
    await waitFor(() => expect(screen.getByTestId("user")).toHaveTextContent("alice"));
    expect(appTimeZone()).toBe("America/New_York");
    expect(putTimeZoneMock).not.toHaveBeenCalled();
  });

  it("asks for the zone after a login whose answer does not carry it", async () => {
    loginMock.mockResolvedValue({ id: "u1", username: "alice" });
    const user = userEvent.setup();
    render(<AuthProvider><Probe /></AuthProvider>);
    await waitFor(() => expect(screen.getByTestId("user")).toHaveTextContent("none"));
    meMock.mockResolvedValue({ id: "u1", username: "alice", timezone: "Asia/Tokyo" });
    await user.click(screen.getByText("do-login"));
    await waitFor(() => expect(appTimeZone()).toBe("Asia/Tokyo"));
    expect(putTimeZoneMock).not.toHaveBeenCalled();
  });
});
