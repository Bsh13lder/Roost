import type { ReactNode } from "react";
import { useCopy } from "../../hooks/useCopy";
import { IconButton } from "../../ui/IconButton";
import { CheckIcon, CopyIcon } from "../icons";

// The part of a hast node a code block needs: its text lives in "text" leaves.
interface HastNode {
  type: string;
  value?: string;
  children?: readonly HastNode[];
}

const COPY_LABEL = { idle: "Copy code", copied: "Copied", failed: "Copy failed" } as const;

// A code block's text as the reader would select it.
export function hastText(node: HastNode | undefined): string {
  if (!node) return "";
  if (node.type === "text") return node.value ?? "";
  return (node.children ?? []).map(hastText).join("");
}

// A fenced code block (redesign P2): it scrolls inside itself, and Copy sits in its corner.
export function CodeBlock({ node, children }: { node?: unknown; children?: ReactNode }) {
  const { state, copy } = useCopy();
  const text = hastText(node as HastNode | undefined).replace(/\n$/, "");
  return (
    <div className="md__code">
      <IconButton className="md__copy" label={COPY_LABEL[state]} tooltip={false} size="sm"
        icon={state === "copied" ? <CheckIcon /> : <CopyIcon />} onClick={() => copy(text)} />
      <pre>{children}</pre>
    </div>
  );
}
