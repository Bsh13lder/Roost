"""Plain-sentence words for the keeper's codes and for grant refusals (Shared Contract)."""

from __future__ import annotations

from roost.constants import MAC_GRANTS_MAX, MAC_LABEL_MAX_CHARS

MAC_AWAY_TEXT = "Your Mac's keeper isn't answering right now."
NO_SUCH_BOT_TEXT = "No such bot."
GRANT_NOT_FOUND_TEXT = "Folder not found."
GRANT_LIMIT_TEXT = f"You can share up to {MAC_GRANTS_MAX} folders. Stop sharing one first."
LABEL_BAD_TEXT = f"Give the folder a name of 1 to {MAC_LABEL_MAX_CHARS} characters."
LABEL_TAKEN_TEXT = "You already share a folder called {label}. Pick another name."
PICK_FAILED_TEXT = "The folder window didn't finish. Try again."
_UNKNOWN_TEXT = "Your Mac couldn't do that."
_THAT_FOLDER = "that folder"

# code -> text for a file step; {label} is the grant's name.
MAC_ERROR_TEXTS: dict[str, str] = {
    "off_limits": "That file is off limits.",
    "not_found": "There's no such file in {label}.",
    "not_text": "That's not a text file.",
    "too_big": "That file is over 1 MB.",
    "bad_ext": "I can only write .md, .txt or .csv files.",
    "exists": "A file with that name already exists in {label}.",
    "changed": "The file changed since you read it. Read it again first.",
    "no_grant": "No folder named {label} is shared with you.",
    "read_only": "{label} is read-only for you.",
    "bad_path": "That path isn't allowed.",
    "rate_limited": "Too many Mac file steps in a minute; try again shortly.",
    "not_downloaded": "That file is still in iCloud. Open it on the Mac once so iCloud downloads it.",
    "mac_said_no": "macOS said no. Allow it in System Settings → Privacy & Security → Files and Folders.",
    "pick_failed": PICK_FAILED_TEXT,
}

# code -> text when the user adds a folder (check-folder).
FOLDER_ERROR_TEXTS: dict[str, str] = {
    "off_limits": "That folder is off limits.",
    "not_found": "That folder doesn't exist.",
    "bad_path": "That isn't a folder I can share.",
    "mac_said_no": MAC_ERROR_TEXTS["mac_said_no"],
    "pick_failed": PICK_FAILED_TEXT,
}


def mac_error_text(code: str, label: str | None = None) -> str:
    """The sentence for a keeper code, with ``label`` filled in."""
    return MAC_ERROR_TEXTS.get(code, _UNKNOWN_TEXT).format(label=label or _THAT_FOLDER)


def folder_error_text(code: str) -> str:
    return FOLDER_ERROR_TEXTS.get(code, _UNKNOWN_TEXT)
