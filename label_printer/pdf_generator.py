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


def calculate_label_layout(events, settings=None):
    """
    Calculate label layout and page usage without generating PDF.
    
    Returns dict with:
      - pages: list of dicts with used_pct (actual area filled)
      - total_pages: number of pages
      - total_labels: total number of labels
    """
    if settings:
        font_name = settings.get("font", FONT_NAME)
        font_size = settings.get("fontSize", FONT_SIZE)
        label_width_cm = settings.get("labelWidth", 1.76)
    else:
        font_name = FONT_NAME
        font_size = FONT_SIZE
        label_width_cm = 1.76
    
    _ensure_font_registered(font_name)
    label_w = label_width_cm * cm
    COLS = int(USABLE_W / label_w)
    
    line_height = font_size + 0.5
    
    from label_formatter import format_event_labels
    
    label_groups = []
    for event in events:
        qty = event.get("labelQuantity", 10)
        try:
            qty = int(qty)
        except (TypeError, ValueError):
            qty = 10
        
        label_sets = format_event_labels(event, qty, settings=settings)
        for lines, qty in label_sets:
            num_lines = len(lines)
            label_groups.append({
                "lines": num_lines,
                "qty": qty,
            })
    
    total_labels = 0
    col = 0
    y_cursor = PAGE_H - MARGIN_TOP
    
    # Track height used in each column of each page
    # page_columns[page_num][col_num] = used_height
    page_columns = [[0] * COLS]  # Start with page 0, all columns at 0
    
    def ensure_space(height):
        nonlocal col, y_cursor, page_columns
        
        if y_cursor - height < MARGIN_BOTTOM:
            # Need more space - move to next column or page
            # First, record the height used in current column
            col_height = (PAGE_H - MARGIN_TOP) - y_cursor
            page_num = len(page_columns) - 1
            page_columns[page_num][col] = col_height
            
            col += 1
            if col >= COLS:
                # Start new page
                page_columns.append([0] * COLS)
                col = 0
            y_cursor = PAGE_H - MARGIN_TOP
    
    def add_height(height):
        nonlocal y_cursor
        y_cursor -= height
    
    for i, group in enumerate(label_groups):
        label_height = group["lines"] * line_height
        num_copies = group["qty"]
        
        for _ in range(num_copies):
            ensure_space(label_height)
            add_height(label_height)
            total_labels += 1
        
        # Add separator between event groups
        if i < len(label_groups) - 1:
            ensure_space(line_height)
            add_height(line_height)
    
    # Record the last column's height
    if total_labels > 0:
        final_col_height = (PAGE_H - MARGIN_TOP) - y_cursor
        page_num = len(page_columns) - 1
        page_columns[page_num][col] = final_col_height
    
    # Calculate actual page usage (sum of column areas / total page area)
    result_pages = []
    for page_num, columns in enumerate(page_columns):
        total_col_height = sum(columns)
        max_possible = USABLE_H * COLS  # All columns full
        pct = int((total_col_height / max_possible) * 100)
        result_pages.append({
            "page_num": page_num + 1,
            "used_pct": min(100, pct),
        })
    
    return {
        "pages": result_pages,
        "total_pages": len(result_pages),
        "total_labels": total_labels,
    }
