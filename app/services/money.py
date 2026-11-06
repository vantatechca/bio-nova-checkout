"""Money formatting. Amounts are integers in minor units (cents); every supported currency is assumed
to have two decimal places."""

from __future__ import annotations

_SYMBOLS = {"USD": "$", "CAD": "CA$", "AUD": "A$", "NZD": "NZ$", "EUR": "€", "GBP": "£"}


def format_money(minor_units: int, currency: str) -> str:
    amount = f"{minor_units / 100:,.2f}"
    symbol = _SYMBOLS.get(currency.upper())
    return f"{symbol}{amount}" if symbol else f"{amount} {currency.upper()}"
