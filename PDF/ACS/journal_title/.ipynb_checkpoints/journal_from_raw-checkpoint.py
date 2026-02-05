# journal_title/journal_from_raw.py
"""
Journal extraction / cleaning utilities.

Design goals:
- Conservative: avoid hallucinating a journal from title/authors noise.
- Repair-friendly: if journal_obs is a placeholder ("MB", "A", "B", "Ed", etc.),
  prefer extracting the *known* DOI journal (iso4/full) from the raw line.
- Keep backwards compatibility: `clean_journal_obs(journal_obs, raw="")`
  still exists and can be called with 1 or 2 args.

Recommended usage in your pipeline:
- If you have DOI journal strings available, use `clean_journal_obs_with_targets(...)`
  (or call `clean_journal_obs(..., doi_journal_full=..., doi_journal_iso4=...)`).

Exports (expected):
- JOURNAL_BEFORE_YEAR_RE
- extract_journal_from_acs_raw
- clean_journal_obs
- clean_journal_obs_with_targets
"""

from __future__ import annotations

import re
from typing import List, Optional

from rapidfuzz import fuzz, process

print("LOADING RAW DATA FROM:", __file__)


# ---------------------------------------------------------------------
# Public regex export (you asked to see this symbol in the module)
# ---------------------------------------------------------------------
# Heuristic: a "journal-like" token right before the year in ACS-ish refs.
# Example: "Mol. Biotechnol. 2000, 16, 127-150."
JOURNAL_BEFORE_YEAR_RE = re.compile(
    r"""
    (?:^|[.;])\s*                          # boundary / punctuation
    (?P<journal>                           # capture journal-ish
        [A-Za-z][A-Za-z0-9&'’\-\s\.]{1,80} # allow abbrev with periods/spaces
    )
    \s+
    (?P<year>(?:19|20)\d{2})\b
    """,
    re.VERBOSE,
)

YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")


# ---------------------------------------------------------------------
# Normalization / heuristics
# ---------------------------------------------------------------------
PLACEHOLDER_JOURNALS = {"mb", "a", "b", "ed"}

# Words that are very likely to appear in titles (not journals)
TITLEISH_WORD_RE = re.compile(
    r"\b(principles|practices|introduction|analysis|review|framework|method|methods)\b",
    re.IGNORECASE,
)


def _norm_spaces(s: str) -> str:
    return " ".join((s or "").split()).strip()


def _strip_punct(s: str) -> str:
    return (s or "").strip().strip(" ,;:.")


def _looks_placeholder_or_bad(j: str) -> bool:
    jj = _norm_spaces(j)
    if not jj:
        return True
    if len(jj) <= 3:
        return True
    if jj.lower() in PLACEHOLDER_JOURNALS:
        return True
    return False


def _looks_title_like(s: str) -> bool:
    """
    Conservative filter: if something looks like a title rather than a journal,
    do NOT treat it as a journal.

    Journals in ACS refs are rarely:
    - 6+ words (titles often are)
    - containing common title-ish words (principles, introduction, review, ...)
    """
    ws = _norm_spaces(s)
    if not ws:
        return True
    if len(ws) <= 3:
        return True
    if ws.lower() in PLACEHOLDER_JOURNALS:
        return True
    if len(ws.split()) >= 6:
        return True
    if TITLEISH_WORD_RE.search(ws):
        return True
    return False


