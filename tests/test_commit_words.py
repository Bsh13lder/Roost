"""C3 Task 1: the commit test that tells a Buy or Send button from browsing."""

from __future__ import annotations

from roost.computer_use.commit_words import LEXICON, commit_class, is_search_box, is_text_box, normalise
from roost.computer_use.models import Box, PageTarget


def _t(text: str, kind: str = "button", **over: object) -> PageTarget:
    fields: dict[str, object] = dict(
        node_id=1, kind=kind, text=text, tag="button" if kind == "button" else "a", input_type="",
        box=Box(0, 0, 50, 20), form_method="", form_submit_text="", is_form_submit=False, link_host="",
        in_dialog="", in_consent=False, cross_origin_frame=False, editable=False, secret_field=False,
        searchish=False, expands=False,
    )
    fields.update(over)
    return PageTarget(**fields)  # type: ignore[arg-type]


def _field(**over: object) -> PageTarget:
    fields: dict[str, object] = {"tag": "input", "input_type": "text", "editable": True, **over}
    return _t("Title", kind="field", **fields)


def test_normalise_strips_accents_case_and_punctuation() -> None:
    assert normalise("  Añadir   FONDOS! ") == "anadir fondos"
    assert normalise("Désactiver") == "desactiver"


def test_lexicon_has_every_committing_class() -> None:
    assert set(LEXICON) == {"spend", "send", "submit", "accept", "delete", "account"}


def test_buy_words_are_spend_in_english_and_spanish() -> None:
    for label in ("Comprar ahora", "Buy now", "Añadir fondos", "Pagar", "Top up", "Proceed to checkout"):
        assert commit_class(_t(label)) == "spend", label


def test_words_are_matched_whole_not_inside_other_words() -> None:
    assert commit_class(_t("Buyer guide", kind="link")) == "browsing"
    assert commit_class(_t("Sendero", kind="link")) == "browsing"


def test_boost_is_spend_and_submit_is_submit() -> None:
    assert commit_class(_t("Boost")) == "spend"
    assert commit_class(_t("Submit")) == "submit"
    assert commit_class(_t("Submit a proposal")) == "submit"


def test_other_classes_in_english_and_spanish() -> None:
    assert commit_class(_t("Send message")) == "send"
    assert commit_class(_t("Enviar")) == "send"
    assert commit_class(_t("Eliminar")) == "delete"
    assert commit_class(_t("Cancel subscription")) == "delete"
    assert commit_class(_t("Aceptar oferta")) == "accept"
    assert commit_class(_t("Save changes")) == "account"


def test_a_post_form_submit_is_submit_whatever_its_label() -> None:
    assert commit_class(_t("Next", form_method="post", is_form_submit=True)) == "submit"
    assert commit_class(_t("Siguiente", form_method="post", is_form_submit=True)) == "submit"


def test_a_get_search_form_is_browsing() -> None:
    button = _t("Search", form_method="get", is_form_submit=True, searchish=True)
    assert commit_class(button) == "browsing"
    box = _field(form_method="get", form_submit_text="Search", searchish=True)
    assert commit_class(box, key="Enter") == "browsing"


def test_accept_all_in_a_cookie_banner_asks_but_reject_is_consent() -> None:
    banner = {"in_dialog": "We use cookies", "in_consent": True}
    assert commit_class(_t("Accept all", **banner)) == "accept"
    assert commit_class(_t("Reject all", **banner)) == "consent"
    assert commit_class(_t("Only necessary", **banner)) == "consent"
    assert commit_class(_t("Rechazar todo", **banner)) == "consent"
    assert commit_class(_t("Close", in_dialog="Cookie settings")) == "consent"
    assert commit_class(_t("Reject and pay", **banner)) == "spend"


def test_decline_outside_a_banner_is_accept_class() -> None:
    assert commit_class(_t("Decline")) == "accept"
    assert commit_class(_t("Reject offer", in_dialog="Offer from client")) == "accept"


def test_icon_only_in_a_dialog_is_unknown() -> None:
    assert commit_class(_t("", in_dialog="Confirm your order")) == "unknown"
    assert commit_class(_t("", form_method="get")) == "unknown"


def test_cross_origin_frame_is_unknown() -> None:
    assert commit_class(_t("Next", cross_origin_frame=True)) == "unknown"
    assert commit_class(_field(cross_origin_frame=True), key="Tab") == "unknown"


