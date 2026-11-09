"""What bots and the owner are told about apps, in one place."""

from __future__ import annotations

BAD_NAME = ("That is not a package name. Use a Debian package's exact name: lowercase letters, digits and + . -, "
            "such as gimp or libreoffice-calc.")
DENIED = "{package} can't be installed on a bot's computer."
BUILT_IN = "{package} comes with the computer already, so there is nothing to install."
LINUX_ONLY = "Apps can be installed only on your own Linux computer."
NOT_FOUND = "Debian has no package called {package}."
NOT_DEBIAN = "{package} isn't in Debian's main archive, so it can't be installed."
ALREADY = "{package} is already on this computer."
NOT_MINE = "{package} wasn't installed with install_app, so it can't be removed."
TOO_MANY = "This computer already has the most apps it may have. Remove one first."
WOULD_REMOVE_OTHERS = "Removing {package} would take other software with it, so it was not removed."
BUSY = "All computers are busy right now. Try again in a few minutes."
UNREACHABLE = "The computer couldn't be reached, so nothing changed."
FAILED = "Installing {package} failed. Nothing was added."
REMOVE_FAILED = "Removing {package} failed."
ASK_ONLY = "That needs the owner's Yes on a card first."
BAD_WHY = "Say in one short sentence why you need it (up to {limit} characters)."

INSTALL_TITLE = "{bot} wants to install {package}"
REMOVE_TITLE = "{bot} wants to remove {package}"
INSTALLED = "Installed {package}."
REMOVED = "Removed {package}."
NO_APPS = "No apps installed yet."
APPS_HEADER = "Apps the owner approved on your computer:"

# The routes' details.
APP_NOT_FOUND = "App not found"
BOT_NOT_FOUND = "Bot not found"
