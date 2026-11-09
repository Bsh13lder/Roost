import { apiRequest } from "./client";

export interface TimeZoneOut {
  timezone: string; // an IANA name, "Asia/Tokyo"
}

// The account's time zone (PUT /api/auth/timezone): 200 with the zone saved, 422 for a name that is not one.
export function putTimeZone(timezone: string): Promise<TimeZoneOut> {
  return apiRequest<TimeZoneOut>("PUT", "/api/auth/timezone", { timezone });
}
