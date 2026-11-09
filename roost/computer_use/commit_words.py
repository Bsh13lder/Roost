"""The commit test: does this click or key spend, send, submit, accept, delete or change an account?

Signing in is not an account change (owner decision 2026-10-23, ``docs/plans/2026-10-23-roost-tabs-signin-flow.md``
B2): "Log in", "Continue with Google", "Next" are browsing; "Sign up", "Log out" and a password change still ask.

``commit_class`` is pure and fails closed: anything it can't place is ``unknown``, which asks. The
label is read as text (R5: "Boost" is spend, "Submit" is submit), in English and Spanish, casefolded,
accents stripped and matched on whole words, multi-word phrases first. Structure beats the label for a
POST form's submit control, and a cross-origin frame (a payment widget) is always ``unknown``.
See docs/plans/2026-10-22-roost-computers-c3-design.md §6.1."""

from __future__ import annotations

import re
import unicodedata
from typing import Mapping

from roost.computer_use.models import CommitClass, PageTarget

# Order matters only between one-word matches of the same length: the more specific classes come first.
LEXICON: Mapping[CommitClass, tuple[str, ...]] = {
    "spend": (
        "pay", "pay now", "payment", "buy", "buy now", "purchase", "checkout", "check out", "proceed to checkout",
        "order", "order now", "place order", "subscribe", "upgrade", "boost", "bid", "place bid", "credits",
        "donate", "top up", "topup", "add funds", "add credits", "renew",
        "pagar", "pago", "comprar", "comprar ahora", "compra", "tramitar pedido", "realizar pedido", "pedido",
        "suscribirse", "suscribirme", "suscribir", "mejorar", "pujar", "puja", "creditos", "donar", "recargar",
        "anadir fondos", "agregar fondos", "renovar",
    ),
    "send": (
        "send", "send message", "message", "reply", "post", "publish", "share", "invite", "comment", "tweet",
        "enviar", "enviar mensaje", "mensaje", "responder", "publicar", "compartir", "invitar", "comentar",
    ),
    "delete": (
        "delete", "remove", "cancel subscription", "cancel plan", "deactivate", "close account", "delete account",
        "unsubscribe",
        "eliminar", "borrar", "quitar", "cancelar suscripcion", "desactivar", "cerrar cuenta", "darse de baja",
    ),
    # Owner decision 2026-10-23 (B2): signing in is browsing (SIGN_IN_WORDS); creating an account, signing out
    # and changing a plan, a password or an email still ask.
    "account": (
        "save changes", "change plan", "change password", "change email", "update password", "update email",
        "sign up", "create account", "register", "log out", "sign out",
        "guardar cambios", "cambiar plan", "cambiar contrasena", "cambiar correo", "registrarse", "registrate",
        "crear cuenta", "cerrar sesion",
    ),
    "accept": (
        "accept", "accept all", "accept offer", "decline", "reject", "agree", "i agree", "sign", "hire", "offer",
        "contract",
        "aceptar", "aceptar todo", "aceptar oferta", "acepto", "rechazar", "de acuerdo", "firmar", "contratar",
        "oferta", "contrato",
    ),
    "submit": (
        "submit", "confirm", "place", "finish", "complete",
        "solicitar", "confirmar", "finalizar", "terminar", "completar",
    ),
}

# Owner decision 2026-10-23 (B2): signing in is ordinary browsing. These are read only when no committing word
# matched. The strong ones name a sign-in and beat a POST form's structure (a login form posts); the weak ones
# ("Next", "Continue") are browsing only outside a POST form, where a checkout step still asks.
SIGN_IN_WORDS: tuple[str, ...] = (
    "sign in", "log in", "login", "signin", "iniciar sesion", "acceder", "entrar",
    "continue with google", "continue with apple", "continue with email", "continue with microsoft",
    "sign in with google", "sign in with apple", "continuar con google", "continuar con apple",
    "continuar con correo",
)
SIGN_IN_STEP_WORDS: tuple[str, ...] = ("continue", "next", "siguiente", "continuar")

