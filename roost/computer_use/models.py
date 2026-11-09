"""The computer-use tool inputs (pydantic, ``extra="forbid"``) and the frozen resolution of an act.

The model's arguments never carry a resolution: ``ActResolution`` is built from the live page by the
runner and judged by the gate. It rides as JSON (without the crop) in an approval card's sealed steps,
and a Yes re-resolves the page and compares the two with ``same_target``."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass, fields
from typing import Annotated, Any, Literal, Mapping

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    TypeAdapter,
    ValidationError,
    field_validator,
    model_validator,
)

from roost.owner_words.constants import OWNER_WORDS_MAX_CHARS
from roost.constants import (
    SCREENSHOT_CAPTION_MAX,
    VAULT_HOST_MAX_CHARS,
    VAULT_USERNAME_MAX_CHARS,
    CU_APP_NAME_RE,
    CU_AREAS_MAX,
    CU_BOX_TOLERANCE_PX,
    CU_EXPECT_MAX_CHARS,
    CU_KEYS,
    CU_LOOK_TARGETS_MAX,
    CU_OPEN_APP_WHY_MAX,
    CU_OPEN_APPS,
    CU_READ_FIND_MAX,
    CU_READY_TIMEOUT_S,
    CU_SCROLL_DEFAULT_NOTCHES,
    CU_SCROLL_MAX_NOTCHES,
    CU_TARGET_KINDS,
    CU_TARGET_TEXT_MAX,
    CU_TYPE_MAX_CHARS,
    CU_TYPE_TEXT_CONTROLS,
    CU_VIEW_MAX_H,
    CU_VIEW_MAX_W,
)

CommitClass = Literal["browsing", "consent", "spend", "send", "submit", "accept", "delete", "account", "unknown"]
TextSourceKind = Literal["message", "card", "note", "document"]
ActTool = Literal["click", "type", "press_key"]
# Full computer, Step 1: "page" is an act in Brave, resolved from the page; "screen" is an act anywhere else on the
# bot's own computer, with no page to resolve (the runner saw another window in front).
ActSpace = Literal["page", "screen"]

_TARGET_KIND_ERROR = "kind must be one of: " + ", ".join(CU_TARGET_KINDS) + "."
_KEY_ERROR = "That key is not on the list: " + ", ".join(CU_KEYS) + "."
_POINT_KEYS = frozenset({"x", "y"})
_TEXT_CONTROL_ERROR = ("The text may hold line breaks (\\n) and tabs, but no other control characters (no \\r): "
                       "write it as plain text.")


class _ToolIn(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


ExpectText = Annotated[str, StringConstraints(min_length=1, max_length=CU_EXPECT_MAX_CHARS)]
# W2 (docs/plans/2026-10-23-roost-owner-words.md): your own words that asked for this act, quoted exactly.
OwnerWordsText = Annotated[str, StringConstraints(min_length=1, max_length=OWNER_WORDS_MAX_CHARS)]


class TargetIn(_ToolIn):
    text: str = Field(min_length=1, max_length=CU_TARGET_TEXT_MAX)
    kind: str = "any"
    nth: int = Field(1, ge=1, le=20)

    @field_validator("kind")
    @classmethod
    def _known_kind(cls, value: str) -> str:
        if value not in CU_TARGET_KINDS:
            raise ValueError(_TARGET_KIND_ERROR)
        return value


# Fast pages (docs/plans/2026-10-26-roost-fast-pages.md): a control's number in the newest look.
ControlIndex = Annotated[int, Field(ge=1, le=CU_LOOK_TARGETS_MAX)]


class ClickIn(_ToolIn):
    target: TargetIn | None = None
    x: int | None = Field(None, ge=0, le=CU_VIEW_MAX_W)
    y: int | None = Field(None, ge=0, le=CU_VIEW_MAX_H)
    index: ControlIndex | None = None
    expect: ExpectText
    owner_words: OwnerWordsText | None = None

    @model_validator(mode="after")
    def _one_way_to_aim(self) -> "ClickIn":
        has_point = self.x is not None or self.y is not None
        if has_point and (self.x is None or self.y is None):
            raise ValueError("A point needs both x and y.")
        aims = sum((self.target is not None, has_point, self.index is not None))
        if aims != 1:
            raise ValueError("Give one way to aim: an index, a target or a point (x and y).")
        return self


class TextSourceIn(_ToolIn):
    kind: TextSourceKind = Field(alias="from")
    id: str | None = Field(None, min_length=1, max_length=64)


class TypeIn(_ToolIn):
    text: str = Field(min_length=1, max_length=CU_TYPE_MAX_CHARS)
    source: TextSourceIn | None = None      # None: your own short search words, only a search box takes them
    index: ControlIndex | None = None       # a text box from the newest look: it is clicked first
    expect: ExpectText
    owner_words: OwnerWordsText | None = None

    @field_validator("text")
    @classmethod
    def _plain_text(cls, text: str) -> str:
        """Owner, 2026-11-01: a line break (``\\n``) and a tab are text (``type`` pastes; they never press a key);
        any other control character, a carriage return included, is refused."""
        if any(unicodedata.category(char) == "Cc" and char not in CU_TYPE_TEXT_CONTROLS for char in text):
            raise ValueError(_TEXT_CONTROL_ERROR)
        return text


class SavedLoginIn(_ToolIn):
    """``use_saved_login`` (owner, 2026-11-05): the email or user name box from the newest look."""
    index: ControlIndex
    expect: ExpectText


class VaultLoginIn(_ToolIn):
    """``use_vault_password`` (owner, 2026-11-08): the email, user name or password box from the newest look.
    ``login_id``, ``site`` and ``username`` are never offered to the model and a first call ignores them (Roost picks
    the login); they ride only in a card's stored call, where Yes checks them."""
    index: ControlIndex
    expect: ExpectText
    login_id: str | None = Field(default=None, max_length=64)
    site: str | None = Field(default=None, max_length=VAULT_HOST_MAX_CHARS)
    username: str | None = Field(default=None, max_length=VAULT_USERNAME_MAX_CHARS)


