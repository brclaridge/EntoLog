import re
from datetime import datetime, date

from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase import pdfmetrics

from print_settings import FONT_CHOICES, FONT_ITALIC_CHOICES

FONT_PATH = "/usr/share/fonts/truetype/liberation/LiberationSansNarrow-Regular.ttf"
FONT_ITALIC_PATH = "/usr/share/fonts/truetype/liberation/LiberationSansNarrow-Italic.ttf"
FONT_NAME = "LiberationSansNarrow"
FONT_SIZE = 4  # points

# Register default font + italic at import time
pdfmetrics.registerFont(TTFont(FONT_NAME, FONT_PATH))
pdfmetrics.registerFont(TTFont(FONT_NAME + "-Italic", FONT_ITALIC_PATH))

# Max label width in points (~1.76cm)
LABEL_WIDTH_PT = 49.89  # 1.76cm = 49.89pt
MAX_LINES = 5
MIN_LINES = 4

_registered_fonts = {FONT_NAME, FONT_NAME + "-Italic"}


def _ensure_font_registered(font_name):
    if font_name not in _registered_fonts:
        path = FONT_CHOICES.get(font_name)
        if path:
            pdfmetrics.registerFont(TTFont(font_name, path))
            _registered_fonts.add(font_name)
    italic_name = font_name + "-Italic"
    if italic_name not in _registered_fonts:
        italic_path = FONT_ITALIC_CHOICES.get(font_name)
        if italic_path:
            pdfmetrics.registerFont(TTFont(italic_name, italic_path))
            _registered_fonts.add(italic_name)


def _strip_markers(text):
    return text.replace("*", "")


def _text_width(text, font_name=FONT_NAME, font_size=FONT_SIZE):
    from reportlab.pdfbase.pdfmetrics import stringWidth
    return stringWidth(_strip_markers(text), font_name, font_size)


def _abbreviate_name(full_name):
    """'Brandon Claridge' -> 'B Claridge', 'DR Smith' stays 'DR Smith'."""
    parts = full_name.strip().split()
    if len(parts) < 2:
        return full_name
    # If first part is already initials (all caps, <=3 chars), keep as-is
    if len(parts[0]) <= 3 and parts[0] == parts[0].upper():
        return full_name
    return parts[0][0].upper() + " " + " ".join(parts[1:])


# Full state/province name -> postal abbreviation. Mirrors the mapping used by
# the Android app's reverseGeocode so desktop and phone produce identical values.
_STATE_ABBREVIATIONS = {
    # US states
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
    "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
    "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS",
    "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
    "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
    "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK",
    "oregon": "OR", "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC",
    "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT",
    "vermont": "VT", "virginia": "VA", "washington": "WA", "west virginia": "WV",
    "wisconsin": "WI", "wyoming": "WY",
    # US federal district and territories
    "district of columbia": "DC", "puerto rico": "PR", "guam": "GU",
    "american samoa": "AS", "u.s. virgin islands": "VI",
    "united states virgin islands": "VI", "northern mariana islands": "MP",
    # Canadian provinces and territories
    "alberta": "AB", "british columbia": "BC", "manitoba": "MB",
    "new brunswick": "NB", "newfoundland and labrador": "NL",
    "northwest territories": "NT", "nova scotia": "NS", "nunavut": "NU",
    "ontario": "ON", "prince edward island": "PE", "quebec": "QC",
    "québec": "QC", "saskatchewan": "SK", "yukon": "YT",
}


def abbreviate_state(name):
    """'California' -> 'CA'. Case-insensitive; names not in the map (e.g.
    international regions, or values already abbreviated) are returned as-is."""
    if not name:
        return name
    trimmed = name.strip()
    return _STATE_ABBREVIATIONS.get(trimmed.lower(), trimmed)


