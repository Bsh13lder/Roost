"""The Pay card's fixed words (P4, P5, P8). None of them ever holds a card value."""

from __future__ import annotations

from typing import Final

NOT_A_PAY_CARD_TEXT: Final = "This card isn't a payment, so it has no card fields."
NOT_YOUR_CHAT_TEXT: Final = "Only a payment in your own chat with the bot can be paid from a card."
WRONG_PAGE_TEXT: Final = "The bot's computer isn't on {host}'s payment page any more, so nothing was typed."
NO_BOXES_TEXT: Final = "I can't see the card boxes next to Pay any more. Take control and type the card there."
FRAMED_TEXT: Final = ("This site's card box is protected: Take control to type your card, then Give it back and "
                      "tap Pay.")
LIST_BOX_TEXT: Final = "This site picks the expiry date from a list. Take control to pick it, then tap Pay."
NOT_TYPED_TEXT: Final = "The card didn't go into the boxes, so I didn't click Pay. Try again or take control."
HELD_TEXT: Final = "You have the bot's computer. Give it back first, then tap Pay."
BUSY_TEXT: Final = "The bot's computer is busy. Try again in a moment."
MISSING_TEXT: Final = "This page needs the card's {part}."
CARD_GONE_TEXT: Final = "That saved card isn't in Vault: cards any more."
CARDS_FULL_TEXT: Final = "Vault: cards is full. Delete a card there first."
PART_WORDS: Final = {"number": "number", "exp": "expiry date", "exp_month": "expiry date",
                     "exp_year": "expiry date", "cvc": "security code", "name": "name"}
