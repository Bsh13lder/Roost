import { Suspense, lazy, useState } from "react";
import { Link } from "react-router-dom";
import { BoardIcon } from "../icons";
import { useAuth } from "../../hooks/useAuth";

// Settings is its own chunk, loaded when your initials are first pressed.
const SettingsSheet = lazy(() => import("../settings/SettingsSheet").then((module) => ({ default: module.SettingsSheet })));

export function initials(name: string): string {
  const parts = name.trim().split(/[\s._-]+/).filter(Boolean);
  const letters = parts.length > 1 ? parts[0][0] + parts[1][0] : name.trim().slice(0, 2);
  return letters.toUpperCase();
}

// The sidebar's fixed bottom (restructure slice 3): your initials open Settings, and the grid opens the Workspace.
export function SidebarFoot() {
  const { user } = useAuth();
  const [open, setOpen] = useState(false);
  return (
    <div className="sidebar-foot">
      <button type="button" className="icon-btn" aria-label="Settings" aria-haspopup="dialog" aria-expanded={open}
        onClick={() => setOpen(true)}>
        <span className="sidebar-foot__initials">{initials(user?.username ?? "")}</span>
      </button>
      <Link to="/routines" className="sidebar-foot__board"><span>Routines</span></Link>
      <Link to="/board" className="sidebar-foot__board"><BoardIcon /><span>Workspace</span></Link>
      {open ? (
        <Suspense fallback={null}><SettingsSheet open onClose={() => setOpen(false)} /></Suspense>
      ) : null}
    </div>
  );
}
