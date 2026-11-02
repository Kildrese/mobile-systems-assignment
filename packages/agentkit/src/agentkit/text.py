"""Text normalization for quote and evidence checks: the same rules on both sides."""

import html
import unicodedata

MIN_QUOTE_CHARS = 3
# Curly quotes, primes, dashes and the no-break space, by code point.
_QUOTES = str.maketrans(
    {
        **dict.fromkeys((0x2018, 0x2019, 0x201A, 0x201B, 0x2032), "'"),
        **dict.fromkeys((0x201C, 0x201D, 0x201E, 0x2033), '"'),
        **dict.fromkeys((0x2010, 0x2011, 0x2012, 0x2013, 0x2014, 0x2212), "-"),
        0x00A0: " ",
    }
)


def normalize(text: str) -> str:
    """HTML entities decoded, NFKC, straight quotes and dashes, lowercase, single spaces."""
    text = unicodedata.normalize("NFKC", html.unescape(text)).translate(_QUOTES).lower()
    return " ".join(text.split())


def quote_found(quote: str, haystack: str) -> bool:
    q = normalize(quote)
    return len(q) >= MIN_QUOTE_CHARS and q in normalize(haystack)