class ScreenshotIn(_ToolIn):
    """``send_screenshot`` (owner, 2026-11-05): an optional caption for the picture in your chat."""
    caption: str | None = Field(default=None, max_length=SCREENSHOT_CAPTION_MAX)


class PressKeyIn(_ToolIn):
    key: str
    index: ControlIndex | None = None       # a text box from the newest look: it is clicked first
    expect: ExpectText
    owner_words: OwnerWordsText | None = None

    @field_validator("key")
    @classmethod
    def _listed_key(cls, value: str) -> str:
        if value not in CU_KEYS:
            raise ValueError(_KEY_ERROR)
        return value


class ScrollIn(_ToolIn):
    direction: Literal["up", "down"]
    amount: int = Field(CU_SCROLL_DEFAULT_NOTCHES, ge=1, le=CU_SCROLL_MAX_NOTCHES)
    at: dict[str, int] | None = None
    area: int | None = Field(None, ge=1, le=CU_AREAS_MAX)    # fast pages: inside an area of the newest look

    @model_validator(mode="after")
    def _one_place(self) -> "ScrollIn":
        if self.at is not None and self.area is not None:
            raise ValueError("Give at or area, not both.")
        return self

    @field_validator("at")
    @classmethod
    def _point_on_screen(cls, value: dict[str, int] | None) -> dict[str, int] | None:
        if value is None:
            return None
        if set(value) != _POINT_KEYS:
            raise ValueError("at needs exactly x and y.")
        if not (0 <= value["x"] <= CU_VIEW_MAX_W and 0 <= value["y"] <= CU_VIEW_MAX_H):
            raise ValueError("at must be inside the page.")
        return value


_APP_NAME = re.compile(CU_APP_NAME_RE)
_APP_ERROR = ("app must be one of " + ", ".join(CU_OPEN_APPS)
              + ", or the exact name of an app installed on your computer.")


