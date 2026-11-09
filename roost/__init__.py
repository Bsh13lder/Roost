"""Roost — a personal AI team for Claude users, self-hosted and encrypted at rest.

Each bot gets its own computer: its own Brave window and its own workspace
container. Night-1 walking skeleton: read-only bots, loopback-only
listeners, no phone pairing yet.
"""

from importlib.metadata import PackageNotFoundError, version as _pkg_version

try:
    __version__ = _pkg_version("roost")
except PackageNotFoundError:
    __version__ = "0.0.0+dev"
