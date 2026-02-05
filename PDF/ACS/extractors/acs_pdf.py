import re
from typing import Dict, Tuple, Optional, List

import pandas as pd
import fitz  # PyMuPDF

print("LOADING ACS REFERENCE EXTRACTOR FROM:", __file__)

# -----------------------------
# Core extractor
# -----------------------------
def extract_references_from_acs_pdf(
    pdf_path: str,
    *,
    keep_report: bool = True,
    expected_n: Optional[int] = None,
) -> Tuple[pd.DataFrame, Dict]:
    """
    Robustly extract the REFERENCES section from an ACS-style PDF and return:
      df_original: columns [ref_id:int, raw:str]
      report: diagnostic metadata (start page, pattern, counts, gaps, etc.)

    Key ACS hardening:
      - Finds "REFERENCES" header (e.g., '■ REFERENCES')
      - Splits references by (n) / [n] / 'n.' but avoids false starts (issue numbers)
      - Removes common ACS footer/header lines (e.g., 'pubs.acs.org', 'ACS Appl. ...', 'Article', etc.)
      - Normalizes whitespace and fixes wrapped page ranges like '8562− 8569' -> '8562−8569'
    """

    # ----- Header detection -----
    HEADER_RE = re.compile(
        r"^\s*[■•\u25A0\u25AA\u25A1\-\–\—]*\s*REFERENCES\s*$",
        re.IGNORECASE
    )

    # ----- Footer/header noise removal (line-based) -----
    # Broad patterns seen in ACS PDFs, including your test file.
    FOOTER_LINE_RE = re.compile(
        r"^\s*("
        r"ACS Applied Polymer Materials|"
        r"pubs\.acs\.org|"
        r"ACS Appl\.|"
        r"Downloaded via|"
        r"See https?://pubs\.acs\.org/sharingguidelines|"
        r"https?://doi\.org/10\.\d{4,9}/\S+|"
        r"Article"
        r")\b.*$",
        re.IGNORECASE
    )
    PAGE_LETTER_RE = re.compile(r"^\s*[A-Z]\s*$")  # e.g., stray "K" page marker

    # ----- Reference start patterns -----
    # IMPORTANT: lookahead for an author-like "Surname," right after the marker.
    # This prevents matching issue numbers that wrap onto a new line, e.g. "(24), 3536−..."
    AUTHOR_LOOKAHEAD = r"(?=[A-Z][A-Za-z\u00C0-\u024F’'\-\. ]{1,40},)"

    START_PATTERNS = {
        "paren": re.compile(rf"^\s*\((\d{{1,4}})\)\s+{AUTHOR_LOOKAHEAD}", re.MULTILINE),
        "bracket": re.compile(rf"^\s*\[(\d{{1,4}})\]\s+{AUTHOR_LOOKAHEAD}", re.MULTILINE),
        "dot": re.compile(rf"^\s*(\d{{1,4}})\.\s+{AUTHOR_LOOKAHEAD}", re.MULTILINE),
    }

    def _page_lines(page_text: str) -> List[str]:
        return [ln.rstrip("\n\r") for ln in page_text.splitlines()]

    def _find_references_start(doc: fitz.Document) -> Tuple[Optional[int], Optional[int]]:
        # Pass 1: standalone header line match
        for i in range(len(doc)):
            text = doc[i].get_text("text") or ""
            lines = _page_lines(text)
            for j, ln in enumerate(lines):
                if HEADER_RE.match(ln.strip()):
                    return i, j
        # Pass 2: any "REFERENCES" line match
        for i in range(len(doc)):
            text = doc[i].get_text("text") or ""
            lines = _page_lines(text)
            for j, ln in enumerate(lines):
                if re.search(r"\bREFERENCES\b", ln, re.IGNORECASE):
                    return i, j
        return None, None

    def _collect_text_from(doc: fitz.Document, start_page: int, start_line: int) -> str:
        parts = []

        # Start page: take only lines AFTER the header line
        start_text = doc[start_page].get_text("text") or ""
        start_lines = _page_lines(start_text)
        parts.append("\n".join(start_lines[start_line + 1 :]))

        # Remaining pages
        for p in range(start_page + 1, len(doc)):
            parts.append(doc[p].get_text("text") or "")

        return "\n".join(parts)

    def _clean_lines(text: str) -> str:
        out = []
        for ln in text.splitlines():
            s = ln.strip()
            if not s:
                out.append(ln)
                continue
            if FOOTER_LINE_RE.match(s):
                continue
            if PAGE_LETTER_RE.match(s):
                continue
            out.append(ln)
        return "\n".join(out)

    def _choose_pattern(text: str) -> Tuple[str, re.Pattern, Dict[str, int]]:
        counts = {name: sum(1 for _ in pat.finditer(text)) for name, pat in START_PATTERNS.items()}
        # pick the max count; break ties deterministically
        best = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
        return best, START_PATTERNS[best], counts

    def _split_refs(text: str, pat: re.Pattern) -> Dict[int, str]:
        matches = list(pat.finditer(text))
        refs: Dict[int, str] = {}

        for i, m in enumerate(matches):
            ref_id = int(m.group(1))
            start = m.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)

            chunk = text[start:end].strip()
            # remove marker from the beginning (everything matched up to author lookahead)
            chunk = chunk[m.end() - m.start() :].strip()

            # normalize whitespace
            chunk = re.sub(r"\s+", " ", chunk)

            # fix wrapped dash ranges: "8562− 8569" or "8562- 8569" -> "8562−8569"
            chunk = re.sub(r"(\d)\s*([−-])\s*(\d)", r"\1\2\3", chunk)

            refs[ref_id] = chunk

        return refs

    # ----- Run extraction -----
    doc = fitz.open(pdf_path)

    start_page, start_line = _find_references_start(doc)
    if start_page is None:
        df_empty = pd.DataFrame(columns=["ref_id", "raw"])
        report = {
            "ok": False,
            "reason": "REFERENCES header not found",
            "pdf_path": pdf_path,
        }
        return (df_empty, report) if keep_report else (df_empty, {})

    raw_ref_text = _collect_text_from(doc, start_page, start_line)
    cleaned_ref_text = _clean_lines(raw_ref_text)

    pattern_name, split_pat, counts = _choose_pattern(cleaned_ref_text)
    refs = _split_refs(cleaned_ref_text, split_pat)

    # Diagnostics: gaps, duplicates, expected_n check
    ref_ids_sorted = sorted(refs.keys())
    gaps = []
    if ref_ids_sorted:
        for a, b in zip(ref_ids_sorted, ref_ids_sorted[1:]):
            if b != a + 1:
                gaps.append((a, b))

    # Build DF
    df_original = pd.DataFrame(
        [{"ref_id": rid, "raw": refs[rid]} for rid in ref_ids_sorted]
    )

    report = {
        "ok": True,
        "pdf_path": pdf_path,
        "references_start_page_1idx": start_page + 1,
        "references_header_line_0idx": start_line,
        "split_pattern": pattern_name,
        "pattern_counts": counts,
        "n_refs": len(df_original),
        "gaps": gaps,
    }

    if expected_n is not None:
        report["expected_n"] = expected_n
        report["meets_expected_n"] = (len(df_original) == expected_n)

    return (df_original, report) if keep_report else (df_original, {})


# -----------------------------
# Example usage on your file:
# -----------------------------
# df_original, report = extract_references_from_acs_pdf("/mnt/data/test.pdf", expected_n=55)
# print(report)
# df_original.head()
