import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { TimeZoneGroup } from "../src/components/settings/TimeZoneGroup";
import { ApiError } from "../src/api/client";
import { appTimeZone, browserTimeZone, setAppTimeZone, zoneCity } from "../src/lib/timeZone";

const putTimeZone = vi.fn();
vi.mock("../src/api/timeZone", () => ({ putTimeZone: (zone: string) => putTimeZone(zone) }));

// A zone that is not this device's, whatever zone the machine running the tests is in.
const OTHER_ZONE = browserTimeZone() === "Asia/Tokyo" ? "America/New_York" : "Asia/Tokyo";

beforeEach(() => {
  putTimeZone.mockReset().mockImplementation((zone: string) => Promise.resolve({ timezone: zone }));
});

afterEach(() => { cleanup(); setAppTimeZone("Europe/Madrid"); });

describe("Settings: Time zone", () => {
  it("shows the account's zone by its city, in a select of zones", () => {
    setAppTimeZone(OTHER_ZONE);
    render(<TimeZoneGroup />);
    const group = screen.getByRole("region", { name: "Time zone" });
    expect(group).toHaveTextContent(zoneCity(OTHER_ZONE));
    const select = screen.getByRole("combobox", { name: "Time zone" }) as HTMLSelectElement;
    expect(select.value).toBe(OTHER_ZONE);
  });

  it("offers this device's zone when the account's differs, and switches to it", async () => {
    setAppTimeZone(OTHER_ZONE);
    const user = userEvent.setup();
    render(<TimeZoneGroup />);
    await user.click(screen.getByRole("button", { name: `Use this device's (${zoneCity(browserTimeZone())})` }));
    expect(putTimeZone).toHaveBeenCalledWith(browserTimeZone());
    await waitFor(() => expect(appTimeZone()).toBe(browserTimeZone()));
    expect(screen.queryByRole("button", { name: /Use this device's/ })).not.toBeInTheDocument();
  });

  it("has no device button when the zones match", () => {
    setAppTimeZone(browserTimeZone());
    render(<TimeZoneGroup />);
    expect(screen.queryByRole("button", { name: /Use this device's/ })).not.toBeInTheDocument();
  });

  it("saves a zone picked from the list", async () => {
    setAppTimeZone(browserTimeZone());
    const user = userEvent.setup();
    render(<TimeZoneGroup />);
    await user.selectOptions(screen.getByRole("combobox", { name: "Time zone" }), OTHER_ZONE);
    expect(putTimeZone).toHaveBeenCalledWith(OTHER_ZONE);
    await waitFor(() => expect(appTimeZone()).toBe(OTHER_ZONE));
  });

  it("keeps the zone and says so when the server refuses it", async () => {
    setAppTimeZone(browserTimeZone());
    putTimeZone.mockRejectedValue(new ApiError(422, "That isn't a time zone."));
    const user = userEvent.setup();
    render(<TimeZoneGroup />);
    await user.selectOptions(screen.getByRole("combobox", { name: "Time zone" }), OTHER_ZONE);
    expect(await screen.findByRole("alert")).toHaveTextContent("That isn't a time zone.");
    expect(appTimeZone()).toBe(browserTimeZone());
  });
});