class OpenAppIn(_ToolIn):
    """Full computer: bring the browser up, or open Files, Terminal, Images or an installed app."""

    app: str = Field(min_length=2, max_length=63)
    why: str | None = Field(None, max_length=CU_OPEN_APP_WHY_MAX)

    @field_validator("app")
    @classmethod
    def _an_app(cls, value: str) -> str:
        if value not in CU_OPEN_APPS and not _APP_NAME.fullmatch(value):
            raise ValueError(_APP_ERROR)
        return value


class ReadTextIn(_ToolIn):
    """Fast pages: read the page's text, or one area's from the newest look, from ``start`` or only where ``find``."""

    area: int | None = Field(None, ge=1, le=CU_AREAS_MAX)
    start: int = Field(0, ge=0)
    find: str | None = Field(None, min_length=1, max_length=CU_READ_FIND_MAX)


class ReadPdfIn(_ToolIn):
    """Fast pages: read the PDF a numbered link goes to, or (no index) the PDF open in the tab."""

    index: ControlIndex | None = None
    start: int = Field(0, ge=0)
    find: str | None = Field(None, min_length=1, max_length=CU_READ_FIND_MAX)


class LookIn(_ToolIn):
    picture: bool = True                    # False: the text summary only (fast pages, slice 6)


class WaitReadyIn(_ToolIn):
    timeout_s: float = Field(CU_READY_TIMEOUT_S, gt=0, le=CU_READY_TIMEOUT_S)


@dataclass(frozen=True)
class Box:
    """A box in viewport CSS pixels."""

    x: float
    y: float
    width: float
    height: float

    def center(self) -> tuple[int, int]:
        return round(self.x + self.width / 2), round(self.y + self.height / 2)


@dataclass(frozen=True)
class PageTarget:
    """One control the resolver found on the page."""

    node_id: int
    kind: str
    text: str
    tag: str
    input_type: str
    box: Box
    form_method: str
    form_submit_text: str
    is_form_submit: bool
    link_host: str
    in_dialog: str
    in_consent: bool
    cross_origin_frame: bool
    editable: bool
    secret_field: bool       # password, one-time-code, autocomplete=current-password/new-password/one-time-code
    searchish: bool          # role=searchbox, type=search, or inside a GET form
    expands: bool            # aria-expanded / aria-haspopup / role=tab
    visible_text: str = ""   # the words inside it when an aria-label names it otherwise ("" for text boxes)
    sign_in_box: bool = False  # B3: a sign-in page's email or user-name box (autocomplete=username, a password form)
    focused: bool = False      # fast pages: it has the keyboard focus (a look says so; boxes are greyed out)
    search_named: bool = False  # fast pages: a one-line box whose own label or placeholder says search / buscar
    form_has_card: bool = False  # the Pay card: its form holds a card box, so a committing click there pays
    card_field: str = ""        # the Pay card, P1: the card part a box holds (number, exp, cvc, name…); a secret box


@dataclass(frozen=True)
class ActResolution:
    tool: ActTool
    url: str
    host: str
    target: PageTarget | None          # None: nothing resolvable (unknown)
    point: tuple[int, int] | None      # viewport px where the click lands
    covered_by: str                    # "" or the covering dialog's title
    nav_host: str                      # "" or the host a link/form would go to
    commit: CommitClass
    text_ok: bool | None = None        # type only: from an approved source
    text_flags: frozenset[str] = frozenset()   # {"contact", "secret"}
    refusal: str = ""                  # a plain-sentence never (password box, outside the page, file picker…)
    crop: bytes = b""                  # JPEG for the card; never in the audit, never in the JSON
    space: ActSpace = "page"           # "screen": not in Brave (full computer, D1)
    owner_words: str = ""              # W2: the act's quote of your request, only when it checked out as yours
    approved_again: bool = False       # W10: you said Yes to this very control on a card in this chat, just now
    own_text: bool = False             # a box on the page holds text that isn't your words (the Send card shows it)


_RESOLUTION = TypeAdapter(ActResolution)
_RESOLUTION_FIELDS = frozenset(f.name for f in fields(ActResolution)) - {"crop"}
_TARGET_FIELDS = frozenset(f.name for f in fields(PageTarget))
_BOX_FIELDS = frozenset(f.name for f in fields(Box))


