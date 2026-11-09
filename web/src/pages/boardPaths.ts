// The Board's addresses that the routes (App.tsx, in the entry) and the lazy Project page both need. A tiny
// module of its own, so the routes never import the Project page's code to read a path.
// There is no Projects tab (lead task 15): projects are the Tasks area's rail. Its old address, and a deleted
// project's page, open All tasks; a project's page goes back to its own tasks.
export const ALL_TASKS_HREF = "/board?tab=tasks&project=all";
export const projectTasksHref = (id: string) => `/board?tab=tasks&project=${encodeURIComponent(id)}`;

// One item's own place on the Board (lead task 06). A task opens its drawer (?task=), a note its page (?note=), a
// document itself (?document=). An expense has no page of its own, so its link is the Money tab narrowed to its day.
export const NOTE_PARAM = "note";
export const DOCUMENT_PARAM = "document";
export const taskHref = (id: string) => `/board?tab=tasks&task=${encodeURIComponent(id)}`;
export const noteHref = (id: string) => `/board?tab=notes&${NOTE_PARAM}=${encodeURIComponent(id)}`;
export const documentHref = (id: string) => `/board?tab=documents&${DOCUMENT_PARAM}=${encodeURIComponent(id)}`;
export const expenseDayHref = (day: string) => `/board?tab=money&range=custom&from=${day}&to=${day}`;
