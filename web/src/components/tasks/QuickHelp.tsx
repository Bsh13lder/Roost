import { TASK_TOKENS, type HelpToken } from "./quickHelpTokens";
import { IconButton } from "../../ui/IconButton";
import { Popover } from "../../ui/Popover";

export interface QuickHelpProps {
  tokens?: readonly HelpToken[]; // the task line's by default; the expense line passes its own
}

// The "?" next to a quick line: every token it reads, with an English and a Spanish example.
export function QuickHelp({ tokens = TASK_TOKENS }: QuickHelpProps) {
  return (
    <Popover label="Quick line help" trigger={<IconButton label="Quick line help" icon={<span aria-hidden="true">?</span>} />}>
      <div className="quick-help">
        <p className="quick-help__lead">Type it all in one line. A chip&apos;s × puts its words back in the title.</p>
        <ul className="quick-help__list">
          {tokens.map((row) => (
            <li key={row.token + row.en} className="quick-help__row">
              <code className="quick-help__token">{row.token}</code>
              <span className="quick-help__means">{row.means}</span>
              <span className="quick-help__example"><span className="quick-help__lang">EN</span> {row.en}</span>
              <span className="quick-help__example"><span className="quick-help__lang">ES</span> {row.es}</span>
            </li>
          ))}
        </ul>
      </div>
    </Popover>
  );
}
