import { lazy, memo, Suspense, useState } from "react";
import { FallbackBoundary } from "./FallbackBoundary";
import { PlainText } from "./PlainText";

// The markdown renderer is a lazy chunk (shared with the notes preview), so the entry stays in budget.
type MarkdownModule = typeof import("../markdown/Markdown");
type MarkdownView = MarkdownModule["default"];

// One fetch of the chunk, shared by the chat's preload and React.lazy: a cache written once when the chunk
// arrives, never edited after. Once it is in, `loaded` holds its renderer, so a reply drawn after that shows
// its markdown on its first frame, with no plain-text frame before it. A failed fetch is forgotten, so the
// next chat that opens tries again.
let loading: Promise<MarkdownModule> | null = null;
let loaded: MarkdownView | null = null;

function loadMarkdown(): Promise<MarkdownModule> {
  loading ??= import("../markdown/Markdown").then(
    (module) => {
      loaded = module.default;
      return module;
    },
    (error: unknown) => {
      loading = null;
      throw error;
    },
  );
  return loading;
}

const LazyMarkdown = lazy(loadMarkdown);

// A chat calls this when it opens (final-review fix), so its first replies don't flash from plain text to
// markdown. It never rejects: a chunk that can't load is logged, and the replies keep their plain text.
export async function preloadMarkdown(): Promise<void> {
  try {
    await loadMarkdown();
  } catch (error) {
    console.warn("Could not preload the markdown renderer: replies show as plain text until it loads.", error);
  }
}

interface RichTextProps {
  text: string;
  id: string;
}

// A bot's reply as markdown (redesign P2). The plain text shows while the renderer loads, and stays if it
// never does: the reply is always readable. Memoized on its two strings (final-review fix): a live frame
// re-renders the whole chat, and only the reply whose text changed is parsed again.
function RichTextView({ text, id }: RichTextProps) {
  // Chosen once per reply, so a reply never swaps renderers (and loses a code block's "Copied") mid-life.
  const [Markdown] = useState(() => loaded ?? LazyMarkdown);
  const plain = <PlainText text={text} keyPrefix={id} />;
  return (
    <FallbackBoundary fallback={plain}>
      <Suspense fallback={plain}>
        <Markdown text={text} />
      </Suspense>
    </FallbackBoundary>
  );
}

export const RichText = memo(RichTextView);
