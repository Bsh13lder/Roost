"""A currency code at the pydantic boundary (polish round A, item 8): "usd" and " USD " are read as "USD"
before the three-letter pattern is checked, so a lower-case code is accepted on every route and tool and
stored in upper case. ``roost.money.models`` upper-cases again, whatever builds a draft."""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import BeforeValidator, Field

from roost.constants import CURRENCY_PATTERN


def upper_case(value: Any) -> Any:
    """A string is trimmed and upper-cased; anything else is left for pydantic to refuse."""
    return value.strip().upper() if isinstance(value, str) else value


CurrencyCode = Annotated[str, BeforeValidator(upper_case), Field(pattern=CURRENCY_PATTERN)]
OptionalCurrencyCode = Annotated[str | None, BeforeValidator(upper_case), Field(pattern=CURRENCY_PATTERN)]
