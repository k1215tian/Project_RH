from odoo import models, api, fields
from odoo.exceptions import ValidationError

def _roman_under_4000(number):
    """Convert integer 1-3999 to Roman numeral."""
    roman_map = (
        (1000, "M"),
        (900, "CM"),
        (500, "D"),
        (400, "CD"),
        (100, "C"),
        (90, "XC"),
        (50, "L"),
        (40, "XL"),
        (10, "X"),
        (9, "IX"),
        (5, "V"),
        (4, "IV"),
        (1, "I"),
    )

    result = []

    for value, symbol in roman_map:
        count, number = divmod(number, value)
        result.append(symbol * count)

    return "".join(result)


def _roman_overline(text):
    """Add Unicode overline to each Roman character."""
    return "".join(f"{char}\u0305" for char in text)


def number_to_roman(number):
    """
    Convert positive integer to Roman numeral.

    Supports numbers greater than 3999 using Unicode overline notation.
    """
    if number is None:
        return ""

    try:
        number = int(number)
    except (TypeError, ValueError) as exc:
        raise ValueError("Number must be a valid integer.") from exc

    if number <= 0:
        raise ValueError("Number must be greater than 0.")

    thousands, remainder = divmod(number, 1000)

    result = []

    if thousands:
        if thousands < 4000:
            result.append(_roman_overline(_roman_under_4000(thousands)))
        else:
            result.append(_roman_overline(number_to_roman(thousands)))

    if remainder:
        result.append(_roman_under_4000(remainder))

    return "".join(result)


def year_to_roman(year):
    """Convert year to Roman numeral."""
    return number_to_roman(year)


def month_to_roman(month):
    """Convert month 1-12 to Roman numeral."""
    try:
        month = int(month)
    except (TypeError, ValueError) as exc:
        raise ValueError("Month must be a valid integer.") from exc

    if not 1 <= month <= 12:
        raise ValueError("Month must be between 1 and 12.")

    return number_to_roman(month)