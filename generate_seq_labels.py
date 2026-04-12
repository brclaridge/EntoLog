"""
Generate sequencing label PDFs:
  BCICH_tube_labels.pdf     — single-line labels for inside tubes
  BCICH_specimen_labels.pdf — three-line labels to pin with specimens

Usage: python3 generate_seq_labels.py
"""

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# Match the font fieldcollect uses for its insect labels
_NARROW_FONT   = "LiberationSansNarrow"
_NARROW_FONT_B = "LiberationSansNarrow-Bold"
pdfmetrics.registerFont(TTFont(_NARROW_FONT,
    "/usr/share/fonts/truetype/liberation/LiberationSansNarrow-Regular.ttf"))
pdfmetrics.registerFont(TTFont(_NARROW_FONT_B,
    "/usr/share/fonts/truetype/liberation/LiberationSansNarrow-Bold.ttf"))

# ── Sequence ──────────────────────────────────────────────────────────────────
PREFIX = "BCICH"
START  = 1
END    = 999
labels = [f"{PREFIX}{n:03d}" for n in range(START, END + 1)]

# ── Page geometry (shared) ────────────────────────────────────────────────────
PAGE_W, PAGE_H = letter
MARGIN  = 0.5 * cm
USABLE_W = PAGE_W - 2 * MARGIN
USABLE_H = PAGE_H - 2 * MARGIN
COLS    = 12
LABEL_W = USABLE_W / COLS


def _write_pdf(output_path, label_content, rows, line_h, font_size, cols=None, label_w=None):
    """
    Render labels in column-major order.

    label_content : list of [(text, bold), ...] lists — one per label
    rows          : number of rows per page
    line_h        : height of each text line in pt
    font_size     : base font size in pt
    cols          : number of columns (defaults to COLS)
    label_w       : column width in pt (defaults to LABEL_W)
    """
    if cols is None:
        cols = COLS
    if label_w is None:
        label_w = LABEL_W

    per_page = cols * rows
    total    = len(label_content)
    pages    = (total + per_page - 1) // per_page
    label_h  = len(label_content[0]) * line_h

    c = canvas.Canvas(output_path, pagesize=letter)

    for page in range(pages):
        page_offset = page * per_page

        for row in range(rows):
            for col in range(cols):
                # column-major indexing
                idx = page_offset + col * rows + row
                if idx >= total:
                    continue
                lines = label_content[idx]

                x     = MARGIN + col * label_w
                top_y = PAGE_H - MARGIN - row * label_h

                c.setFillColorRGB(0, 0, 0)
                for i, (text, font) in enumerate(lines):
                    # font may be a font-name string or a bool (True=bold) for tube labels
                    if isinstance(font, bool):
                        fn = "Helvetica-Bold" if font else "Helvetica"
                    else:
                        fn = font
                    c.setFont(fn, font_size)
                    text_y = top_y - (i + 1) * line_h + (line_h - font_size) / 2
                    c.drawString(x + 1.5, text_y, text)

        if page < pages - 1:
            c.showPage()

    c.save()
    print(f"Wrote {output_path}")
    print(f"  Labels: {total}  ({labels[0]} – {labels[-1]})")
    print(f"  Grid:   {cols} cols × {rows} rows = {per_page} per page, {pages} page(s)")


def generate_tube_labels(output_path="BCICH_tube_labels.pdf"):
    """Single-line labels for inside tubes."""
    font_size = 7.0
    line_h    = font_size + 2.0
    rows      = int(USABLE_H / line_h)

    content = [[(code, True)] for code in labels]
    _write_pdf(output_path, content, rows, line_h, font_size)


def generate_specimen_labels(output_path="BCICH_specimen_labels.pdf"):
    """Three-line labels sized to match fieldcollect's standard insect labels."""
    font_size = 4.0          # same as fieldcollect default
    line_h    = font_size + 0.5  # same as pdf_generator.py
    label_w   = 1.76 * cm    # 49.89 pt — fieldcollect standard width

    cols    = int(USABLE_W / label_w)
    label_h = 3 * line_h
    rows    = int(USABLE_H / label_h)

    content = [
        [
            (code,                          _NARROW_FONT_B),
            ("COI sequencing project",      _NARROW_FONT),
            ("with Daniel Souto, UofU",     _NARROW_FONT),
        ]
        for code in labels
    ]
    _write_pdf(output_path, content, rows, line_h, font_size, cols=cols, label_w=label_w)


if __name__ == "__main__":
    generate_tube_labels()
    generate_specimen_labels()
