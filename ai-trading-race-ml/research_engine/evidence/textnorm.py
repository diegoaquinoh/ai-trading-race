"""Pinned text normalization for matching and lexical retrieval.

``lex-norm-v1``:

1. Unicode NFKC, lowercase; en/em dashes become ``-``; curly apostrophes become ``'``.
2. Terms are ``[a-z0-9]+`` runs (hyphenated words split into parts).
3. A fixed English stopword list is removed (``STOPWORDS``; frozen with the version).
4. Light plural folding: ``-ies`` -> ``-y``; a trailing ``s`` is dropped when the
   word is longer than 3 characters and does not end in ``ss``, ``us`` or ``is``.

No corpus statistics are involved, so normalization cannot leak future data.
"""

from __future__ import annotations

import re
import unicodedata

LEX_NORMALIZER_VERSION = "lex-norm-v1"

STOPWORDS = frozenset("""
a about above after again against all also am an and any are as at be because been before
being below between both but by can could did do does doing down during each few for from
further had has have having he her here hers herself him himself his how i if in into is it
its itself just me more most my myself no nor not now of off on once only or other our ours
ourselves out over own same she should so some such than that the their theirs them themselves
then there these they this those through to too under until up very was we were what when
where which while who whom why will with would you your yours yourself yourselves
did said say says what's whats tell give show
""".split())

_TERM = re.compile(r"[a-z0-9]+")
_DASHES = str.maketrans({"–": "-", "—": "-", "−": "-", "’": "'", "‘": "'"})


def normalize_for_match(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).translate(_DASHES).lower()
    return re.sub(r"\s+", " ", text).strip()


def fold(term: str) -> str:
    if len(term) > 4 and term.endswith("ies"):
        return term[:-3] + "y"
    if len(term) > 3 and term.endswith("s") and not term.endswith(("ss", "us", "is")):
        return term[:-1]
    return term


def lexical_terms(text: str, *, keep_stopwords: bool = False) -> list[str]:
    norm = normalize_for_match(text)
    terms = _TERM.findall(norm)
    if not keep_stopwords:
        terms = [t for t in terms if t not in STOPWORDS]
    return [fold(t) for t in terms]


def alias_key(text: str) -> str:
    """Normalized alias form: lex-norm-v1 terms joined by single spaces."""
    return " ".join(lexical_terms(text, keep_stopwords=True))
