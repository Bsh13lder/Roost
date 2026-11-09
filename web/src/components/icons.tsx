import type { ReactNode } from "react";

// Roost's own 20×20 line icons (no icon library): each is decorative, so the
// button or link around it carries the accessible name.
function Icon({ children }: { children: ReactNode }) {
  return (
    <svg
      viewBox="0 0 20 20"
      width={20}
      height={20}
      aria-hidden="true"
      focusable="false"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      {children}
    </svg>
  );
}

export function BackIcon() {
  return <Icon><path d="M12 4l-6 6 6 6" /></Icon>;
}

export function MoreIcon() {
  return (
    <Icon>
      <circle cx={4} cy={10} r={1.6} />
      <circle cx={10} cy={10} r={1.6} />
      <circle cx={16} cy={10} r={1.6} />
    </Icon>
  );
}

export function PlusIcon() {
  return <Icon><path d="M10 4v12M4 10h12" /></Icon>;
}

export function SearchIcon() {
  return (
    <Icon>
      <circle cx={9} cy={9} r={5.5} />
      <path d="M13 13l4 4" />
    </Icon>
  );
}

export function BoardIcon() {
  return (
    <Icon>
      <rect x={3} y={3} width={6} height={6} rx={1.5} />
      <rect x={11} y={3} width={6} height={6} rx={1.5} />
      <rect x={3} y={11} width={6} height={6} rx={1.5} />
      <rect x={11} y={11} width={6} height={6} rx={1.5} />
    </Icon>
  );
}

export function ShareIcon() {
  return <Icon><path d="M10 3v10M6 7l4-4 4 4M4 13v3h12v-3" /></Icon>;
}

export function ChevronIcon() {
  return <Icon><path d="M8 4l6 6-6 6" /></Icon>;
}

export function PencilIcon() {
  return <Icon><path d="M13.5 3.5l3 3L7 16H4v-3z" /></Icon>;
}

export function ReplyIcon() {
  return <Icon><path d="M8 5L3 10l5 5M3 10h9a5 5 0 015 5v1" /></Icon>;
}

export function CloseIcon() {
  return <Icon><path d="M5 5l10 10M15 5L5 15" /></Icon>;
}

export function ChevronDownIcon() {
  return <Icon><path d="M5 8l5 5 5-5" /></Icon>;
}

export function ChevronUpIcon() {
  return <Icon><path d="M5 12l5-5 5 5" /></Icon>;
}

export function CheckIcon() {
  return <Icon><path d="M4 10.5l4 4 8-9" /></Icon>;
}

export function CopyIcon() {
  return (
    <Icon>
      <rect x={7} y={7} width={10} height={10} rx={2} />
      <path d="M13 7V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v6a2 2 0 0 0 2 2h2" />
    </Icon>
  );
}

export function UploadIcon() {
  return <Icon><path d="M10 13V3M6 7l4-4 4 4M4 13v3h12v-3" /></Icon>;
}

export function SparkIcon() {
  return <Icon><path d="M10 2.5l1.8 5.7 5.7 1.8-5.7 1.8-1.8 5.7-1.8-5.7-5.7-1.8 5.7-1.8z" /></Icon>;
}

export function CalendarIcon() {
  return (
    <Icon>
      <rect x={3} y={4.5} width={14} height={12.5} rx={2} />
      <path d="M3 8.5h14M7 2.5v4M13 2.5v4" />
    </Icon>
  );
}

// The priority flag (12×12): a small filled flag on a pole, drawn in the colour of its text.
export function FlagIcon() {
  return (
    <svg viewBox="0 0 12 12" width={12} height={12} aria-hidden="true" focusable="false">
      <path d="M2.5 1.5v9M2.5 2h6.2l-1.4 2.3 1.4 2.3H2.5" fill="currentColor" stroke="currentColor"
        strokeWidth={1.2} strokeLinejoin="round" />
    </svg>
  );
}

export function PinIcon() {
  return <Icon><path d="M12 3l5 5-2.5 1-3 3 .5 3.5-1.5 1.5-3.5-3.5L4 17M12 3L8.5 6 6 7l7 7" /></Icon>;
}

// A day's note (14×14): a small page with two lines of text.
export function DayNoteIcon() {
  return (
    <svg viewBox="0 0 14 14" width={13} height={13} fill="none" stroke="currentColor" strokeWidth={1.3}
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
      <path d="M3 1.8h6.2L11.5 4v8.2H3z" />
      <path d="M5 6.5h4.5M5 9h3" />
    </svg>
  );
}

export function LockIcon() {
  return (
    <Icon>
      <rect x={4.5} y={9} width={11} height={7.5} rx={2} />
      <path d="M7 9V6.5a3 3 0 016 0V9" />
    </Icon>
  );
}

