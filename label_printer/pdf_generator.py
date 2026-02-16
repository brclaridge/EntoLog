from reportlab.lib.pagesizes import letter
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas
from reportlab.pdfbase.pdfmetrics import stringWidth

from label_formatter import FONT_NAME, FONT_SIZE, _ensure_font_registered

# Page layout
PAGE_W, PAGE_H = letter  # 612 x 792 pt
MARGIN_LEFT = 0.5 * cm
MARGIN_RIGHT = 0.5 * cm
MARGIN_TOP = 0.5 * cm
MARGIN_BOTTOM = 0.5 * cm

SEPARATOR_TEXT = "*" * 11
SEPARATOR_FONT = "Helvetica-Bold"

USABLE_W = PAGE_W - MARGIN_LEFT - MARGIN_RIGHT
USABLE_H = PAGE_H - MARGIN_TOP - MARGIN_BOTTOM


def generate_pdf(label_sets, output_path, settings=None):
    """
    Generate a PDF with labels arranged in a grid.

    label_sets: list of (lines, quantity) where lines is a list of strings
    output_path: where to write the PDF
    settings: optional dict with font/fontSize/labelWidth keys
    """
    if settings:
        font_name = settings.get("font", FONT_NAME)
        font_size = settings.get("fontSize", FONT_SIZE)
        _ensure_font_registered(font_name)
        label_w = settings.get("labelWidth", 1.76) * cm
    else:
        font_name = FONT_NAME
        font_size = FONT_SIZE
        label_w = 1.76 * cm

    COLS = int(USABLE_W / label_w)
    COL_SPACING = USABLE_W / COLS

    line_height = font_size + 0.5
    separator_font_size = font_size
    separator_height = line_height

    c = canvas.Canvas(output_path, pagesize=letter)
    c.setFont(font_name, font_size)

    col = 0
    x = MARGIN_LEFT + col * COL_SPACING
    y_cursor = PAGE_H - MARGIN_TOP

    def ensure_space(height):
        nonlocal col, x, y_cursor
        if y_cursor - height < MARGIN_BOTTOM:
            col += 1
            if col >= COLS:
                c.showPage()
                col = 0
            x = MARGIN_LEFT + col * COL_SPACING
            y_cursor = PAGE_H - MARGIN_TOP
            c.setFont(font_name, font_size)

    italic_font_name = font_name + "-Italic"

    def draw_rich_line(canvas_obj, lx, ly, text, regular_font, italic_font, size):
        """Draw a line with *italic* marker support."""
        parts = text.split("*")
        cx = lx
        for i, part in enumerate(parts):
            if not part:
                continue
            is_italic = i % 2 == 1
            fn = italic_font if is_italic else regular_font
            canvas_obj.setFont(fn, size)
            canvas_obj.drawString(cx, ly, part)
            cx += stringWidth(part, fn, size)
        canvas_obj.setFont(regular_font, size)

    for event_idx, (lines, qty) in enumerate(label_sets):
        if not lines:
            continue
        label_height = len(lines) * line_height
        try:
            copies = max(0, int(qty))
        except (TypeError, ValueError):
            copies = 0
        for _ in range(copies):
            ensure_space(label_height)
            for line_idx, line_text in enumerate(lines):
                if line_text:
                    text_y = y_cursor - (line_idx + 1) * line_height
                    if "*" in line_text:
                        draw_rich_line(c, x, text_y, line_text,
                                       font_name, italic_font_name, font_size)
                    else:
                        c.drawString(x, text_y, line_text)
            y_cursor -= label_height

        # Draw separator between event groups (not after the last event).
        if event_idx < len(label_sets) - 1:
            ensure_space(separator_height)
            c.setFont(SEPARATOR_FONT, separator_font_size)
            sep_y = y_cursor - line_height
            c.drawString(x, sep_y, SEPARATOR_TEXT)
            y_cursor -= separator_height
            c.setFont(font_name, font_size)

    c.save()
    return output_path