# ---------------------------------------------------------------------
# Core extractors
# ---------------------------------------------------------------------
def extract_journal_from_acs_raw(raw: str) -> str:
    """
    Conservative ACS-ish journal extractor.

    Strategy:
    1) Look for a journal immediately before the year using JOURNAL_BEFORE_YEAR_RE.
       This is more robust than "take text after last period" because authors/titles
       contain many periods.
    2) If regex fails, fallback:
       - find first year
       - take text immediately before year
       - take the last period-delimited chunk
       - reject if it looks title-like / placeholder-like

    Returns:
        journal-like string, or "" if not confidently found.
    """
    if not isinstance(raw, str) or not raw.strip():
        return ""

    s = _norm_spaces(raw)

    # 1) Best effort: journal right before year
    candidates: List[str] = []
    for m in JOURNAL_BEFORE_YEAR_RE.finditer(s):
        j = _strip_punct(m.group("journal"))
        if j:
            candidates.append(j)

    # Use the *last* match (closest to the year position)
    if candidates:
        j = candidates[-1]
        # If it smells like a title, reject
        if not _looks_title_like(j):
            return j

    # 2) Fallback path (more fragile)
    m = YEAR_RE.search(s)
    if not m:
        return ""

    pre = s[: m.start()].strip()
    if not pre:
        return ""

    # Take segment after last period in 'pre' (but validate aggressively)
    if "." in pre:
        cand = pre.split(".")[-1].strip()
    else:
        cand = pre

    cand = _strip_punct(cand)
    if not cand:
        return ""

    # Reject obvious title-like captures (this is what bit you on ref 23)
    if _looks_title_like(cand):
        return ""

    return cand


def _extract_journal_from_raw_using_targets(
    raw: str, targets: List[str], min_score: int = 90
) -> str:
    """
    Try to recover journal by searching for known target strings (from DOI metadata)
    inside the raw reference line.

    First preference: containment (exact substring match, case-insensitive).
    Fallback: fuzzy partial_ratio between raw and targets (choice-set is targets).
    """
    raw_n = _norm_spaces(raw)
    if not raw_n or not targets:
        return ""

    # Containment first (most conservative + most accurate)
    raw_low = raw_n.lower()
    for t in targets:
        t_n = _norm_spaces(t)
        if t_n and t_n.lower() in raw_low:
            # Return canonical target (not a raw slice)
            return t_n

    # Fuzzy fallback (still conservative because the only possible outputs are targets)
    best = process.extractOne(raw_n, targets, scorer=fuzz.partial_ratio)
    if best and best[1] >= min_score:
        return _norm_spaces(best[0])

    return ""


# ---------------------------------------------------------------------
# Public cleaners (drop-in safe)
# ---------------------------------------------------------------------
def clean_journal_obs(
    journal_obs: str,
    raw: str = "",
    doi_journal_full: str = "",
    doi_journal_iso4: str = "",
) -> str:
    """
    Clean observed journal string.

    Backwards compatible:
      - You can call clean_journal_obs(journal_obs)
      - Or clean_journal_obs(journal_obs, raw)

    If doi_journal_full / doi_journal_iso4 are provided, it will *prefer* matching
    them in the raw reference line when journal_obs looks bad.

    Rules:
    - Normalize whitespace / strip punctuation.
    - If journal_obs is placeholder-like or title-like:
        1) try to recover by matching DOI journal strings in raw
        2) else fallback to extract_journal_from_acs_raw(raw)
        3) else keep journal_obs (even if imperfect)
    """
    j = _strip_punct(_norm_spaces(journal_obs))

    # Only repair when the observed value is suspect
    if _looks_placeholder_or_bad(j) or _looks_title_like(j):
        targets = [
            t for t in [doi_journal_iso4, doi_journal_full] if _norm_spaces(t)
        ]

        # Prefer known DOI strings if available
        if targets and raw:
            hit = _extract_journal_from_raw_using_targets(raw, targets, min_score=85)
            if hit:
                return _strip_punct(hit)

        # Last resort: conservative ACS heuristic
        if raw:
            cand = extract_journal_from_acs_raw(raw)
            cand = _strip_punct(_norm_spaces(cand))
            if cand and not _looks_title_like(cand):
                return cand

    return j


def clean_journal_obs_with_targets(
    journal_obs: str,
    raw: str = "",
    doi_journal_full: str = "",
    doi_journal_iso4: str = "",
) -> str:
    """
    Explicit helper for the "I have DOI journal strings in my row" case.
    This is just a readability alias for clean_journal_obs(..., doi_journal_full=..., doi_journal_iso4=...).
    """
    return clean_journal_obs(
        journal_obs=journal_obs,
        raw=raw,
        doi_journal_full=doi_journal_full,
        doi_journal_iso4=doi_journal_iso4,
    )


__all__ = [
    "JOURNAL_BEFORE_YEAR_RE",
    "extract_journal_from_acs_raw",
    "clean_journal_obs",
    "clean_journal_obs_with_targets",
]