// Restructure slice 3: the profile's rows, the chat's ⋯ menu and the composer's +.
export function ClockIcon() {
  return <Icon><circle cx={10} cy={10} r={7} /><path d="M10 6v4l2.5 2" /></Icon>;
}

export function ScreenIcon() {
  return <Icon><rect x={2.5} y={3.5} width={15} height={10} rx={1.5} /><path d="M7 17h6M10 13.5V17" /></Icon>;
}

export function BookIcon() {
  return <Icon><path d="M3 4.5h4.5a2.5 2.5 0 012.5 2.5v9a2 2 0 00-2-2H3zM17 4.5h-4.5A2.5 2.5 0 0010 7v9a2 2 0 012-2h5z" /></Icon>;
}

export function GearIcon() {
  return (
    <Icon>
      <circle cx={10} cy={10} r={2.5} />
      <path d="M10 2.5v2M10 15.5v2M2.5 10h2M15.5 10h2M4.7 4.7l1.4 1.4M13.9 13.9l1.4 1.4M4.7 15.3l1.4-1.4M13.9 6.1l1.4-1.4" />
    </Icon>
  );
}

export function PersonIcon() {
  return <Icon><circle cx={10} cy={7} r={3} /><path d="M4 17a6 6 0 0112 0" /></Icon>;
}

export function TrashIcon() {
  return <Icon><path d="M4 6h12M8 6V4h4v2M5.5 6l1 10.5h7l1-10.5M8.5 9v5M11.5 9v5" /></Icon>;
}

export function LinkIcon() {
  return <Icon><path d="M8.5 11.5a3 3 0 004.2 0l2.6-2.6a3 3 0 00-4.2-4.2l-.9.9M11.5 8.5a3 3 0 00-4.2 0l-2.6 2.6a3 3 0 004.2 4.2l.9-.9" /></Icon>;
}

export function FileIcon() {
  return <Icon><path d="M5 2.5h6.5L15 6v11.5H5z" /><path d="M11.5 2.5V6H15" /></Icon>;
}

// "Web": the quiet mark on chat text that came from a web page.
export function GlobeIcon() {
  return <Icon><circle cx="10" cy="10" r="7" /><path d="M3 10h14M10 3c2 2.2 2.8 4.5 2.8 7S12 14.8 10 17c-2-2.2-2.8-4.5-2.8-7S8 5.2 10 3z" /></Icon>;
}

// A project, on its "#Name" chip.
export function FolderIcon() {
  return <Icon><path d="M3 6.5A1.5 1.5 0 0 1 4.5 5h3l1.5 2h6.5A1.5 1.5 0 0 1 17 8.5v6a1.5 1.5 0 0 1-1.5 1.5h-11A1.5 1.5 0 0 1 3 14.5z" /></Icon>;
}

// The clean calendar: a reminder that fires that day.
export function BellIcon() {
  return <Icon><path d="M5 13.5V9a5 5 0 0 1 10 0v4.5l1.5 1.5h-13zM8.5 17.5a1.6 1.6 0 0 0 3 0" /></Icon>;
}

// Board toggles: a routine's runs on a calendar.
export function RepeatIcon() {
  return <Icon><path d="M4 9V8a3 3 0 0 1 3-3h9l-2.5-2.5M16 11v1a3 3 0 0 1-3 3H4l2.5 2.5" /></Icon>;
}

// Voice: the composer's microphone.
export function MicIcon() {
  return <Icon><rect x={7.5} y={2.5} width={5} height={9} rx={2.5} /><path d="M4.5 9.5a5.5 5.5 0 0011 0M10 15v2.5" /></Icon>;
}

// Voice: a reply read aloud (a speaker with sound).
export function SpeakerIcon() {
  return <Icon><path d="M3.5 8v4h3l4 3.5v-11l-4 3.5zM13.5 7.5a3.5 3.5 0 010 5M15.5 5a7 7 0 010 10" /></Icon>;
}

// Voice: stop what is playing or recording.
export function StopIcon() {
  return <Icon><rect x={5.5} y={5.5} width={9} height={9} rx={1.5} /></Icon>;
}

// The call button: a voice as five bars.
export function WaveIcon() {
  return <Icon><path d="M3 9v2M6.5 6.5v7M10 3.5v13M13.5 6.5v7M17 9v2" /></Icon>;
}

export function MicOffIcon() {
  return (
    <Icon>
      <path d="M12.5 8V5a2.5 2.5 0 00-4.9-.7M7.5 7.5V9a2.5 2.5 0 004 2" />
      <path d="M4.5 9.5a5.5 5.5 0 009.3 4M15.5 9.5c0 .5-.1 1-.2 1.5M10 15v2.5M3 3l14 14" />
    </Icon>
  );
}

export function HangUpIcon() {
  return <Icon><path d="M2.5 11.5c4.2-3.6 10.8-3.6 15 0l-1.8 2.2-3-1.2v-2a9 9 0 00-5.4 0v2l-3 1.2z" /></Icon>;
}
