"""Shared rig for the keeper's Mac file API tests: the real keeper app in process, a fake home under
tmp_path, one grant on ``home/Notes``. No test here touches a real home folder."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from fastapi.testclient import TestClient

from roost.config import RoostConfig
from roost.desk.signing import signed_headers
from roost.keeper.app import create_app

SECRET = "k" * 32
BOT_A = "11111111-1111-4111-8111-111111111111"
BOT_B = "22222222-2222-4222-8222-222222222222"
GRANT_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"


@dataclass
class MacRig:
    app: object
    client: TestClient
    home: Path
    root: Path
    config: RoostConfig

    def call(self, method: str, path: str, body: dict | None = None, *, sign: bool = True):
        raw = json.dumps(body if body is not None else {}).encode()
        headers = signed_headers(SECRET, method, path, raw) if sign else {}
        headers["content-type"] = "application/json"
        return self.client.request(method, path, content=raw, headers=headers)

    def fs(self, route: str, body: dict | None = None, *, bot_id: str = BOT_A, grant_id: str = GRANT_ID):
        payload = {"grant_id": grant_id, "bot_id": bot_id, **(body or {})}
        return self.call("POST", f"/mac/fs/{route}", payload)

    def push(self, *grants: dict):
        return self.call("PUT", "/mac/grants", {"grants": list(grants)})

    def grant(self, root: Path | None = None, *, access: str = "read_write", bot_id: str | None = None,
              grant_id: str = GRANT_ID) -> dict:
        return {"grant_id": grant_id, "root": str(root or self.root), "access": access, "bot_id": bot_id}

    def audit_lines(self) -> list[dict]:
        log = self.config.database_dir / "keeper-audit.log"
        return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []


def build_rig(tmp_path: Path, *, access: str = "read_write", push: bool = True) -> MacRig:
    base = tmp_path.resolve()
    home = base / "home"
    root = home / "Notes"
    root.mkdir(parents=True)
    config = RoostConfig(
        server_secret="x" * 32, database_dir=base / "data", desks_dir=base / "desks", keeper_secret=SECRET,
        mac_home=home, mac_backups_dir=base / "backups",
    )
    app = create_app(config)
    rig = MacRig(app, TestClient(app), home, root, config)
    if push:
        assert rig.push(rig.grant(access=access)).status_code == 200
    return rig