def test_no_target_is_unknown() -> None:
    assert commit_class(None) == "unknown"
    assert commit_class(None, key="Enter") == "unknown"


def test_menus_tabs_and_links_are_browsing() -> None:
    assert commit_class(_t("Filters", expands=True)) == "browsing"
    assert commit_class(_t("Reviews", kind="tab")) == "browsing"
    assert commit_class(_t("Find work", kind="link")) == "browsing"
    assert commit_class(_t("Remote only", kind="checkbox")) == "browsing"
    assert commit_class(_t("Newest", kind="option")) == "browsing"
    assert commit_class(_t("Settings", kind="menuitem")) == "browsing"
    assert commit_class(_t("Do the thing")) == "unknown"


def test_focusing_a_field_is_browsing_whatever_its_label() -> None:
    assert commit_class(_t("Email", kind="field", tag="input", editable=True)) == "browsing"


def test_enter_in_a_post_form_takes_the_forms_class() -> None:
    assert commit_class(_field(form_method="post", form_submit_text="Next"), key="Enter") == "submit"
    assert commit_class(_field(form_method="post", form_submit_text="Pay now"), key="Enter") == "spend"
    assert commit_class(_field(form_method="get", form_submit_text="Send"), key="Enter") == "send"


def test_enter_in_a_lone_field_is_unknown_and_other_keys_browse() -> None:
    assert commit_class(_field(), key="Enter") == "unknown"
    assert commit_class(_field(tag="textarea", searchish=True), key="Enter") == "unknown"
    assert commit_class(_field(), key="Tab") == "browsing"
    assert commit_class(_field(), key="PageDown") == "browsing"


def test_space_on_a_button_is_the_buttons_class() -> None:
    assert commit_class(_t("Buy now"), key="Space") == "spend"
    assert commit_class(_t("Filters", expands=True), key="Space") == "browsing"
    assert commit_class(_t("Next", form_method="post", is_form_submit=True), key="Enter") == "submit"
    assert commit_class(_field(), key="Space") == "browsing"


# -- security review (a) after Task 10 ------------------------------------------------------------------------


def test_a_page_role_cannot_make_a_buy_button_a_text_box() -> None:
    # <button role="textbox">Buy now</button>: the role is the page's word, the tag is the browser's.
    fake = _t("Buy now", tag="button", editable=True)
    assert not is_text_box(fake)
    assert commit_class(fake) == "spend"
    assert commit_class(fake, key="Space") == "spend"
    assert commit_class(fake, key="Enter") == "spend"
    # A div that only claims to be a text box is judged by its label.
    assert commit_class(_t("Buy now", kind="field", tag="div", editable=True)) == "spend"
    assert commit_class(_t("Send message", kind="field", tag="div", editable=True)) == "send"


def test_a_real_composer_is_still_a_text_box() -> None:
    assert commit_class(_t("Write a message", kind="field", tag="div", editable=True)) == "browsing"
    assert commit_class(_t("Message #general", kind="field", tag="div", editable=True)) == "browsing"
    assert commit_class(_t("Email", kind="field", tag="input", input_type="email", editable=True)) == "browsing"
    assert commit_class(_t("Comment", kind="field", tag="textarea", editable=True)) == "browsing"
    assert not is_text_box(_t("Pay", kind="field", tag="input", input_type="submit", editable=True))


def test_an_aria_label_cannot_hide_what_the_button_says() -> None:
    assert commit_class(_t("Next page", kind="link", visible_text="Pay now")) == "spend"
    assert commit_class(_t("Read more", visible_text="Comprar ahora")) == "spend"
    assert commit_class(_t("Pay now", kind="link", visible_text="Next page")) == "spend"
    assert commit_class(_t("Next page", kind="link", visible_text="Next page")) == "browsing"


def test_a_post_submit_in_a_cookie_box_is_still_submit() -> None:
    banner = {"in_dialog": "Cookie settings", "in_consent": True, "form_method": "post", "is_form_submit": True}
    for label in ("Close", "Dismiss", "No thanks", "Decline", "Reject all"):
        assert commit_class(_t(label, **banner)) not in ("consent", "browsing"), label
    assert commit_class(_t("Close", **banner)) == "submit"


def test_a_consent_label_over_a_buy_button_is_not_consent() -> None:
    banner = {"in_dialog": "We use cookies", "in_consent": True}
    assert commit_class(_t("Reject all", visible_text="Buy now", **banner)) not in ("consent", "browsing")
    assert commit_class(_t("Reject all", visible_text="Reject all", **banner)) == "consent"


