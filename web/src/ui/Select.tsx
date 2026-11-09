import * as RadixSelect from "@radix-ui/react-select";
import { CheckIcon, ChevronDownIcon } from "../components/icons";
import { cx } from "./cx";
import { controlA11y, useFieldControl } from "./Field";
import { usePortalContainer } from "./portalContainer";
import type { ControlSize } from "./Button";

// An option's value is never "" (Radix keeps "" for "nothing chosen"): use a word such as "none".
export interface SelectOption<T extends string = string> {
  value: T;
  label: string;
  hint?: string; // a short line beside the label in the list; the button shows the label alone
  disabled?: boolean;
}

export interface SelectProps<T extends string = string> {
  value: T;
  onChange: (value: T) => void;
  options: ReadonlyArray<SelectOption<T>>;
  label?: string; // the accessible name when the select is not inside a Field
  id?: string;
  disabled?: boolean;
  placeholder?: string;
  size?: ControlSize;
  defaultOpen?: boolean; // open when first drawn (a link that says "pick one here")
}

// A styled list to pick one from (redesign P1, Radix Select): the keyboard, typeahead and screen
// reader behaviour of a native select, in Roost's look. It opens below its button.
export function Select<T extends string = string>({
  value, onChange, options, label, id, disabled = false, placeholder, size = "lg", defaultOpen = false,
}: SelectProps<T>) {
  const a11y = controlA11y(useFieldControl(), { id });
  const container = usePortalContainer();
  return (
    <RadixSelect.Root value={value} onValueChange={(next) => onChange(next as T)} disabled={disabled}
      defaultOpen={defaultOpen}>
      <RadixSelect.Trigger {...a11y} aria-label={label} className={cx("select", `select--${size}`)}>
        <RadixSelect.Value placeholder={placeholder} />
        <RadixSelect.Icon className="select__icon"><ChevronDownIcon /></RadixSelect.Icon>
      </RadixSelect.Trigger>
      <RadixSelect.Portal container={container}>
        <RadixSelect.Content className="select__content" position="popper" sideOffset={4}>
          <RadixSelect.Viewport className="select__viewport">
            {options.map((option) => (
              <RadixSelect.Item key={option.value} value={option.value} disabled={option.disabled} className="select__item">
                <RadixSelect.ItemText>{option.label}</RadixSelect.ItemText>
                {option.hint ? <span className="select__hint">{option.hint}</span> : null}
                <RadixSelect.ItemIndicator className="select__check"><CheckIcon /></RadixSelect.ItemIndicator>
              </RadixSelect.Item>
            ))}
          </RadixSelect.Viewport>
        </RadixSelect.Content>
      </RadixSelect.Portal>
    </RadixSelect.Root>
  );
}
