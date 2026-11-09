"""The desk keeper — a separate host process from the gateway.

Runs as ``python -m roost.keeper`` (see ``__main__.py``), binding
``127.0.0.1:18801``. It owns the one thing the gateway (a Docker-friendly
process) should never touch directly: real host resources per bot — a
Brave Browser window over a private CDP pipe (``browsers.py``) and, from a
later task, a workspace container. Every request it accepts is HMAC-signed
(``roost/desk/signing.py`` + ``auth.py``); nothing it does is reachable
without the shared ``keeper_secret``.
"""

from __future__ import annotations