_ROMAN_MONTHS = {
    1: "i",
    2: "ii",
    3: "iii",
    4: "iv",
    5: "v",
    6: "vi",
    7: "vii",
    8: "viii",
    9: "ix",
    10: "x",
    11: "xi",
    12: "xii",
}


def _parse_date_obj(value):
    if not value:
        return None
    v = value.strip()
    try:
        return date.fromisoformat(v)
    except Exception:
        pass
    try:
        return datetime.fromisoformat(v.replace("Z", "+00:00")).date()
    except Exception:
        pass
    for fmt in (
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%m/%d/%Y",
    ):
        try:
            return datetime.strptime(v, fmt).date()
        except Exception:
            continue
    return None


_MONTH_ABBR = {
    1: "JAN", 2: "FEB", 3: "MAR", 4: "APR", 5: "MAY", 6: "JUN",
    7: "JUL", 8: "AUG", 9: "SEP", 10: "OCT", 11: "NOV", 12: "DEC",
}


def _format_date(iso_str, fmt="roman"):
    """Convert stored date/datetime to display format."""
    d = _parse_date_obj(iso_str)
    if not d:
        return ""
    if fmt == "iso":
        return d.isoformat()
    if fmt == "dmy":
        return f"{d.day} {_MONTH_ABBR[d.month]} {d.year}"
    return f"{d.day}.{_ROMAN_MONTHS[d.month]}.{d.year}"


def _format_date_range(start_iso, end_iso, fmt="roman"):
    """Format a date range with an en dash and compact shared components."""
    if not start_iso and not end_iso:
        return ""
    if not start_iso:
        return _format_date(end_iso, fmt)
    if not end_iso:
        return _format_date(start_iso, fmt)

    start = _parse_date_obj(start_iso)
    end = _parse_date_obj(end_iso)
    if not start or not end:
        return _format_date(start_iso, fmt) or _format_date(end_iso, fmt)

    if fmt == "iso":
        if start == end:
            return start.isoformat()
        return f"{start.isoformat()} – {end.isoformat()}"

    if fmt == "dmy":
        if start.year == end.year and start.month == end.month:
            return f"{start.day}–{end.day} {_MONTH_ABBR[start.month]} {start.year}"
        if start.year == end.year:
            return (
                f"{start.day} {_MONTH_ABBR[start.month]} – "
                f"{end.day} {_MONTH_ABBR[end.month]} {start.year}"
            )
        return (
            f"{start.day} {_MONTH_ABBR[start.month]} {start.year} – "
            f"{end.day} {_MONTH_ABBR[end.month]} {end.year}"
        )

    # roman (default)
    if start.year == end.year and start.month == end.month:
        return f"{start.day}–{end.day}.{_ROMAN_MONTHS[start.month]}.{start.year}"
    if start.year == end.year:
        return (
            f"{start.day}.{_ROMAN_MONTHS[start.month]}–"
            f"{end.day}.{_ROMAN_MONTHS[end.month]}.{start.year}"
        )
    return (
        f"{start.day}.{_ROMAN_MONTHS[start.month]}.{start.year}–"
        f"{end.day}.{_ROMAN_MONTHS[end.month]}.{end.year}"
    )


def _do_wrap(text, max_width, break_pattern,
             font_name=FONT_NAME, font_size=FONT_SIZE):
    """Greedy line wrapping using the given break_pattern regex.

    Wraps all text — never truncates.
    """
    lines = []
    remaining = text

    while remaining:
        if _text_width(remaining, font_name, font_size) <= max_width:
            lines.append(remaining)
            remaining = ""
            break

        best_break = -1
        for m in re.finditer(break_pattern, remaining):
            pos = m.end()
            if _text_width(remaining[:pos], font_name, font_size) <= max_width:
                best_break = pos
            else:
                break

        # If no break found, force break at max width
        if best_break == -1:
            for i in range(len(remaining), 0, -1):
                if _text_width(remaining[:i], font_name, font_size) <= max_width:
                    best_break = i
                    break
            if best_break == -1:
                best_break = 1

        lines.append(remaining[:best_break].rstrip())
        remaining = remaining[best_break:].lstrip()

    return lines


