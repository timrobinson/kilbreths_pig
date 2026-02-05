"""
acs_title_extractor.py

A clean, font-aware extractor for ACS (American Chemical Society)
paper titles from digital PDFs using PyMuPDF.

Usage:
    from acs_title_extractor import ACSExtractor
    title = ACSExtractor().extract_title("paper.pdf")
"""
print("LOADING ACS TITLE EXTRACTOR FROM:", __file__)

import fitz  # PyMuPDF


class ACS_Title_Extractor:
    """
    Extracts ACS paper titles from digital PDFs using layout and font-size
    heuristics tuned to ACS journal formatting.
    """

    def __init__(self, top_fraction: float = 0.2):
        """
        Parameters
        ----------
        top_fraction : float
            Fraction of the page height to consider for title candidates.
            ACS titles always appear in the upper half of page 1.
        """
        self.top_fraction = top_fraction

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def extract_title(self, pdf_path: str) -> str:
        """
        Extract the ACS paper title from the first page of a PDF.

        Parameters
        ----------
        pdf_path : str
            Path to the PDF file.

        Returns
        -------
        str
            The extracted title, or an empty string if not found.
        """
        doc = fitz.open(pdf_path)
        page = doc.load_page(0)

        spans = self._extract_spans(page)
        spans = self._filter_top_region(page, spans)
        spans = self._filter_non_title(spans)
        # print("DEBUG: spans after filtering =", len(spans))
        # for s in spans:
        #     print(f"{s['size']:>6}  {s['y0']:>6}  {s['text']}")

        if not spans:
            return ""

        # Identify the dominant title font size
        max_font = max(s["size"] for s in spans)

        # Keep spans within 1 pt of the max font size
        from collections import Counter

        # Round sizes to nearest 0.5 pt to cluster similar spans
        sizes = [round(s["size"] * 2) / 2 for s in spans]
        dominant_size = Counter(sizes).most_common(1)[0][0]

        title_candidates = [s for s in spans if round(s["size"] * 2) / 2 == dominant_size]

        # Group by y0 (titles often span multiple spans on the same line)
        from collections import defaultdict

        lines = defaultdict(list)
        for s in title_candidates:
            # Round y0 to nearest pixel to group lines
            key = round(s["y0"])
            lines[key].append(s)

        # Pick the top-most line group (smallest y0)
        top_line_key = sorted(lines.keys())[0]
        top_line_spans = lines[top_line_key]

        # Sort left-to-right
        top_line_spans.sort(key=lambda s: s["x0"])

        # Merge text
        title = " ".join(s["text"].strip() for s in top_line_spans)
        return self._clean_title(title)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _extract_spans(self, page):
        """Extract all text spans with font size and bounding boxes."""
        spans = []
        blocks = page.get_text("dict")["blocks"]

        for b in blocks:
            if "lines" not in b:
                continue
            for line in b["lines"]:
                for span in line["spans"]:
                    spans.append({
                        "text": span["text"],
                        "size": span["size"],
                        "font": span["font"],
                        "y0": b["bbox"][1],
                        "x0": b["bbox"][0],
                    })
        return spans

    def _filter_top_region(self, page, spans):
        """Keep only spans in the upper portion of the page."""
        cutoff = page.rect.height * self.top_fraction
        return [s for s in spans if s["y0"] < cutoff]

    def _filter_non_title(self, spans):
        """Remove spans that are clearly not part of the title."""
        filtered = []
        for s in spans:
            text = s["text"].strip()

            if not text:
                continue

            # Skip abstract header
            if text.upper().startswith("ABSTRACT"):
                continue

            # Skip author lines (many commas)
            if text.count(",") >= 3:
                continue

            # Skip all-caps blocks (ACS titles are not all caps)
            if text.isupper() and len(text.split()) > 2:
                continue

            filtered.append(s)

        return filtered

    def _clean_title(self, title: str) -> str:
        """Normalize whitespace and remove artifacts."""
        title = title.replace("\n", " ")
        title = " ".join(title.split())
        return title.strip()


# ----------------------------------------------------------------------
# Optional CLI usage
# ----------------------------------------------------------------------
if __name__ == "__main__":
    import sys

    if len(sys.argv) != 2:
        print("Usage: python acs_title_extractor.py <pdf_path>")
        sys.exit(1)

    extractor = ACS_Title_Extractor()
    result = extractor.extract_title(sys.argv[1])
    print(result)