# Owner, 2026-10-25: a pop-up's plain dismiss buttons are browsing, so a bot clears "What's new" or "Turn on
# notifications?" by itself. Only a label that is exactly one of these counts ("OK, delete" still deletes), and
# never a POST form's submit.
DISMISS_WORDS: tuple[str, ...] = (
    "ok", "okay", "got it", "not now", "maybe later", "later", "close", "dismiss", "skip", "no thanks",
    "no thank you", "continue", "x",
    "entendido", "ahora no", "mas tarde", "cerrar", "vale", "omitir", "no gracias", "continuar",
    # Owner, 2026-11-05: starting a search or an unpaid booking over (Wizz Air's "Restart booking" after a timeout).
    "restart", "restart booking", "restart search", "start over", "start again", "new search",
    "empezar de nuevo", "reiniciar", "nueva busqueda",
)

# Owner, 2026-10-31 (W8): "Apply now" on a job page only opens the application form; the form's own submit or send
# button is where it commits. Outside a POST form these are browsing; a POST form's submit stays "submit" by its
# structure. Read only when no committing word matched ("Apply and pay" still spends).
FORM_OPEN_WORDS: tuple[str, ...] = ("apply", "apply now", "aplicar", "postular", "postularse")

# Owner, 2026-10-25: opening a picture, a file preview or more text is looking, not changing. A label that starts
# with one of these, is at most VIEW_LABEL_MAX_WORDS long and says no other action or an account is browsing.
VIEW_WORDS: tuple[str, ...] = (
    "open", "view", "show", "preview", "expand", "play", "zoom", "see",
    "abrir", "ver", "mostrar", "ampliar", "reproducir",
)
VIEW_LABEL_MAX_WORDS = 4
_ACCOUNT_NOUNS = frozenset({"account", "accounts", "cuenta", "cuentas"})

# Inside a cookie or consent banner these keep you browsing (R4); "Accept all" there still asks.
CONSENT_WORDS: tuple[str, ...] = (
    "reject", "reject all", "decline", "only necessary", "necessary only", "essential only", "only essential",
    "use necessary cookies only", "close", "dismiss", "no thanks",
    "rechazar", "rechazar todo", "rechazar todas", "solo necesarias", "solo las necesarias", "cerrar", "no gracias",
)
CONSENT_CONTAINER_MARKS: tuple[str, ...] = (
    "cookie", "cookies", "consent", "gdpr", "privacy", "consentimiento", "privacidad",
)

# Action labels are short and verb-first ("Accept offer", "Send"). A longer label is a content row (a chat, a job,
# a search result): only its first words are read, and a row with no action there is browsing (owner, 2026-10-23).
ACTION_LABEL_MAX_WORDS = 6

_BROWSING_KINDS = frozenset({"link", "tab", "checkbox", "radio", "option", "menuitem", "row", "field"})
_NON_ALNUM = re.compile(r"[^0-9a-z]+")
# Native text boxes: the browser, not the page, says they take typing.
_TEXT_INPUT_TYPES = frozenset({"", "text", "search", "email", "url", "tel", "number", "password"})
_NATIVE_BOX_TAGS = frozenset({"input", "textarea"})
# Controls in their own right: a role or contenteditable on them never makes them a text box.
_CONTROL_TAGS = frozenset({"button", "a", "summary", "select", "option", "label", "details"})
# Words that name a text box rather than an action ("Write a message", "Email"). They are dropped before a
# claimed (non-native) text box's label is read, so a composer stays a text box and "Send message" still sends.
BOX_NAME_WORDS: tuple[str, ...] = (
    "message", "mensaje", "comment", "comentario", "reply", "respuesta", "email", "correo", "password",
    "contrasena",
)
# Fast pages, slice 4: words that make a one-line box a search box by its own label ("Search or start a new chat").
SEARCH_NAME_WORDS: tuple[str, ...] = (
    "search", "find", "filter", "buscar", "busca", "busqueda", "filtrar", "filtro", "encontrar",
)
# Away from a text box these keys are a site's delete shortcuts (mail, files).
_DELETE_KEYS = frozenset({"Delete", "Backspace"})
# Keys that only move, scroll or close (2026-10-25): browsing even with nothing focused. Enter and Space may press
# a control, and Delete and Backspace may delete, so those still need a known target.
_MOVE_KEYS = frozenset({"Escape", "Tab", "Shift+Tab", "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight",
                        "PageUp", "PageDown", "Home", "End", "Back"})


