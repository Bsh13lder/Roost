// The small part of noVNC's RFB API Roost uses. @novnc/novnc ships no types (MPL-2.0, used as published).
declare module "@novnc/novnc" {
  interface RfbOptions { shared?: boolean; credentials?: { password?: string } }
  export default class RFB {
    constructor(target: Element, urlOrChannel: string | WebSocket, options?: RfbOptions);
    viewOnly: boolean;
    scaleViewport: boolean;
    resizeSession: boolean;
    background: string;
    addEventListener(type: string, listener: (event: Event) => void): void;
    disconnect(): void;
  }
}