def _pack_fields(parts, max_width, font_name=FONT_NAME, font_size=FONT_SIZE,
                 allow_dot_break=True, force_break_before=None):
    """Greedily pack fields onto lines, joined with "; ".

    A field is never split across lines. The only exception is a field that is
    physically wider than the label on its own — that must wrap within itself,
    since there is no other way to fit it.

    ``force_break_before`` is an index into ``parts`` at which to start a new
    line even if the field would otherwise fit on the current one. It is used to
    push the locality onto its own line after the geographic header.
    """
    break_pattern = r"[. ]" if allow_dot_break else r" "
    lines = []
    current = ""

    for i, raw in enumerate(parts):
        part = (raw or "").strip()
        if not part:
            continue

        forced = force_break_before is not None and i == force_break_before
        candidate = part if not current else current + "; " + part

        # Flush the current line if this field is forced onto a new line or it
        # simply won't fit alongside what's already there.
        if current and (forced or
                        _text_width(candidate, font_name, font_size) > max_width):
            lines.append(current)
            current = ""

        if not current:
            # Start a fresh line with this field. If the field alone is wider
            # than the label, wrap it within itself (the unavoidable split).
            if _text_width(part, font_name, font_size) <= max_width:
                current = part
            else:
                sub = _do_wrap(part, max_width, break_pattern, font_name, font_size)
                lines.extend(sub[:-1])
                current = sub[-1] if sub else ""
        else:
            current = candidate

    if current:
        lines.append(current)

    # Clean up trailing separators and whitespace on all lines
    lines = [line.rstrip().rstrip(";").rstrip() for line in lines]

    return lines


