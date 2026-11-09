// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Milind Soni and OpenMausBot contributors
// Modified from OpenMausBot src/components/AskCard.tsx @ 3b1f6de by BlckIt, 2026: AskCard and AskSettledLine
// kept as FoldCard and FoldedLine; Tailwind classes, lucide-react icons, tour hooks and the ASK_* button
// constants replaced by Roost CSS classes (styles/chat.css) and text marks.
// Licensed under the Apache License, Version 2.0 (the "License"); you may not use
// this file except in compliance with the License. You may obtain a copy of the
// License at http://www.apache.org/licenses/LICENSE-2.0 (also LICENSES/Apache-2.0.txt).
// Unless required by applicable law or agreed to in writing, software distributed
// under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR
// CONDITIONS OF ANY KIND, either express or implied. See the License for the
// specific language governing permissions and limitations under the License.
//
// The one shape every in-chat card shares: while it waits it is a compact card
// with its title, an optional line on why, and its controls. Once handled it
// folds into a single quiet line, so a long chat doesn't keep a stack of boxes.
import type { ReactNode } from "react";

export function FoldCard({ icon, title, explanation, children, footer, ariaLabel, className }: {
  icon?: ReactNode; title: ReactNode; explanation?: ReactNode; children?: ReactNode; footer?: ReactNode; ariaLabel: string;
  className?: string; // an extra class, e.g. fold-card--wide for a card that holds a live screen
}) {
  return (
    <div role="group" aria-label={ariaLabel} data-fold-card="open" className={className ? `fold-card ${className}` : "fold-card"}>
      <div className="fold-card__head">
        {icon ? <span aria-hidden="true" className="fold-card__icon">{icon}</span> : null}
        <div className="fold-card__title"><bdi dir="auto">{title}</bdi></div>
      </div>
      {explanation ? <div className="fold-card__why">{explanation}</div> : null}
      {children ? <div className="fold-card__body">{children}</div> : null}
      {footer ? <div className="fold-card__footer">{footer}</div> : null}
    </div>
  );
}

export function FoldedLine({ icon, children, action, ariaLabel }: {
  icon?: ReactNode; children: ReactNode; action?: ReactNode; ariaLabel?: string;
}) {
  return (
    <div role="group" aria-label={ariaLabel} data-fold-card="folded" className="fold-card fold-card--folded">
      <span aria-hidden="true" className="fold-card__tick">{icon ?? "✓"}</span>
      <span dir="auto" aria-live="polite" className="fold-card__line">{children}</span>
      {action}
    </div>
  );
}
