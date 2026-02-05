# journal_iso4.py
from __future__ import annotations

import re
from functools import lru_cache

print("LOADING ISO4 COMPLIANT JOURNAL TITLES FROM:", __file__)

try:
    from iso4 import abbreviate as iso4_abbreviate
except ImportError as e:
    raise ImportError("Missing dependency: iso4. Install with `pip install iso4`.") from e


def norm_journal(s: str) -> str:
    """Normalize journal strings for matching/output (whitespace, dashes, ampersands)."""
    if not isinstance(s, str):
        return ""
    s = s.strip()
    s = re.sub(r"\s+", " ", s)
    s = s.replace("−", "-").replace("–", "-").replace("—", "-")
    s = s.replace("&", "and")
    return s


@lru_cache(maxsize=50000)
def iso4_or_full(journal_full: str) -> str:
    """Return ISO-4 abbreviation if derivable; otherwise return normalized full."""
    jf = norm_journal(journal_full)
    if not jf:
        return ""
    try:
        ab = iso4_abbreviate(jf)
        ab = norm_journal(ab)
        return ab if ab else jf
    except Exception:
        return jf


def add_iso4_columns(
    df_doi,
    journal_col: str = "journal",
    full_col: str = "journal_full",
    iso4_col: str = "journal_iso4",
    preferred_col: str = "journal_preferred",
):
    """
    Expand df_DOI with:
      - journal_full: normalized full journal title from DOI metadata
      - journal_iso4: ISO-4 abbreviation if possible else normalized full
      - journal_preferred: what to print in ACS output (defaults to journal_iso4)
    """
    if journal_col not in df_doi.columns:
        raise KeyError(f"df_doi missing required column '{journal_col}'")

    df = df_doi.copy()
    df[full_col] = df[journal_col].apply(norm_journal)
    df[iso4_col] = df[journal_col].apply(iso4_or_full)
    df[preferred_col] = df[iso4_col].apply(norm_journal)
    return df


def _strip_periods(s: str) -> str:
    return (s or "").replace(".", "")


def best_journal_score(
    obs_journal: str,
    doi_journal_full: str,
    doi_journal_iso4: str,
    score_fn,
    strip_periods: bool = True,
):
    """
    Compare observed journal against DOI full + ISO4. Return (best_score, variant).
    variant in {"iso4","full"}.
    """
    o = norm_journal(obs_journal)
    full = norm_journal(doi_journal_full)
    iso4 = norm_journal(doi_journal_iso4)

    if strip_periods:
        o, full, iso4 = _strip_periods(o), _strip_periods(full), _strip_periods(iso4)

    s_full = float(score_fn(o, full)) if o and full else 0.0
    s_iso4 = float(score_fn(o, iso4)) if o and iso4 else 0.0

    if s_iso4 >= s_full:
        return s_iso4, "iso4"
    return s_full, "full"

