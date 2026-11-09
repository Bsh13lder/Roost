"""Serve the built web SPA (``web/dist``) at ``/`` with client-side
routing fallback — see the contract's Task 12 brief ("Modify
``roost/gateway/routes/static.py`` + ``app.py`` to serve ``web/dist``
at ``/`` with SPA fallback (only when ``web/dist`` exists)").

Only mounted when ``web/dist`` actually exists on disk (``create_app``
checks ``web_dist_exists()`` before calling ``mount_static``, see its
one-line edit) — a dev checkout that never ran ``make web`` has no
``dist/`` yet, and the gateway must still start cleanly for the Python
test suite, which never builds the frontend.

``/api/*`` is never shadowed by this, on two levels: FastAPI matches
routers in registration order, and ``create_app`` always includes the
API routers before calling ``mount_static`` (see ``app.py``), so a path
some router actually handles never reaches this mount at all. And for
an ``/api/...`` path no router handles (a route removed, or never
written) — which does land here, since the mount sits at ``/`` —
``_SpaStaticFiles.get_response`` re-raises its own 404 instead of
falling back to ``index.html``, so FastAPI's normal 404 still answers
rather than the SPA shell lying about the route's existence.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException
from starlette.types import Scope

from roost.constants import SPA_CONTENT_SECURITY_POLICY


def _web_dist_dir() -> Path:
    """``web/dist``, resolved relative to the repo root (three levels up
    from this file: ``roost/gateway/routes/static.py``)."""
    return Path(__file__).resolve().parents[3] / "web" / "dist"


class _SpaStaticFiles(StaticFiles):
    """``StaticFiles`` that falls back to ``index.html`` for any GET/HEAD
    that would otherwise 404, so a client-side route (``/bots/abc``, a
    reload on ``/bots/abc/desk``, ...) still loads the SPA shell
    instead of a raw 404 — ``main.tsx``'s router then resolves the path
    itself from ``window.location``.

    Only a plain 404 on a non-``/api`` path is caught and rewritten.
    Every other outcome (405 on a non-GET/HEAD method, 401 on a
    permission error, a 404 under ``/api/...``) is re-raised unchanged —
    a real server error, or a missing API route, should never be masked
    as "here's the homepage".

    Every response carries the SPA's Content-Security-Policy (no remote images).
    """

    async def get_response(self, path: str, scope: Scope):  # type: ignore[override]
        try:
            response = await super().get_response(path, scope)
        except HTTPException as exc:
            # S1 Task 1 fix round 1, finding 1: this mount sits at "/" and
            # StaticFiles.get_path strips the leading slash, so an API path
            # with no matching router (a route deleted or not yet written)
            # reaches here too, not just real static misses. Re-raise those
            # so FastAPI's own 404 answers instead of the SPA shell.
            if exc.status_code != 404 or path == "api" or path.startswith("api/"):
                raise
            response = FileResponse(Path(str(self.directory)) / "index.html")
        response.headers["Content-Security-Policy"] = SPA_CONTENT_SECURITY_POLICY
        return response


def web_dist_exists() -> bool:
    """Whether ``web/dist/index.html`` exists — the guard ``create_app``
    checks before calling ``mount_static`` (a dev/test checkout that
    never ran ``make web`` has no built frontend yet)."""
    return (_web_dist_dir() / "index.html").is_file()


def mount_static(app: FastAPI) -> None:
    """Mount the built SPA at ``/``. Caller must check
    ``web_dist_exists()`` first — see this module's docstring. Mounted
    last (after every ``/api/...`` router): a FastAPI ``Mount`` only
    matches once nothing registered earlier already has, so this never
    shadows the API."""
    app.mount("/", _SpaStaticFiles(directory=_web_dist_dir(), html=True), name="web")


def mount_static_if_built(app: FastAPI) -> bool:
    """``mount_static(app)``, but only when ``web/dist`` has actually
    been built — the one call ``create_app`` needs (see ``app.py``) to
    stay a no-op for a Python-only checkout. Returns whether it mounted,
    which is all a caller could otherwise learn by re-checking
    ``web_dist_exists()`` itself."""
    if not web_dist_exists():
        return False
    mount_static(app)
    return True
