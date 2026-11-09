import { parseDate, type DateKind } from "../../api/dates";
import { pickedParts, type IsoDay } from "./dates";

// A date-only field's value as the day an API that takes "YYYY-MM-DD" wants: a picked day as it is,
// words read by the gateway the way `kind` says (an expense's day is "spent"; its sentence is the
// ApiError's message when it can't), "" as null.
export async function resolveDay(value: string, kind: DateKind = "due"): Promise<IsoDay | null> {
  const text = value.trim();
  if (!text) return null;
  const parts = pickedParts(text);
  if (parts) return parts.day;
  const read = await parseDate(text, kind);
  return read.due_date ? read.due_date.slice(0, 10) : null;
}
