import { putTimeZone, type TimeZoneOut } from "../api/timeZone";
import { browserTimeZone, isTimeZone, setAppTimeZone } from "./timeZone";

type SaveZone = (zone: string) => Promise<TimeZoneOut>;

/** Takes the zone GET /api/auth/me gave: a known zone becomes the app's; none (null) means the account was
 * never told one, so this device's is used and saved silently; undefined (the server did not say) changes
 * nothing. A failed save keeps the device's zone for now and is tried again on the next load. */
export async function adoptAccountZone(timezone: string | null | undefined, save: SaveZone = putTimeZone): Promise<void> {
  if (timezone === undefined) return;
  if (timezone !== null) {
    if (!setAppTimeZone(timezone)) console.warn("The account's time zone is not one this browser knows.", timezone);
    return;
  }
  const device = browserTimeZone();
  if (!isTimeZone(device)) return;
  setAppTimeZone(device);
  try {
    await save(device);
  } catch (err: unknown) {
    console.warn("Roost could not save this device's time zone to the account.", err);
  }
}
