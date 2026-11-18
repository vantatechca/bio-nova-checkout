"""Checks a pushed section before it is stored.

Besides the shape (``schemas.panels``) every string in the payload is scanned for what looks like a full card
number. Senders are trusted to send only the last four digits, but the server does not rely on that alone.
"""

from __future__ import annotations

import re
from collections.abc import Iterator

from pydantic import ValidationError

from app.errors import BadRequest, Unprocessable
from app.schemas.panels import WriteIn
from app.services.panel_catalog import CARDS_SECTION, SITES_SECTION

# 13-19 digits, optionally separated by single spaces or dashes ("4242 4242 4242 4242").
DIGIT_RUN = re.compile(r"\d(?:[ -]?\d){12,18}")


def passes_luhn(digits: str) -> bool:
    total = 0
    for index, char in enumerate(reversed(digits)):
        n = int(char)
        if index % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


def looks_like_full_card_number(text: str) -> bool:
    for run in DIGIT_RUN.finditer(text):
        digits = re.sub(r"\D", "", run.group())
        # Issuer ranges start with 2-6 (Mastercard 2/5, Amex 3, Visa 4, Discover 6).
        if 13 <= len(digits) <= 19 and digits[0] in "23456" and passes_luhn(digits):
            return True
    return False


def _strings(value: object) -> Iterator[str]:
    """Every string in a JSON value, keys included. Whole numbers count too: 4242424242424242 is just as bad."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, bool):
        return
    elif isinstance(value, int):
        yield str(value)
    elif isinstance(value, dict):
        for key, item in value.items():
            yield str(key)
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)


def _first_error(exc: ValidationError) -> str:
    first = exc.errors()[0]
    where = ".".join(str(part) for part in first["loc"])
    message = first["msg"].removeprefix("Value error, ")
    return f"{where}: {message}" if where else message


def validate_write(panel: str, section: str, body: object) -> dict:
    """Returns the content to store (a JSON-ready dict), or raises ``BadRequest`` / ``Unprocessable``."""
    if not isinstance(body, dict):
        raise BadRequest('Send a JSON object like {"content": {...}}')
    if any(looks_like_full_card_number(text) for text in _strings(body)):
        raise Unprocessable(
            "Rejected: the content contains what looks like a full card number. Send only the last 4 digits."
        )
    try:
        content = WriteIn.model_validate(body).content
    except ValidationError as exc:
        raise BadRequest(_first_error(exc)) from None
    if content.sites is not None and (panel, section) != SITES_SECTION:
        raise BadRequest("sites: only allowed in the Sites > Live Sites section")
    if content.cards is not None and (panel, section) != CARDS_SECTION:
        raise BadRequest("cards: only allowed in the Ads Data > Credit Card Info section")
    return content.model_dump(mode="json", exclude_none=True)
