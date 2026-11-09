import type { MentionOption, MentionTrigger } from "../lib/mentions";

// The small "@Name" (a bot) or "#Name" (a project) list over a composer while one is being typed.
export function MentionList({ id, options, active, onPick, trigger = "@" }: {
  id: string; options: readonly MentionOption[]; active: number; onPick: (option: MentionOption) => void;
  trigger?: MentionTrigger;
}) {
  return (
    <ul id={id} role="listbox" aria-label={trigger === "#" ? "Project" : "Mention"} className="mention-list">
      {options.map((option, index) => (
        <li
          key={option.id}
          id={`${id}-${index}`}
          role="option"
          aria-selected={index === active}
          className="mention-list__option"
          // mousedown, not click: keeps focus (and the caret) in the box.
          onMouseDown={(event) => {
            event.preventDefault();
            onPick(option);
          }}
        >
          {trigger}{option.name}
        </li>
      ))}
    </ul>
  );
}