def normalise(text: str) -> str:
    """Casefold, strip accents, keep letters and digits, one space between words."""
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    bare = "".join(char for char in decomposed if not unicodedata.combining(char))
    return _NON_ALNUM.sub(" ", bare).strip()


def _phrases(skip: frozenset[str]) -> tuple[tuple[str, CommitClass], ...]:
    pairs = [(normalise(phrase), cls) for cls, words in LEXICON.items() for phrase in words]
    kept = [(phrase, cls) for phrase, cls in pairs if phrase not in skip]
    return tuple(sorted(kept, key=lambda pair: -len(pair[0].split())))   # stable: lexicon order within a length


_ALL_PHRASES = _phrases(frozenset())
_CONSENT = frozenset(normalise(word) for word in CONSENT_WORDS)
_PHRASES_BUT_CONSENT = _phrases(_CONSENT)
_BOX_NAMES = frozenset(normalise(word) for word in BOX_NAME_WORDS)
_SEARCH_NAMES = frozenset(normalise(word) for word in SEARCH_NAME_WORDS)
_SIGN_IN = tuple(normalise(word) for word in SIGN_IN_WORDS)
_SIGN_IN_STEPS = tuple(normalise(word) for word in SIGN_IN_STEP_WORDS)
_DISMISS = frozenset(normalise(word) for word in DISMISS_WORDS)
# Icon names a page gives its X ("ic-close", "btn-close"): these words are dropped before a dismiss is read.
_VIEW = frozenset(normalise(word) for word in VIEW_WORDS)
_FORM_OPEN = tuple(normalise(word) for word in FORM_OPEN_WORDS)
_ICON_WORDS = frozenset({"ic", "icon", "btn", "button", "svg"})


def _has(label: str, phrase: str) -> bool:
    return f" {phrase} " in f" {label} "


def _lexicon_class(label: str, phrases: tuple[tuple[str, CommitClass], ...] = _ALL_PHRASES) -> CommitClass | None:
    return next((cls for phrase, cls in phrases if _has(label, phrase)), None)


def _without_sign_in(label: str) -> str:
    """The label with its sign-in phrases taken out, so "Sign in" is not read as "sign" (accept)."""
    padded = f" {label} "
    for phrase in _SIGN_IN:
        padded = padded.replace(f" {phrase} ", " ")
    return " ".join(padded.split())


# A chat row's unread count ("2 unread messages", "3 mensajes no leidos") names no action: it is cut before the
# label is read, so opening a WhatsApp chat is not "send" (owner, 2026-10-26).
_UNREAD_COUNT = re.compile(r"(?:\b\d+ )?(?:\bunread messages?\b|\bmensajes? no leidos?\b)")


def _without_unread(label: str) -> str:
    return " ".join(_UNREAD_COUNT.sub(" ", label).split())


def _leading(text: str) -> str:
    """A label's first ``ACTION_LABEL_MAX_WORDS`` words, where an action names itself."""
    return " ".join(text.split()[:ACTION_LABEL_MAX_WORDS])


def _is_content_row(target: PageTarget) -> bool:
    """A long label, or one with an unread count, outside a dialog: a row of content, not an action."""
    texts = (normalise(target.text), normalise(target.visible_text))
    return not target.in_dialog and any(
        len(text.split()) > ACTION_LABEL_MAX_WORDS or _UNREAD_COUNT.search(text) for text in texts)