def test_enter_in_a_box_whose_form_says_send_is_send_even_if_searchish() -> None:
    chat = _field(form_method="get", form_submit_text="Send", searchish=True)
    assert commit_class(chat, key="Enter") == "send"
    assert not is_search_box(chat)
    assert is_search_box(_field(form_method="get", form_submit_text="Search", searchish=True))
    assert is_search_box(_field(input_type="search", searchish=True))
    assert not is_search_box(_field(tag="textarea", searchish=True))
    assert not is_search_box(_field(form_method="post", searchish=True))
    assert not is_search_box(_t("Go", searchish=True))


def test_delete_keys_outside_a_text_box_ask() -> None:
    row = _t("Invoice from Ana", kind="link")
    assert commit_class(row, key="Delete") == "delete"
    assert commit_class(row, key="Backspace") == "delete"
    assert commit_class(row, key="Tab") == "browsing"
    assert commit_class(row, key="ArrowDown") == "browsing"
    assert commit_class(_field(), key="Delete") == "browsing"
    assert commit_class(_field(), key="Backspace") == "browsing"
    assert commit_class(_t("Buy now", tag="button", editable=True), key="Delete") == "delete"


# --- Owner decision 2026-10-23 (B2): signing in is browsing, not an account change ---------------------------

def test_sign_in_words_are_browsing_buttons_and_links() -> None:
    for label in ("Log in", "Sign in", "Login", "Iniciar sesión", "Continue", "Next", "Siguiente", "Continuar",
                  "Continue with Google", "Continue with Apple", "Continue with email", "Acceder"):
        assert commit_class(_t(label)) == "browsing", label
        assert commit_class(_t(label, kind="link")) == "browsing", label


def test_a_sign_in_button_in_a_post_form_is_browsing() -> None:
    for label in ("Sign in", "Log in", "Iniciar sesión", "Continue with Google"):
        assert commit_class(_t(label, form_method="post", is_form_submit=True)) == "browsing", label


def test_creating_an_account_and_changing_it_still_ask() -> None:
    for label in ("Sign up", "Registrarse", "Create account", "Crear cuenta", "Log out", "Cerrar sesión",
                  "Save changes", "Change plan", "Change password", "Change email", "Cambiar contraseña"):
        assert commit_class(_t(label)) == "account", label


def test_committing_words_beat_the_sign_in_words() -> None:
    assert commit_class(_t("Continue to payment")) == "spend"
    assert commit_class(_t("Sign up and continue")) == "account"
    assert commit_class(_t("Next", form_method="post", is_form_submit=True)) == "submit"


# A content row is not an action (owner, 2026-10-23): Chief's click on an Upwork chat row asked as "accept".
JAMES_ROW = "JB James Blue, James Blue 10/14/26 Bot Developer James Blue ended the contract"


def test_a_long_content_row_is_browsing_even_with_a_committing_word_late_in_it() -> None:
    assert commit_class(_t(JAMES_ROW)) == "browsing"
    assert commit_class(_t("Bot Developer", visible_text=JAMES_ROW)) == "browsing"
    assert commit_class(_t(JAMES_ROW, kind="link")) == "browsing"


def test_a_long_label_that_starts_with_an_action_still_commits() -> None:
    assert commit_class(_t("Accept offer from James Blue for the bot project")) == "accept"
    assert commit_class(_t("Send message to James Blue about the new contract")) == "send"


# Owner, 2026-11-06: ALSA's "Iniciar sesión con Google" is Google's button in Google's own frame; it asked twice.
# Signing in is browsing (B2), in a frame too; a frame that says anything else, or only "Next", stays unknown.

def test_a_frames_sign_in_with_google_button_is_browsing() -> None:
    for label in ("Botón Iniciar sesión con Google", "Sign in with Google", "Continue with Google",
                  "Continuar con Google", "Iniciar sesión"):
        assert commit_class(_t(label, cross_origin_frame=True)) == "browsing", label
    assert commit_class(_t("Buy with Google Pay", cross_origin_frame=True)) == "unknown"
    assert commit_class(_t("Sign in and pay", cross_origin_frame=True)) == "unknown"
    assert commit_class(_t("Continue", cross_origin_frame=True)) == "unknown"
    assert commit_class(_t("Sign in with Google", cross_origin_frame=True), key="Enter") == "unknown"


