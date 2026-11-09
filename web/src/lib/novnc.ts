// The one module that reaches @novnc/novnc (MPL-2.0, used as published, never patched). The import() makes
// Vite emit it as its own chunk, so the main bundle never carries it (web/tests/licenseGate.test.ts).
export interface RfbLike {
  viewOnly: boolean;
  scaleViewport: boolean;
  addEventListener(type: string, listener: (event: Event) => void): void;
  disconnect(): void;
  focus?(): void;
  clipboardPasteFrom?(text: string): void;
  sendKey?(keysym: number, code: string | null, down?: boolean): void;
}

export type RfbConstructor = new (target: Element, channel: WebSocket, options?: { shared?: boolean }) => RfbLike;

export async function loadRfb(): Promise<RfbConstructor> {
  const module = await import("@novnc/novnc");
  return module.default as unknown as RfbConstructor;
}