def _words_class(target: PageTarget, phrases: tuple[tuple[str, CommitClass], ...] = _ALL_PHRASES) -> CommitClass | None:
    """The class its accessible name or its own words say; either may commit (an aria-label can't hide "Pay").
    Only a label's leading words are read, so "… ended the contract" in a chat row is not an action; a long label
    outside a dialog (a content row: an email, a chat, a result) commits only when it starts with the action
    (owner, 2026-11-06: "Gracias por comprar en Alsa" is an email, not a purchase)."""
    for text in (normalise(target.text), normalise(target.visible_text)):
        text = _without_unread(_without_sign_in(text))
        row = not target.in_dialog and len(text.split()) > ACTION_LABEL_MAX_WORDS
        text = _leading(text)
        found = (_starting_class(text, phrases) if row else _lexicon_class(text, phrases)) if text else None
        if found is not None:
            return found
    return None


def _starting_class(label: str, phrases: tuple[tuple[str, CommitClass], ...]) -> CommitClass | None:
    return next((cls for phrase, cls in phrases if f"{label} ".startswith(f"{phrase} ")), None)


def _box_label_class(target: PageTarget) -> CommitClass | None:
    label = " ".join(word for word in normalise(target.text).split() if word not in _BOX_NAMES)
    shown = normalise(target.visible_text)
    return _lexicon_class(label) or (_lexicon_class(shown) if shown else None)


def is_text_box(target: PageTarget) -> bool:
    """A box that takes typing: a native text input or textarea, or an editable area that is not a control
    and whose label names no action. A page's role or contenteditable alone never makes a button a box."""
    if not target.editable:
        return False
    if target.tag in _NATIVE_BOX_TAGS:
        return target.tag == "textarea" or target.input_type in _TEXT_INPUT_TYPES
    if target.tag in _CONTROL_TAGS:
        return False
    return _box_label_class(target) is None


def is_search_box(target: PageTarget) -> bool:
    """A one-line search box by the browser's structure (role searchbox, type=search, a search landmark, a GET
    form): not in a POST form, and its form's submit says nothing that commits. Enter there is browsing."""
    return (is_text_box(target) and target.searchish and target.tag != "textarea" and target.form_method != "post"
            and _lexicon_class(normalise(target.form_submit_text)) is None)


def takes_search_words(target: PageTarget) -> bool:
    """Fast pages, slice 4: a box that takes the bot's own short search words with no card: a structural search box,
    or a one-line box whose own label says search (``search_named``). Owner, 2026-11-03: Enter there is browsing
    too (``_enter_class``); a message box never says search, so it keeps its card."""
    if is_search_box(target):
        return True
    return (is_text_box(target) and target.search_named and target.tag != "textarea"
            and target.form_method != "post" and _lexicon_class(normalise(target.form_submit_text)) is None)


def names_a_search(words: str) -> bool:
    """A box's label or names say search, in English or Spanish, as a whole word."""
    return bool(set(normalise(words).split()) & _SEARCH_NAMES)


def _in_consent_container(target: PageTarget) -> bool:
    dialog = normalise(target.in_dialog)
    return target.in_consent or any(_has(dialog, mark) for mark in CONSENT_CONTAINER_MARKS)


def _consent(target: PageTarget) -> bool:
    label = normalise(target.text)
    if not label or not _in_consent_container(target):
        return False
    said_consent = any(_has(label, word) for word in _CONSENT)
    return said_consent and _words_class(target, _PHRASES_BUT_CONSENT) is None


def _structural(target: PageTarget) -> CommitClass | None:
    if not (target.text.strip() or target.visible_text.strip()) and (target.form_method or target.in_dialog):
        return "unknown"
    if target.expands or target.searchish or target.kind in _BROWSING_KINDS:
        return "browsing"
    return None


def _said(target: PageTarget, phrases: tuple[str, ...]) -> bool:
    """Its accessible name or its own words contain one of ``phrases`` (whole words)."""
    texts = [text for text in (normalise(target.text), normalise(target.visible_text)) if text]
    return any(_has(text, phrase) for text in texts for phrase in phrases)


def _sign_in_class(target: PageTarget, post_submit: bool) -> CommitClass | None:
    """B2: "Log in", "Continue with Google" anywhere, and "Next" / "Continue" outside a POST form, are browsing."""
    if _said(target, _SIGN_IN) or (not post_submit and _said(target, _SIGN_IN_STEPS)):
        return "browsing"
    return None