def resolution_to_json(r: ActResolution) -> dict[str, Any]:
    """The resolution as plain JSON, without the crop (the crop rides apart, sealed, on the card)."""
    data = {name: value for name, value in asdict(r).items() if name != "crop"}
    data["point"] = list(r.point) if r.point is not None else None
    data["text_flags"] = sorted(r.text_flags)
    return data


def _check_keys(data: Mapping[str, Any], allowed: frozenset[str], what: str) -> None:
    unknown = set(data) - allowed
    if unknown:
        raise ValueError(f"The stored {what} has fields it should not: {', '.join(sorted(unknown))}.")


def resolution_from_json(data: Mapping[str, Any]) -> ActResolution:
    """Rebuild a stored resolution; anything unknown or malformed is a ValueError."""
    _check_keys(data, _RESOLUTION_FIELDS, "resolution")
    target = data.get("target")
    if isinstance(target, Mapping):
        _check_keys(target, _TARGET_FIELDS, "target")
        box = target.get("box")
        if isinstance(box, Mapping):
            _check_keys(box, _BOX_FIELDS, "box")
    try:
        return _RESOLUTION.validate_python(dict(data), strict=False)
    except ValidationError as exc:
        raise ValueError("The stored resolution is not valid.") from exc


def _near(a: float, b: float, tol: int) -> bool:
    return abs(a - b) <= tol


def _boxes_near(a: Box, b: Box, tol: int) -> bool:
    return all(_near(x, y, tol) for x, y in ((a.x, b.x), (a.y, b.y), (a.width, b.width), (a.height, b.height)))


def _points_near(a: tuple[int, int] | None, b: tuple[int, int] | None, tol: int) -> bool:
    if a is None or b is None:
        return a is b
    return _near(a[0], b[0], tol) and _near(a[1], b[1], tol)


def _page_address(url: str) -> str:
    """The page's address without its ``#fragment`` (scrolling to a section is the same page)."""
    return url.split("#", 1)[0]


# Owner, 2026-11-03: Upwork relabels "Send for 14 Connects" to "Send for 12 Connects" while a card waits. For these
# classes a count in the label may change (the class itself must not); a Pay button's price never may.
COUNT_FREE_CLASSES: frozenset[str] = frozenset({"send", "submit", "accept"})
_LABEL_FIELDS = ("text", "form_submit_text", "visible_text")
_SAME_FIELDS = ("kind", "tag", "input_type", "form_method", "is_form_submit", "link_host", "in_dialog", "in_consent",
                "cross_origin_frame", "editable", "secret_field")
_DIGITS = re.compile(r"\d+")


def without_counts(text: str) -> str:
    """A label with every number in it made the same ("Send for 14 Connects" -> "Send for # Connects")."""
    return _DIGITS.sub("#", text)


def _label_key(text: str, counts_free: bool) -> str:
    return without_counts(text) if counts_free else text


def _same_control(a: PageTarget, b: PageTarget, *, counts_free: bool = False) -> bool:
    if not all(getattr(a, name) == getattr(b, name) for name in _SAME_FIELDS):
        return False
    return all(_label_key(getattr(a, name), counts_free) == _label_key(getattr(b, name), counts_free)
               for name in _LABEL_FIELDS)


def same_target(a: ActResolution, b: ActResolution, tol: int = CU_BOX_TOLERANCE_PX) -> bool:
    """True only when ``b`` names the same control as ``a``: same page address (a ``#fragment`` aside), host,
    label (a count in a send, submit or accept label aside), structure and class,
    with the box and point moved by at most ``tol`` pixels. Nothing resolvable is never the same."""
    if a.target is None or b.target is None:
        return False
    if _page_address(a.url) != _page_address(b.url):
        return False
    if (a.tool, a.host, a.nav_host, a.commit, a.covered_by) != (b.tool, b.host, b.nav_host, b.commit, b.covered_by):
        return False
    counts_free = a.commit in COUNT_FREE_CLASSES
    return (_same_control(a.target, b.target, counts_free=counts_free) and _boxes_near(a.target.box, b.target.box, tol)
            and _points_near(a.point, b.point, tol))
