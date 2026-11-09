import type { SuggestOption } from "./quickSuggest";

export interface QuickSuggestListProps {
  id: string; // the list's id; the input's aria-controls points at it
  options: readonly SuggestOption[];
  active: number; // the highlighted option (the input's aria-activedescendant)
  onPick: (option: SuggestOption) => void;
  onHover: (index: number) => void;
}

export const optionId = (listId: string, index: number) => `${listId}-option-${index}`;

// The quick add's suggestions under the input: a listbox the input drives from the keyboard. A click
// picks without taking focus from the input.
export function QuickSuggestList({ id, options, active, onPick, onHover }: QuickSuggestListProps) {
  return (
    <ul id={id} role="listbox" aria-label="Suggestions" className="quick-suggest">
      {options.map((option, index) => (
        <li key={option.key} id={optionId(id, index)} role="option" aria-selected={index === active}
          className="quick-suggest__option" onMouseDown={(event) => event.preventDefault()}
          onMouseEnter={() => onHover(index)} onClick={() => onPick(option)}>
          <span>{option.label}</span>
          {option.hint ? <span className="quick-suggest__hint">{option.hint}</span> : null}
        </li>
      ))}
    </ul>
  );
}
