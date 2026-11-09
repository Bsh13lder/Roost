import { createContext } from "react";

// The project a quick add that names none joins (lead task 15): the one the Tasks rail picked. The Kanban column's
// "+" and the Calendar day's sit deep inside, so the Tasks area provides it once instead of passing it down.
export const QuickAddProject = createContext<string | undefined>(undefined);
