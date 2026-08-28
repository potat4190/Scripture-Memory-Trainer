"""Text normalization for answer checking. Pure function of ``(text, lang)``.

Uses the third-party ``regex`` package (not stdlib ``re``) because only it
supports ``\\p{P}``, the Unicode punctuation property. That is what makes
"strip punctuation entirely, in every script" a one-line rule instead of a
hand-maintained character list. See ``docs/TOOLING.md`` section 0.

Order matters: NFC first (Arabic and Devanagari can arrive decomposed), then
quote/full-width folding, then the language-specific rules, then punctuation,
then whitespace, then case folding.
"""

from __future__ import annotations

import unicodedata

import regex as re

# Curly quotes -> straight (codepoint -> codepoint, for str.translate).
_QUOTES = {0x2018: 0x27, 0x2019: 0x27, 0x201C: 0x22, 0x201D: 0x22}

# Full-width forms -> ASCII: U+FF0C -> "," and U+FF1B -> ";".
_FULLWIDTH = {0xFF0C: 0x2C, 0xFF1B: 0x3B}

# Arabic harakat (optional diacritics): U+064B-U+0652, plus tatweel U+0640
# and dagger alef U+0670.
_ARABIC_HARAKAT = frozenset(range(0x064B, 0x0653)) | {0x0640, 0x0670}

_ARABIC_ALEF_WASLA = "ٱ"
_ARABIC_ALEF = "ا"
_ARABIC_ALEF_MAQSURA = "ى"
_ARABIC_YEH = "ي"

_HINDI_NUKTA = "़"

_PUNCT_RE = re.compile(r"\p{P}+")
_WHITESPACE_RE = re.compile(r"\s+")


def normalize(text: str, lang: str) -> str:
    """Return the comparison form of ``text`` for a card in language ``lang``."""
    s = unicodedata.normalize("NFC", text)
    s = s.translate(_QUOTES)
    s = s.translate(_FULLWIDTH)

    if lang == "ar":
        s = "".join(ch for ch in s if ord(ch) not in _ARABIC_HARAKAT)
        s = s.replace(_ARABIC_ALEF_WASLA, _ARABIC_ALEF)
        s = s.replace(_ARABIC_ALEF_MAQSURA, _ARABIC_YEH)
    elif lang == "hi":
        s = s.replace(_HINDI_NUKTA, "")
    # zh: deliberately NO simplified/traditional conversion. This is a rule,
    # not an oversight -- traditional input against a simplified card must stay
    # incorrect. Do not "fix" this. See docs/DECISIONS.md.

    s = _PUNCT_RE.sub("", s)
    s = _WHITESPACE_RE.sub(" ", s).strip()
    return s.casefold()
