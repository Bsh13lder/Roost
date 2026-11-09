// What a Univer editor needs from its document kind (M2 D4): mount a snapshot
// into a container and report edits, read the current snapshot back, tear
// down. UniverEditor's tests hand it a fake kit, so they never load Univer.
export interface MountedEditor {
  snapshot(): Record<string, unknown> | null;
  dispose(): void;
}

export interface UniverKit {
  mount(container: HTMLElement, payload: Record<string, unknown>, onChange: () => void): MountedEditor;
}

// Univer renders its own React root into the element it is given and
// unmounts that root when disposed. Each mount gets a fresh host element, so
// a remount ("Load the latest") never shares a root with the editor it
// replaces, and the old one is torn down after the current React commit:
// unmounting a root inside another root's commit is unsafe.
export function mountHost(container: HTMLElement): HTMLElement {
  const host = document.createElement("div");
  host.className = "univer-host";
  container.appendChild(host);
  return host;
}

export function disposeAfterCommit(host: HTMLElement, dispose: () => void): void {
  setTimeout(() => {
    dispose();
    host.remove();
  }, 0);
}
