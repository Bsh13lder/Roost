"""The keeper's signed Mac file routes (``register_mac_routes``).

Every handler follows one order: the signature (``require_signed_body``, 401), the strict body
(422, never echoing input), the grant lookup, the per-bot rate limit, the operation in a worker
thread with the grant's root opened by file descriptor, and one audit line with ids and the
result code only. No handler starts a process except ``pick-folder``'s fixed argv.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Callable

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, RootModel, ValidationError

from roost.keeper.auth import require_signed_body
from roost.keeper.macfs import find as find_module
from roost.keeper.macfs import models as m
from roost.keeper.macfs import ops_read, ops_write
from roost.keeper.macfs.errors import MacFsError
from roost.keeper.macfs.grants import KeeperGrant
from roost.keeper.macfs.paths import split_rel
from roost.keeper.macfs.picker import FolderPickError

log = logging.getLogger(__name__)

_NO_BOT = "-"
_STATUS = {
    "off_limits": 403, "not_found": 404, "not_text": 415, "too_big": 413, "bad_ext": 415, "exists": 409,
    "changed": 409, "no_grant": 403, "grants_unset": 503, "read_only": 403, "bad_path": 400,
    "rate_limited": 429, "not_downloaded": 409, "mac_said_no": 403,
}

Op = Callable[[Any, KeeperGrant, int, Any], dict[str, Any]]


def parse_body(model: type[BaseModel], body: bytes) -> Any:
    """Validate a body; the 422 names fields and error types only, never the values sent."""
    try:
        return model.model_validate_json(body or b"{}")
    except ValidationError as exc:
        detail = [{"loc": list(e["loc"]), "type": e["type"]} for e in exc.errors(include_input=False, include_url=False)]
        raise HTTPException(status_code=422, detail=detail) from None


def http_error(exc: MacFsError) -> HTTPException:
    detail: dict[str, Any] = {"code": exc.code}
    if exc.current_sha256 is not None:
        detail["current_sha256"] = exc.current_sha256
    return HTTPException(status_code=_STATUS.get(exc.code, 400), detail=detail)


def _with_root(mac, grant: KeeperGrant, request, op: Op) -> dict[str, Any]:
    root_fd = mac.registry.open_root(grant)
    try:
        return op(mac, grant, root_fd, request)
    finally:
        os.close(root_fd)


async def run_fs(app: FastAPI, body: bytes, model: type[m.FsIn], action: str, op: Op) -> dict[str, Any]:
    request = parse_body(model, body)
    wrapper = request
    if isinstance(request, RootModel):
        request = request.root   # undo: a union told apart by ``kind``; the op reads the wrapper
    mac, audit = app.state.mac, app.state.audit
    try:
        grant = mac.registry.lookup(request.grant_id, request.bot_id)
        mac.limiter.take(request.bot_id)
        result = await asyncio.to_thread(_with_root, mac, grant, wrapper, op)
    except MacFsError as exc:
        audit.record(action, request.bot_id, exc.code, grant_id=request.grant_id)
        raise http_error(exc) from None
    except Exception as exc:  # an I/O failure we did not map: log its type only, never a path
        log.warning("mac file step failed: %s", type(exc).__name__)
        audit.record(action, request.bot_id, "error", grant_id=request.grant_id)
        raise HTTPException(status_code=500, detail={"code": "io_error"}) from None
    size = result.get("size")
    audit.record(action, request.bot_id, "ok", grant_id=request.grant_id, size=size if isinstance(size, int) else None)
    return result


def _find_op(mac, grant: KeeperGrant, root_fd: int, body: m.FindIn) -> dict[str, Any]:
    query = find_module.FindQuery(body.name, body.text, split_rel(body.path))
    found = find_module.find(grant, root_fd, query, lambda: mac.registry.generation, home=mac.home)
    return {"hits": list(found.hits), "truncated": found.truncated}


def _register_grant_routes(app: FastAPI) -> None:
    @app.put("/mac/grants")
    async def put_grants(body: bytes = Depends(require_signed_body)):
        request = parse_body(m.PutGrantsIn, body)
        mac = app.state.mac
        try:
            grants = await asyncio.to_thread(ops_read.build_grants, mac.home, request.grants)
        except ops_read.BadGrant as exc:
            app.state.audit.record("mac_grants", _NO_BOT, "bad_grant")
            raise HTTPException(status_code=422, detail={"code": "bad_grant", "grant_id": exc.grant_id}) from None
        mac.registry.replace(grants)
        app.state.audit.record("mac_grants", _NO_BOT, "ok", size=len(grants))
        return {"count": len(grants)}

    @app.post("/mac/check-folder")
    async def check_folder(body: bytes = Depends(require_signed_body)):
        request = parse_body(m.CheckFolderIn, body)
        try:
            result = await asyncio.to_thread(ops_read.check_folder, app.state.mac.home, request.path)
        except MacFsError as exc:
            app.state.audit.record("mac_check", _NO_BOT, exc.code)
            raise http_error(exc) from None
        app.state.audit.record("mac_check", _NO_BOT, "ok")
        return result

    @app.post("/mac/pick-folder")
    async def pick_folder(body: bytes = Depends(require_signed_body)):
        parse_body(m.EmptyIn, body)
        try:
            picked = await app.state.mac.picker.pick()
        except MacFsError as exc:
            app.state.audit.record("mac_pick", _NO_BOT, exc.code)
            raise http_error(exc) from None
        except FolderPickError:
            app.state.audit.record("mac_pick", _NO_BOT, "pick_failed")
            raise HTTPException(status_code=503, detail={"code": "pick_failed"}) from None
        app.state.audit.record("mac_pick", _NO_BOT, "ok" if picked else "cancelled")
        return {"path": picked}


def _register_read_routes(app: FastAPI) -> None:
    @app.post("/mac/fs/list")
    async def fs_list(body: bytes = Depends(require_signed_body)):
        return await run_fs(app, body, m.ListIn, "mac_list", ops_read.list_folder)

    @app.post("/mac/fs/find")
    async def fs_find(body: bytes = Depends(require_signed_body)):
        return await run_fs(app, body, m.FindIn, "mac_find", _find_op)

    @app.post("/mac/fs/read")
    async def fs_read(body: bytes = Depends(require_signed_body)):
        return await run_fs(app, body, m.ReadIn, "mac_read", ops_read.read_file)

    @app.post("/mac/fs/stat")
    async def fs_stat(body: bytes = Depends(require_signed_body)):
        return await run_fs(app, body, m.StatIn, "mac_stat", ops_read.stat_files)


def _register_write_routes(app: FastAPI) -> None:
    @app.post("/mac/fs/create")
    async def fs_create(body: bytes = Depends(require_signed_body)):
        return await run_fs(app, body, m.CreateIn, "mac_create", ops_write.create_file)

    @app.post("/mac/fs/write")
    async def fs_write(body: bytes = Depends(require_signed_body)):
        return await run_fs(app, body, m.WriteIn, "mac_write", ops_write.write_file)

    @app.post("/mac/fs/rename")
    async def fs_rename(body: bytes = Depends(require_signed_body)):
        return await run_fs(app, body, m.RenameIn, "mac_rename", ops_write.rename_file)

    @app.post("/mac/fs/trash")
    async def fs_trash(body: bytes = Depends(require_signed_body)):
        return await run_fs(app, body, m.TrashIn, "mac_trash", ops_write.trash_file)

    @app.post("/mac/fs/undo")
    async def fs_undo(body: bytes = Depends(require_signed_body)):
        return await run_fs(app, body, m.UndoIn, "mac_undo", ops_write.undo)


def register_mac_routes(app: FastAPI) -> None:
    _register_grant_routes(app)
    _register_read_routes(app)
    _register_write_routes(app)
