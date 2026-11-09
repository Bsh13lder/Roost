"""What the keeper holds for the Mac file API: the home folder it judges against, the grants
(memory only), the per-bot rate limiter, the picker and the backups. ``create_app`` builds one as ``app.state.mac``."""

from __future__ import annotations

import hashlib
import hmac
import os

from roost.config import RoostConfig
from roost.keeper.macfs.backups import Backups
from roost.keeper.macfs.grants import GrantRegistry
from roost.keeper.macfs.limits import OpsLimiter
from roost.keeper.macfs.picker import FolderPicker

_BACKUP_KEY_LABEL = b"roost:mac-backup:v1"


class MacFs:
    def __init__(self, config: RoostConfig) -> None:
        self.home = os.path.realpath(config.mac_home)
        self.registry = GrantRegistry(self.home)
        self.limiter = OpsLimiter()
        self.picker = FolderPicker(home=self.home)
        key = hmac.new(config.keeper_secret.encode(), _BACKUP_KEY_LABEL, hashlib.sha256).digest()
        self.backups = Backups(config.mac_backups_dir, key)
