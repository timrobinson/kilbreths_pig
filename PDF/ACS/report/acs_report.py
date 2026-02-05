"""
Kilbreth's Pig — ACS Normalization report builder.

This module is designed to be imported from your ACS Normalization notebook/pipeline.

Expected inputs:
- df_compare: a DataFrame with at minimum:
    ref_id (int)
    match_score (float, 0..100)
  And ideally one of:
    title (string)  [preferred]
    doi_url_final or doi_url (string)
    raw (string)    [optional, can be used as fallback display text]

Icons:
- yes.png, maybe.png, no.png (required)
- logo.png (optional)

Output:
- a single PDF report with a header, summary, and per-reference rows with pig icons.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Dict, Any, Tuple

import pandas as pd

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import LETTER
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle, KeepTogether
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors

try:
    from PIL import Image as PILImage
except Exception:  # pragma: no cover
    PILImage = None

print("LOADING KILBRETHS PIG REPORTS FROM:", __file__)

# ---------------------------------------------------------------------
# Canvas with page X of Y without duplicating pages
# ---------------------------------------------------------------------
class NumberedCanvas(canvas.Canvas):
    """
    Canvas that allows 'Page X of Y' by saving page states and rendering
    footer content in a second pass without duplicating pages.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self._draw_page_number(num_pages)
            super().showPage()
        super().save()

    def _draw_page_number(self, page_count: int):
        self.setFont("Helvetica", 9)
        self.setFillColor(colors.grey)
        self.drawRightString(LETTER[0] - 0.75 * inch, 0.55 * inch, f"Page {self._pageNumber} of {page_count}")


# ---------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------
@dataclass
class PigThresholds:
    happy: float = 50.0     # >= happy => yes pig
    maybe: float = 35.0     # >= maybe and < happy => maybe pig


def _validate_assets(yes_icon: Path, maybe_icon: Path, no_icon: Path) -> None:
    for p in [yes_icon, maybe_icon, no_icon]:
        if not p.exists():
            raise FileNotFoundError(f"Missing required icon file: {p}")


def _pick_icon(score: float, yes_icon: Path, maybe_icon: Path, no_icon: Path, thresholds: PigThresholds) -> Path:
    try:
        s = float(score)
    except Exception:
        return no_icon
    if s >= thresholds.happy:
        return yes_icon
    if s >= thresholds.maybe:
        return maybe_icon
    return no_icon


def _safe_str(x) -> str:
    return "" if x is None else str(x).strip()


