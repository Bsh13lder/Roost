// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Milind Soni and OpenMausBot contributors
// Modified from OpenMausBot src/components/WorkingIndicator.tsx and src/lib/working-time.ts @ 3b1f6de by BlckIt,
// 2026: Tailwind classes and cn() replaced by Roost CSS classes (styles/sidebar.css); formatElapsed moved in.
// Licensed under the Apache License, Version 2.0 (the "License"); you may not use
// this file except in compliance with the License. You may obtain a copy of the
// License at http://www.apache.org/licenses/LICENSE-2.0 (also LICENSES/Apache-2.0.txt).
// Unless required by applicable law or agreed to in writing, software distributed
// under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR
// CONDITIONS OF ANY KIND, either express or implied. See the License for the
// specific language governing permissions and limitations under the License.
//
// Duty-cycled activity indicators: the dots step through a few opacity holds
// per cycle (CSS), and the timer rewrites its own text node once a second
// instead of re-rendering through React. Long-lived indicators stay cheap.
import { useEffect, useRef } from "react";

/** Elapsed wall-clock as a compact string: 42s, 1m 05s, 12m 40s. */
export function formatElapsed(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000));
  if (total < 60) return `${total}s`;
  const minutes = Math.floor(total / 60);
  const seconds = total % 60;
  return `${minutes}m ${String(seconds).padStart(2, "0")}s`;
}

export function WorkingDots({ size = 4 }: { size?: number }) {
  return (
    <span className="working-dots" aria-hidden="true">
      {[0, 200, 400].map((delay) => (
        <span key={delay} className="working-dots__dot" style={{ width: size, height: size, animationDelay: `${delay}ms` }} />
      ))}
    </span>
  );
}

/** Self-ticking elapsed readout, counting up from `since` (epoch ms). */
export function WorkingTimer({ since }: { since: number }) {
  const node = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    const tick = () => {
      if (node.current) node.current.textContent = formatElapsed(Date.now() - since);
    };
    tick();
    const timer = setInterval(tick, 1000);
    return () => clearInterval(timer);
  }, [since]);
  return <span ref={node} className="working-timer" />;
}