def _dismisses(target: PageTarget) -> bool:
    """Its whole label (or its own words) is one dismiss word: nothing else is said, so nothing else is done."""
    texts = [text for text in (normalise(target.text), normalise(target.visible_text)) if text]
    bare = [" ".join(word for word in text.split() if word not in _ICON_WORDS) for text in texts]
    return bool(bare) and all(text in _DISMISS for text in bare)


def closes_dialog(target: PageTarget) -> bool:
    """Owner, 2026-11-05: a dialog's own close button: its whole label is one dismiss word ("Cerrar", "X") or a
    consent banner's keep-browsing answer ("Rechazar"), and a click on it commits nothing."""
    return (_dismisses(target) or _consent(target)) and _click_class(target) in ("browsing", "consent")


def _views(target: PageTarget) -> bool:
    """A short label that opens something to look at ("Open picture", "Ver foto"), naming no account."""
    words = normalise(target.text).split()
    return (0 < len(words) <= VIEW_LABEL_MAX_WORDS and words[0] in _VIEW
            and not _ACCOUNT_NOUNS & set(words))


# The Pay card (review 2026-11-06): in a form that holds a card box, a click that sends the form pays, whatever its
# label says ("Continue", "Confirmar"), so it parks on the Pay card.
_CARD_FORM_SENDS: frozenset[str] = frozenset({"submit", "send", "accept"})


def _in_card_form(target: PageTarget, found: CommitClass) -> CommitClass:
    sends = found in _CARD_FORM_SENDS or (found == "unknown" and target.is_form_submit)
    return "spend" if target.form_has_card and sends else found


def _click_class(target: PageTarget) -> CommitClass:
    if is_text_box(target):
        return "browsing"                     # focusing a text box commits nothing; typing is judged on its own
    found = _words_class(target)
    post_submit = target.is_form_submit and target.form_method == "post"
    if found is None:
        found = _sign_in_class(target, post_submit)
    if post_submit:
        return found or "submit"              # structure beats the label, and beats a consent container
    if _consent(target):
        return "consent"
    if found is None and (_is_content_row(target) or _dismisses(target) or _views(target)
                          or _said(target, _FORM_OPEN)):
        return "browsing"
    return found or _structural(target) or "unknown"


def _frame_sign_in(target: PageTarget) -> bool:
    """A frame's button that names a sign-in ("Sign in with Google") and no committing word."""
    return not target.editable and _said(target, _SIGN_IN) and _words_class(target) is None


def _enter_class(target: PageTarget) -> CommitClass:
    """Enter in a text box sends its form: the form's submit label first, then its method."""
    if not is_text_box(target):
        return _click_class(target)
    found = _lexicon_class(normalise(target.form_submit_text))
    if found is not None:
        return found
    if target.form_method == "post":
        return "submit"
    if is_search_box(target) or takes_search_words(target):
        return "browsing"                     # owner, 2026-11-03: a box whose own label says search too
    return "unknown"                          # a lone box or a scripted form may send a chat message on Enter


def commit_class(target: PageTarget | None, *, key: str | None = None) -> CommitClass:
    """The class of a click on ``target`` or of pressing ``key`` while ``target`` has focus."""
    if target is not None and target.cross_origin_frame:
        # a payment widget's frame: even moving keys there are unknown; only a click on a sign-in button that says
        # nothing else is browsing (owner, 2026-11-06: Google's "Iniciar sesión con Google" lives in Google's frame)
        return "browsing" if key is None and _frame_sign_in(target) else "unknown"
    if key in _MOVE_KEYS:
        return "browsing"
    if target is None:
        return "unknown"
    if key is None:
        return _in_card_form(target, _click_class(target))
    if key == "Enter":
        return _in_card_form(target, _enter_class(target))
    if is_text_box(target):
        return "browsing"
    if key == "Space":
        return _click_class(target)
    if key in _DELETE_KEYS:
        return "delete"
    return "browsing"
