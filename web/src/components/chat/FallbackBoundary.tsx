import { Component, type ErrorInfo, type ReactNode } from "react";

interface FallbackBoundaryProps {
  fallback: ReactNode;
  children: ReactNode;
}

// Shows `fallback` instead of a part that failed to draw (redesign P2: a lazy chunk that could not load),
// so one broken piece never blanks the whole chat. The failure is logged, never hidden.
export class FallbackBoundary extends Component<FallbackBoundaryProps, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError(): { failed: boolean } {
    return { failed: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.warn("Showing plain text: the markdown renderer could not load.", error, info.componentStack);
  }

  render(): ReactNode {
    return this.state.failed ? this.props.fallback : this.props.children;
  }
}
