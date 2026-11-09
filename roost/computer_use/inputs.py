"""Which pydantic input validates each screen tool's arguments (``extra="forbid"``, ``roost/computer_use/models.py``)."""

from __future__ import annotations

from types import MappingProxyType

from pydantic import BaseModel

from roost.computer_use import tabs
from roost.computer_use.models import (
    ClickIn, LookIn, OpenAppIn, PressKeyIn, ReadPdfIn, ReadTextIn, SavedLoginIn, ScreenshotIn, VaultLoginIn, ScrollIn, TypeIn, WaitReadyIn,
)

TOOL_INPUTS: MappingProxyType[str, type[BaseModel]] = MappingProxyType({
    "look": LookIn, "click": ClickIn, "type": TypeIn, "press_key": PressKeyIn, "scroll": ScrollIn,
    "wait_ready": WaitReadyIn, "read_text": ReadTextIn, "read_pdf": ReadPdfIn, "open_app": OpenAppIn,
    "switch_tab": tabs.TabIn, "close_tab": tabs.TabIn, "use_saved_login": SavedLoginIn, "use_vault_password": VaultLoginIn,
    "send_screenshot": ScreenshotIn,
})
NO_ARGS = frozenset({"list_tabs"})
