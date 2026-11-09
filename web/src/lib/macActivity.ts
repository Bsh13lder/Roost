// web/src/lib/macActivity.ts: a Mac activity line's body as a sentence (the same words as roost/mac/activity.py).
import type { MacActivityData } from "../api/types";
import { OUTSIDE_CONTENT_MARK } from "../components/approvals/constants";

const OPS = new Set(["create", "edit", "rename", "trash", "undo"]);
const FALLBACK = "Changed a file";

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

export function parseMacActivity(body: string): MacActivityData | null {
  try {
    const data: unknown = JSON.parse(body);
    if (!isRecord(data) || typeof data.op !== "string" || !OPS.has(data.op)) return null;
    if (typeof data.label !== "string" || typeof data.path !== "string") return null;
    return {
      op: data.op as MacActivityData["op"], label: data.label, path: data.path,
      new_path: typeof data.new_path === "string" ? data.new_path : undefined,
      plus: typeof data.plus === "number" ? data.plus : 0, minus: typeof data.minus === "number" ? data.minus : 0,
      tainted_basis: data.tainted_basis === true, undid: typeof data.undid === "string" ? data.undid : undefined,
      undo: isRecord(data.undo) ? data.undo : null,
    };
  } catch {
    return null;
  }
}

// Control characters never reach a line (a name with a newline would look like two lines).
const clean = (text: string) => text.replace(/[\u0000-\u001f\u007f]/g, " ").trim();
const nameOf = (path: string) => clean(path.replace(/\/+$/, "").split("/").pop() ?? "");

export function macActivityLine(data: MacActivityData | null): string {
  if (!data) return FALLBACK;
  const name = nameOf(data.path);
  const label = clean(data.label);
  const mark = data.tainted_basis ? ` · ${OUTSIDE_CONTENT_MARK}` : "";
  switch (data.op) {
    case "create": return `Created ${name} · ${label}${mark}`;
    case "edit": return `Edited ${name} · ${label} (+${data.plus} −${data.minus})${mark}`;
    case "rename": return `Renamed ${name} → ${nameOf(data.new_path ?? "")} · ${label}${mark}`;
    case "trash": return `Moved ${name} to the trash · ${label}${mark}`;
    default: {
      if (data.undid === "trash") return `Moved ${name} back from the trash · ${label}`;
      const what = ({ edit: "the edit of", create: "the creation of", rename: "the rename of" } as Record<string, string>)[data.undid ?? ""] ?? "the change to";
      return `Undid ${what} ${name} · ${label}`;
    }
  }
}
