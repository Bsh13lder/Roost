import type { MessageOut } from "../../api/types";
import { parseProgramActivity, programActivityLine } from "../../lib/programActivity";

// A program the bot ran in its own workspace, as one quiet line ("Ran: python3 a.py · exit 0"), with its output
// folded under it. The output is plain text in a <pre>: never markdown, never HTML.
export function ProgramActivityRow({ message }: { message: MessageOut }) {
  const data = parseProgramActivity(message.body);
  const failed = data !== null && data.op === "run" && (data.timed_out || data.exit_code !== 0);
  return (
    <li className="message message--activity message--program">
      <span className={failed ? "message__activity-text program-activity--failed" : "message__activity-text"}>
        {programActivityLine(data)}
      </span>
      {data && data.op === "run" && data.output ? (
        <details className="program-activity__output">
          <summary>Output{data.cut ? " (cut)" : ""}</summary>
          <pre>{data.output}</pre>
        </details>
      ) : null}
    </li>
  );
}