def format_event(event, settings=None):
    """Convert a collecting event dict to label lines."""
    if settings:
        font_name = settings.get("font", FONT_NAME)
        font_size = settings.get("fontSize", FONT_SIZE)
        min_lines = settings.get("minLines", MIN_LINES)
        max_lines = settings.get("maxLines", MAX_LINES)
        allow_dot_break = (
            settings.get("allowDateDotBreak", True)
            or settings.get("allowCoordDotBreak", True)
        )
        _ensure_font_registered(font_name)
        label_width_cm = settings.get("labelWidth", 1.76)
    else:
        font_name = FONT_NAME
        font_size = FONT_SIZE
        min_lines = MIN_LINES
        max_lines = MAX_LINES
        allow_dot_break = True
        label_width_cm = 1.76
    label_width = label_width_cm * 28.3465 * 1.05  # cm to points, +5% width

    # coordPrecision may be stored as a string (e.g. from form/JSON); coerce to
    # an int so the precision override actually applies. None / blank / invalid
    # falls back to the coordinate's own stored precision.
    coord_decimals = event.get("coordPrecision")
    try:
        coord_decimals = int(float(coord_decimals))
    except (ValueError, TypeError):
        coord_decimals = None
    parts = []

    # Country; State; County — use county value as-is for international flexibility
    country = event.get("country", "")
    state = event.get("stateProvince", "")
    county = event.get("county", "")

    geo_parts = []
    if country:
        if country.upper() in ("US", "USA", "UNITED STATES"):
            geo_parts.append(f"USA; {state}" if state else "USA")
        else:
            geo_parts.append(f"{country}; {state}" if state else country)
    elif state:
        geo_parts.append(state)
    if county:
        geo_parts.append(county)
    parts.extend(geo_parts)

    # Locality — remember its position so it can be pushed onto its own line.
    locality = event.get("locality", "")
    locality_idx = None
    if locality:
        locality_idx = len(parts)
        parts.append(locality)

    # Elevation
    elev = event.get("elevation")
    if elev is not None:
        try:
            parts.append(f"{int(elev)}m")
        except (ValueError, TypeError):
            pass

    # Lat/Lon
    lat = event.get("latitude")
    lon = event.get("longitude")
    if lat is not None and lon is not None:
        try:
            def _coord_text(v):
                # Show exactly what is stored in the field. coordPrecision only
                # caps the number of decimals (trims excess) — it never pads,
                # so the label always reflects the field's actual precision.
                s = str(v).strip()
                if isinstance(coord_decimals, int):
                    actual = len(s.split(".", 1)[1]) if "." in s else 0
                    if actual > coord_decimals:
                        s = f"{float(v):.{coord_decimals}f}"
                return s

            lat_s = _coord_text(lat)
            lon_s = _coord_text(lon)
            coord_str = f"{lat_s} {lon_s}"
            parts.append(coord_str)
        except (ValueError, TypeError):
            pass

    # Date — use date range if start/end are set, otherwise use createdAt
    start_dt = event.get("startDateTime")
    end_dt = event.get("endDateTime")
    created = event.get("createdAt")

    if start_dt and end_dt:
        date_str = _format_date_range(start_dt, end_dt)
    else:
        date_str = _format_date(created)
    if date_str:
        parts.append(date_str)

    # Collectors
    collectors = event.get("collectors", [])
    if collectors:
        abbreviated = [_abbreviate_name(c) for c in collectors]
        parts.append(", ".join(abbreviated))

    # Collection technique
    technique = event.get("collectionTechnique")
    if technique:
        parts.append(technique)

    # Host (last field) — optionally excluded for split-label mode
    exclude_host = settings.get("_exclude_host", False) if settings else False
    host = event.get("host")
    if host and not exclude_host:
        parts.append(host)

    pack_args = dict(font_name=font_name, font_size=font_size,
                     allow_dot_break=allow_dot_break)

    # Compact greedy packing (fields never split across lines).
    greedy_lines = _pack_fields(parts, label_width, **pack_args)

    # Rule: put the locality on its own line (line 2, right after the geographic
    # header) — but only when a header actually precedes it and the forced break
    # keeps the label within max_lines. If honouring it would spill onto an
    # extra line, fall back to the compact greedy layout. Field integrity is
    # independent of this: _pack_fields never splits a field either way.
    if locality_idx is not None and locality_idx > 0:
        forced_lines = _pack_fields(parts, label_width,
                                    force_break_before=locality_idx, **pack_args)
        lines = forced_lines if len(forced_lines) <= max_lines else greedy_lines
    else:
        lines = greedy_lines

    # Keep a minimum physical label height for easier cutting/handling.
    while len(lines) < min_lines:
        lines.append("")

    return lines


def format_event_labels(event, qty, settings=None):
    """Return a list of (lines, qty) tuples for one event.

    Normally returns one entry.  When splitHostLabel is enabled and the
    event has host data, returns two: the main label and a host-only label.
    """
    split = settings.get("splitHostLabel", False) if settings else False
    host = event.get("host")

    if split and host:
        # Main label without host
        split_settings = dict(settings, _exclude_host=True) if settings else {"_exclude_host": True}
        main_lines = format_event(event, split_settings)

        # Host-only label
        font_name = settings.get("font", FONT_NAME) if settings else FONT_NAME
        font_size = settings.get("fontSize", FONT_SIZE) if settings else FONT_SIZE
        min_lines = settings.get("minLines", MIN_LINES) if settings else MIN_LINES
        max_lines = settings.get("maxLines", MAX_LINES) if settings else MAX_LINES
        label_width_cm = settings.get("labelWidth", 1.76) if settings else 1.76
        label_width = label_width_cm * 28.3465 * 1.05  # +5% width
        _ensure_font_registered(font_name)

        host_lines = _pack_fields([host], label_width,
                                  font_name=font_name, font_size=font_size)
        while len(host_lines) < min_lines:
            host_lines.append("")

        return [(main_lines, qty), (host_lines, qty)]

    return [(format_event(event, settings), qty)]