def build_acs_report(
    df_compare: pd.DataFrame,
    out_pdf: str = "Kilbreths_Pig_ACS_Report.pdf",
    *,
    article_title: str = "",
    source_pdf: str = "",
    thresholds: PigThresholds = PigThresholds(),
    logo_path: str = "logo.png",
    yes_icon: str = "yes.png",
    maybe_icon: str = "maybe.png",
    no_icon: str = "no.png",
    footer_text: str = "From the offices of Boondoggle Research",
    report_title_left: str = "Kilbreth's Pig — ACS Normalization",
    ref_id_col: str = "ref_id",
    score_col: str = "match_score",
    title_col: str = "title",
    doi_url_cols: Tuple[str, ...] = ("doi_url_final", "doi_url", "doi_url_doi"),
    raw_col: str = "raw",
) -> str:
    """
    Build a PDF report showing per-reference match scores with pig icons.

    df_compare requirements:
      - ref_id_col: int-like
      - score_col: float-like 0..100

    Optional columns:
      - title_col
      - any column listed in doi_url_cols
      - raw_col (fallback)

    Returns out_pdf path (string).
    """
    out_pdf = str(out_pdf)
    logo_path = Path(logo_path)
    yes_icon = Path(yes_icon)
    maybe_icon = Path(maybe_icon)
    no_icon = Path(no_icon)

    _validate_assets(yes_icon, maybe_icon, no_icon)
    if not logo_path.exists():
        logo_path = None

    required = [ref_id_col, score_col]
    for c in required:
        if c not in df_compare.columns:
            raise KeyError(f"df_compare missing required column: '{c}'")

    d = df_compare.copy()
    d = d.sort_values(ref_id_col, kind="mergesort")

    # styles
    styles = getSampleStyleSheet()
    body = ParagraphStyle(
        "body", parent=styles["BodyText"],
        fontName="Helvetica", fontSize=10, leading=13, spaceAfter=2
    )
    small = ParagraphStyle(
        "small", parent=body, fontSize=9, leading=11, textColor=colors.grey
    )
    refnum_style = ParagraphStyle(
        "refnum", parent=body, fontName="Helvetica-Bold"
    )
    yes_style = ParagraphStyle("yes_style", parent=body, textColor=colors.darkgreen)
    maybe_style = ParagraphStyle("maybe_style", parent=body, textColor=colors.black)
    no_style = ParagraphStyle("no_style", parent=body, textColor=colors.red)

    def _pick_text_style(score: float):
        try:
            s = float(score)
        except Exception:
            return no_style
        if s >= thresholds.happy:
            return yes_style
        if s >= thresholds.maybe:
            return maybe_style
        return no_style

    def _best_doi_url(row) -> str:
        for col in doi_url_cols:
            if col in row and _safe_str(row[col]):
                return _safe_str(row[col])
        return ""

    def draw_header(canv, doc):
        canv.saveState()
        width, height = LETTER
        y_top = height - 0.75 * inch

        canv.setFont("Helvetica-Bold", 12)
        canv.drawString(0.75 * inch, y_top, report_title_left)

        if logo_path is not None and PILImage is not None:
            try:
                with PILImage.open(logo_path) as im:
                    w_px, h_px = im.size
                    aspect = h_px / w_px if w_px else 1.0
                logo_w = 1.8 * inch
                logo_h = logo_w * aspect
                x_logo = width - 0.75 * inch - logo_w + 0.25 * inch
                y_logo = height - 0.75 * inch - logo_h + 0.45 * inch
                canv.drawImage(
                    str(logo_path), x_logo, y_logo,
                    width=logo_w, height=logo_h,
                    preserveAspectRatio=True, mask="auto"
                )
            except Exception:
                pass

        # footer (left)
        canv.setFont("Helvetica-Oblique", 9)
        canv.setFillColor(colors.grey)
        canv.drawString(0.75 * inch, 0.55 * inch, footer_text)

        canv.restoreState()

    # summary counts
    def _bucket(score):
        try:
            s = float(score)
        except Exception:
            return "no"
        if s >= thresholds.happy:
            return "yes"
        if s >= thresholds.maybe:
            return "maybe"
        return "no"

    buckets = d[score_col].apply(_bucket)
    n_yes = int((buckets == "yes").sum())
    n_maybe = int((buckets == "maybe").sum())
    n_no = int((buckets == "no").sum())
    n_total = len(d)

    # document
    doc = SimpleDocTemplate(
        out_pdf,
        pagesize=LETTER,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=1.25 * inch,
        bottomMargin=0.85 * inch,
        title=report_title_left,
        author="Kilbreth's Pig",
    )

    story = []
    story.append(Spacer(1, 0.2 * inch))

    story.append(Paragraph(
        "This report summarizes reference normalization using DOI-derived metadata and a "
        "string-consistency score between the original bibliography entry and DOI metadata.",
        body
    ))

    if article_title.strip():
        story.append(Paragraph(f"Article under evaluation: <b>{article_title}</b>.", body))
    if source_pdf.strip():
        story.append(Paragraph(f"Source PDF: <b>{source_pdf}</b>.", body))

    story.append(Paragraph(
        f"Pig policy: score ≥ <b>{thresholds.happy:.0f}</b> is a happy pig. "
        f"Summary: <b>{n_yes}</b> happy, <b>{n_maybe}</b> maybe, <b>{n_no}</b> unhappy (of {n_total} total).",
        body
    ))

    story.append(Spacer(1, 0.20 * inch))

    # entries
    icon_size = 0.32 * 1.1 * inch
    col_icon_w = 0.45 * 1.1 * inch
    col_text_w = doc.width - col_icon_w

    for _, row in d.iterrows():
        ref_id = row.get(ref_id_col)
        score = row.get(score_col)

        title = _safe_str(row.get(title_col)) if title_col in row else ""
        doi_url = _best_doi_url(row)
        raw = _safe_str(row.get(raw_col)) if raw_col in row else ""

        display_text = title or doi_url or raw or "(missing title / doi / raw)"

        icon_path = _pick_icon(score, yes_icon, maybe_icon, no_icon, thresholds)
        icon = Image(str(icon_path), width=icon_size, height=icon_size)

        refnum_para = Paragraph(f"{int(ref_id)}.", refnum_style) if pd.notna(ref_id) else Paragraph("?.", refnum_style)
        text_style = _pick_text_style(score)

        # Show score and DOI URL on a second line (small)
        main = Paragraph(
            display_text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"),
            text_style
        )
        extra_lines = []
        if pd.notna(score):
            extra_lines.append(f"score: {float(score):.1f}")
        if doi_url:
            extra_lines.append(f"doi: {doi_url}")
        extra = Paragraph(" &nbsp;&nbsp;|&nbsp;&nbsp; ".join(extra_lines), small) if extra_lines else None

        text_table_rows = [[refnum_para, main]]
        if extra is not None:
            text_table_rows.append(["", extra])

        text_table = Table(
            text_table_rows,
            colWidths=[0.35 * inch, col_text_w - 0.35 * inch],
            style=TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ])
        )

        row_table = Table(
            [[icon, text_table]],
            colWidths=[col_icon_w, col_text_w],
            style=TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ])
        )

        story.append(KeepTogether([row_table]))

    doc.build(
        story,
        onFirstPage=draw_header,
        onLaterPages=draw_header,
        canvasmaker=NumberedCanvas,
    )

    return out_pdf