# Owner, 2026-11-06: Gela's click on an ALSA receipt in Gmail parked on a Pay card: "comprar" was among the row's
# first words. In a content row an action names itself first ("Pay 36 EUR for …"); a word later on is content.
GMAIL_ROW = ("Inbox Gracias por comprar en Alsa - alsa. Estimado cliente, Tu compra se ha realizado correctamente. "
             "Este es su localizador")


def test_a_content_row_commits_only_when_it_starts_with_the_action() -> None:
    assert commit_class(_t(GMAIL_ROW, kind="row")) == "browsing"
    assert commit_class(_t(GMAIL_ROW)) == "browsing"
    assert commit_class(_t("Gracias", visible_text=GMAIL_ROW)) == "browsing"
    assert commit_class(_t("Pagar 36 EUR por 2 billetes de autobús Madrid Tbilisi")) == "spend"
    assert commit_class(_t("Comprar ahora: 2 billetes de autobús de Valencia a Barcelona")) == "spend"


def test_a_long_label_in_a_dialog_or_a_post_form_is_not_a_content_row() -> None:
    assert commit_class(_t(JAMES_ROW, in_dialog="End contract")) != "browsing"
    post = _t(JAMES_ROW, is_form_submit=True, form_method="post")
    assert commit_class(post) == "submit"
    assert commit_class(_t(JAMES_ROW, cross_origin_frame=True)) == "unknown"


def test_short_labels_are_read_whole_as_before() -> None:
    assert commit_class(_t("Accept offer")) == "accept"
    assert commit_class(_t("Pay €20")) == "spend"
    assert commit_class(_t("End the contract now")) == "accept"


# Owner, 2026-10-25: "if he need accept continue or reject cookies or something that he should do automatically".
# A pop-up's plain dismiss buttons are browsing; anything that also says an action still asks.

def test_a_popups_dismiss_buttons_are_browsing() -> None:
    for label in ("Got it", "OK", "Okay", "Not now", "Maybe later", "Close", "Dismiss", "Skip", "No thanks",
                  "Continue", "Entendido", "Ahora no", "Más tarde", "Cerrar", "Vale", "Omitir"):
        assert commit_class(_t(label, in_dialog="What's new")) == "browsing", label
        assert commit_class(_t(label)) == "browsing", label


def test_starting_a_search_over_is_browsing() -> None:
    """Owner, 2026-11-05: Wizz Air's "Restart booking" after a timeout asked for a Yes; nothing is booked yet."""
    for label in ("Restart booking", "Start over", "Start again", "New search", "Restart", "Empezar de nuevo"):
        assert commit_class(_t(label, in_dialog="Your session expired")) == "browsing", label
    assert commit_class(_t("Restart subscription")) != "browsing"


def test_a_dismiss_word_beside_an_action_still_asks() -> None:
    assert commit_class(_t("OK, delete", in_dialog="Delete chat?")) == "delete"
    assert commit_class(_t("Close account")) not in ("browsing", "consent")
    assert commit_class(_t("OK, send")) == "send"
    assert commit_class(_t("Got it, pay now")) == "spend"


def test_a_dismiss_word_as_a_post_forms_submit_still_submits() -> None:
    assert commit_class(_t("OK", is_form_submit=True, form_method="post")) == "submit"


def test_cookie_banners_reject_freely_and_accept_still_asks() -> None:
    assert commit_class(_t("Reject all", in_consent=True)) == "consent"
    assert commit_class(_t("Accept all", in_consent=True)) == "accept"


def test_an_icon_named_close_button_is_a_dismiss() -> None:
    """WhatsApp's photo viewer names its X "ic-close" (2026-10-25)."""
    for label in ("ic-close", "close-icon", "icon close", "btn-close", "x-icon", "ic_dismiss"):
        assert commit_class(_t(label, in_dialog="Photo")) == "browsing", label
    assert commit_class(_t("ic-delete")) == "delete"
    assert commit_class(_t("icon")) == "unknown"


# Owner, 2026-10-26: opening a WhatsApp chat asked as "send" because its row says "1 unread message".
def test_an_unread_count_in_a_chat_row_is_not_a_send() -> None:
    for label in ("1 unread message +995 574 74 33 22 13:39 \U0001f979", "2 unread messages Francis 12:01",
                  "3 mensajes no leídos Francis 12:01"):
        assert commit_class(_t(label)) == "browsing", label
    assert commit_class(_t("Send message")) == "send"
    assert commit_class(_t("Message")) == "send"
