import { PlusIcon, SearchIcon } from "../icons";
import { Input } from "../../ui/Input";
import { Menu, MenuItem, MenuLink } from "../../ui/Menu";

export interface SidebarTopProps {
  query: string;
  onQuery: (query: string) => void;
  onNewRoom: () => void;
}

// The sidebar's fixed top: search always shown, and the + for a new bot or room.
export function SidebarTop({ query, onQuery, onNewRoom }: SidebarTopProps) {
  return (
    <div className="sidebar-top">
      <label className="sidebar-search">
        <span className="sidebar-search__icon" aria-hidden="true"><SearchIcon /></span>
        <Input type="search" aria-label="Search chats" placeholder="Search" controlSize="md" value={query}
          onChange={(event) => onQuery(event.target.value)} />
      </label>
      <Menu label="New" trigger={<PlusIcon />}>
        <MenuLink to="/bots/new">New bot</MenuLink>
        <MenuItem onSelect={onNewRoom}>New room</MenuItem>
      </Menu>
    </div>
  );
}
