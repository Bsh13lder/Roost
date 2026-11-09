import { useState, type FormEvent } from "react";
import { Button } from "../../ui/Button";
import { DateTimePicker } from "../../ui/date/DateTimePicker";
import { Input } from "../../ui/Input";
import { Menu, MenuItem } from "../../ui/Menu";
import { Popover } from "../../ui/Popover";
import { MAX_SUGGESTIONS } from "./constants";
import {
  PRIORITY_CHOICES, REPEAT_CHOICES, dateWords, filterNames, insertWords, tagWords,
} from "./quickInsert";

export interface QuickPickersProps {
  text: string; // the line as typed
  matches: Record<string, string[]> | undefined; // the words each chip came from: a pick replaces them
  projects: readonly string[];
  tags: readonly string[];
  onText: (next: string) => void; // the line with the picked words in it
  onNeed: (list: "projects" | "tags") => void; // a picker opened: load the names it lists
}

type Which = "date" | "project" | "tag";

// Manual pickers beside the quick add's line (Amendment T): Date, Project, Priority, Tag and Repeat. Each
// writes the same words typing would, into the line, so the server reads them and the same chip appears.
export function QuickPickers({ text, matches, projects, tags, onText, onNeed }: QuickPickersProps) {
  const [open, setOpen] = useState<Which | null>(null);
  const [draft, setDraft] = useState("");
  const [query, setQuery] = useState("");
  const toggle = (which: Which) => (now: boolean) => {
    setOpen(now ? which : null);
    setQuery("");
    if (now && which === "project") onNeed("projects");
    if (now && which === "tag") onNeed("tags");
  };
  const put = (words: string, kind: string, replace = true) => {
    onText(insertWords(text, words, replace ? matches?.[kind] ?? [] : []));
    setOpen(null);
  };
  const addTag = (raw: string) => {
    const words = tagWords(raw);
    if (words && !text.toLocaleLowerCase().split(/\s+/).includes(words.toLocaleLowerCase())) put(words, "tag", false);
  };
  // The panel is portalled, but React still bubbles its submit to the quick add's own form: stop it there.
  const submitTag = (event: FormEvent) => { event.preventDefault(); event.stopPropagation(); addTag(query); };
  const shownProjects = filterNames(projects, query).slice(0, MAX_SUGGESTIONS * 3);
  const shownTags = filterNames(tags, query).slice(0, MAX_SUGGESTIONS);
  return (
    <div className="quick-pickers" role="group" aria-label="Add details">
      <Popover label="Pick a date" open={open === "date"} onOpenChange={toggle("date")} align="start"
        trigger={<Button variant="ghost" size="sm">Date</Button>}>
        <div className="quick-picker">
          <DateTimePicker label="Due date" value={draft} onChange={setDraft} />
          <Button variant="primary" size="sm" onClick={() => { put(dateWords(draft), "date"); setDraft(""); }}>
            {draft.trim() ? "Use this date" : "No date"}
          </Button>
        </div>
      </Popover>
      <Popover label="Pick a project" open={open === "project"} onOpenChange={toggle("project")} align="start"
        trigger={<Button variant="ghost" size="sm">Project</Button>}>
        <div className="quick-picker">
          <Input aria-label="Search projects" placeholder="Search projects" value={query} autoComplete="off"
            onChange={(event) => setQuery(event.target.value)} />
          <ul className="quick-picker__list">
            {shownProjects.map((name) => (
              <li key={name}><Button variant="ghost" size="sm" onClick={() => put(`/${name}`, "project")}>{name}</Button></li>
            ))}
          </ul>
          {shownProjects.length === 0 ? <p className="quick-picker__none">No project like that.</p> : null}
        </div>
      </Popover>
      <Menu label="Priority" trigger="Priority" align="start">
        {PRIORITY_CHOICES.map((choice) => (
          <MenuItem key={choice.key} onSelect={() => put(choice.words, "priority")}>{choice.label}</MenuItem>
        ))}
      </Menu>
      <Popover label="Pick a tag" open={open === "tag"} onOpenChange={toggle("tag")} align="start"
        trigger={<Button variant="ghost" size="sm">Tag</Button>}>
        <form className="quick-picker" onSubmit={submitTag}>
          <Input aria-label="Tag" placeholder="Find or make a tag" value={query} autoComplete="off"
            onChange={(event) => setQuery(event.target.value)} />
          <ul className="quick-picker__list">
            {shownTags.map((name) => (
              <li key={name}><Button variant="ghost" size="sm" onClick={() => addTag(name)}>{`#${name}`}</Button></li>
            ))}
          </ul>
          <Button type="submit" variant="primary" size="sm" disabled={tagWords(query) === null}>Add tag</Button>
        </form>
      </Popover>
      <Menu label="Repeat" trigger="Repeat" align="start">
        {REPEAT_CHOICES.map((choice) => (
          <MenuItem key={choice.key} onSelect={() => put(choice.words, "repeat")}>{choice.label}</MenuItem>
        ))}
      </Menu>
    </div>
  );
}
