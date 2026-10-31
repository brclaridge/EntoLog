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
# Hard cap on lines per label (settings key "maxLines"). Enforced by the layout
# ladder in _lay_out: an event that cannot be squeezed into this many lines
# overflows onto a continuation label rather than growing past it.
MAX_LINES = 5
MIN_LINES = 4

# Field kinds, in the order they appear on a label. The layout ladder grants
# concessions per kind, so packing needs to know what each string is.
GEO = "geo"
LOCALITY = "locality"
ELEVATION = "elevation"
COORDS = "coords"
DATE = "date"
COLLECTORS = "collectors"
TECHNIQUE = "technique"
HOST = "host"

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


def _pack_fields(fields, max_width, font_name=FONT_NAME, font_size=FONT_SIZE,
                 split_kinds=frozenset(), dot_break_kinds=frozenset(),
                 force_break_before=None):
    """Greedily pack fields onto lines, joined with "; ".

    ``fields`` is a list of ``(kind, text)`` pairs, where kind is one of the
    field constants above. Kind drives the two concessions the layout ladder
    hands out rung by rung:

    ``split_kinds``      fields that may flow across a line break instead of
                         being placed whole on a fresh line.
    ``dot_break_kinds``  fields that may additionally break at "." — used to
                         wrap dates and coordinates mid-value.

    A field not named in ``split_kinds`` is never split, with one unavoidable
    exception: a field physically wider than the label has nowhere else to go.

    ``force_break_before`` is an index into ``fields`` at which to start a new
    line even if the field would otherwise fit on the current one. It is used to
    push the locality onto its own line after the geographic header.
    """
    lines = []
    current = ""

    for i, (kind, raw) in enumerate(fields):
        part = (raw or "").strip()
        if not part:
            continue

        pattern = r"[. ]" if kind in dot_break_kinds else r" "
        forced = force_break_before is not None and i == force_break_before

        if forced and current:
            lines.append(current)
            current = ""

        if kind in split_kinds:
            # Flowable: fill the rest of the current line and continue onto the
            # next, rather than starting fresh. This is what buys back lines.
            text = part if not current else current + "; " + part
            sub = _do_wrap(text, max_width, pattern, font_name, font_size)
            lines.extend(sub[:-1])
            current = sub[-1] if sub else ""
            continue

        candidate = part if not current else current + "; " + part

        # Flush the current line if this field won't fit alongside what's there.
        if current and _text_width(candidate, font_name, font_size) > max_width:
            lines.append(current)
            current = ""

        if not current:
            # Start a fresh line with this field. If the field alone is wider
            # than the label, wrap it within itself (the unavoidable split).
            if _text_width(part, font_name, font_size) <= max_width:
                current = part
            else:
                sub = _do_wrap(part, max_width, pattern, font_name, font_size)
                lines.extend(sub[:-1])
                current = sub[-1] if sub else ""
        else:
            current = candidate

    if current:
        lines.append(current)

    # Clean up trailing separators and whitespace on all lines
    lines = [line.rstrip().rstrip(";").rstrip() for line in lines]

    return lines


def _rungs(locality_idx, allow_date_dot, allow_coord_dot):
    """The layout ladder, in order of increasing concession.

    Each rung is a kwargs dict for _pack_fields. The first rung whose result
    fits within max_lines wins; if none do, the caller overflows onto a second
    label using the last rung. Font size and label width are never touched —
    those are the user's settings, not ours to adjust.
    """
    ladder = []

    # 1. Prettiest: locality on its own line, every field intact.
    if locality_idx is not None and locality_idx > 0:
        ladder.append(dict(force_break_before=locality_idx))

    # 2. Compact: greedy packing, every field still intact.
    ladder.append(dict())

    # 3. Let the wordy prose fields flow across line breaks. Technique is here
    # because in practice it carries habitat description ("Malaise trap on edge
    # of aspen stand and meadow"), not just a method name. Host is deliberately
    # left out — it is a taxon name and should not wrap mid-binomial; letting it
    # flow saved only one event in 180 and is not worth splitting a species.
    flow = {LOCALITY, COLLECTORS, TECHNIQUE}
    ladder.append(dict(split_kinds=set(flow)))

    # 4. Break the date mid-value at a ".".
    dots = set()
    if allow_date_dot:
        flow = flow | {DATE}
        dots = dots | {DATE}
        ladder.append(dict(split_kinds=set(flow), dot_break_kinds=set(dots)))

    # 5. Break the coordinates mid-value at a ".".
    if allow_coord_dot:
        flow = flow | {COORDS}
        dots = dots | {COORDS}
        ladder.append(dict(split_kinds=set(flow), dot_break_kinds=set(dots)))

    return ladder


def _lay_out(fields, max_width, max_lines, locality_idx,
             allow_date_dot, allow_coord_dot, font_name, font_size):
    """Run the ladder. Returns a list of labels, each a list of lines.

    Returns more than one label only when the content cannot be made to fit in
    max_lines by any rung — the overflow spills onto a continuation label,
    split on a field boundary so no value is cut in half.
    """
    cfg = dict(font_name=font_name, font_size=font_size)
    ladder = _rungs(locality_idx, allow_date_dot, allow_coord_dot)

    for rung in ladder:
        lines = _pack_fields(fields, max_width, **cfg, **rung)
        if len(lines) <= max_lines:
            return [lines]

    # Nothing fits. Keep the largest whole-field prefix that does, and push the
    # rest onto a continuation label (which may itself overflow again).
    #
    # The prefix is laid out by recursing, not by reusing the last rung: with
    # fewer fields to place it will often fit on an earlier, prettier rung, and
    # there is no reason to break a date or coordinate on a label that had room
    # anyway. Recursion terminates because k < len(fields) strictly shrinks it.
    for k in range(len(fields) - 1, 0, -1):
        head = _lay_out(fields[:k], max_width, max_lines,
                        locality_idx if (locality_idx or 0) < k else None,
                        allow_date_dot, allow_coord_dot, font_name, font_size)
        if len(head) == 1:
            tail = _lay_out(fields[k:], max_width, max_lines, None,
                            allow_date_dot, allow_coord_dot, font_name, font_size)
            return head + tail

    # Degenerate: the very first field alone needs more than max_lines. There is
    # no field boundary to split on, so break it by line instead.
    lines = _pack_fields(fields, max_width, **cfg, **ladder[-1])
    return [lines[i:i + max_lines] for i in range(0, len(lines), max_lines)]


def _label_config(settings):
    """Pull the layout knobs out of settings, applying defaults."""
    if settings:
        font_name = settings.get("font", FONT_NAME)
        font_size = settings.get("fontSize", FONT_SIZE)
        min_lines = settings.get("minLines", MIN_LINES)
        max_lines = settings.get("maxLines", MAX_LINES)
        # Two independent rungs of the ladder, not one blanket flag: each only
        # ever loosens breaking for its own field kind.
        allow_date_dot = settings.get("allowDateDotBreak", True)
        allow_coord_dot = settings.get("allowCoordDotBreak", True)
        date_format = settings.get("dateFormat", "roman")
        label_width_cm = settings.get("labelWidth", 1.76)
        _ensure_font_registered(font_name)
    else:
        font_name = FONT_NAME
        font_size = FONT_SIZE
        min_lines = MIN_LINES
        max_lines = MAX_LINES
        allow_date_dot = True
        allow_coord_dot = True
        date_format = "roman"
        label_width_cm = 1.76

    if min_lines > max_lines:
        min_lines = max_lines

    return {
        "font_name": font_name,
        "font_size": font_size,
        "min_lines": min_lines,
        "max_lines": max_lines,
        "allow_date_dot": allow_date_dot,
        "allow_coord_dot": allow_coord_dot,
        "date_format": date_format,
        # cm to points, +5% width
        "label_width": label_width_cm * 28.3465 * 1.05,
    }


def _build_fields(event, exclude_host=False, date_format="roman"):
    """Convert a collecting event dict to a list of (kind, text) fields.

    Returns (fields, locality_idx) — the index is where the forced
    locality-on-its-own-line break goes, or None if there is no locality.
    """
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
    parts.extend((GEO, g) for g in geo_parts)

    # Locality — remember its position so it can be pushed onto its own line.
    locality = event.get("locality", "")
    locality_idx = None
    if locality:
        locality_idx = len(parts)
        parts.append((LOCALITY, locality))

    # Elevation
    elev = event.get("elevation")
    if elev is not None:
        try:
            parts.append((ELEVATION, f"{int(elev)}m"))
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
            parts.append((COORDS, coord_str))
        except (ValueError, TypeError):
            pass

    # Date — use date range if start/end are set, otherwise use createdAt
    start_dt = event.get("startDateTime")
    end_dt = event.get("endDateTime")
    created = event.get("createdAt")

    if start_dt and end_dt:
        date_str = _format_date_range(start_dt, end_dt, date_format)
    else:
        date_str = _format_date(created, date_format)
    if date_str:
        parts.append((DATE, date_str))

    # Collectors
    collectors = event.get("collectors", [])
    if collectors:
        abbreviated = [_abbreviate_name(c) for c in collectors]
        parts.append((COLLECTORS, ", ".join(abbreviated)))

    # Collection technique
    technique = event.get("collectionTechnique")
    if technique:
        parts.append((TECHNIQUE, technique))

    # Host (last field) — optionally excluded for split-label mode
    host = event.get("host")
    if host and not exclude_host:
        parts.append((HOST, host))

    return parts, locality_idx


def format_event(event, settings=None):
    """Convert a collecting event dict to the lines of its first label.

    Kept for callers that only ever want one label. Use format_event_labels to
    get the continuation labels an overflowing event produces.
    """
    return format_event_all_labels(event, settings)[0]


def format_event_all_labels(event, settings=None, exclude_host=False):
    """Lay an event out, returning a list of labels (each a list of lines)."""
    cfg = _label_config(settings)
    fields, locality_idx = _build_fields(
        event, exclude_host=exclude_host, date_format=cfg["date_format"])

    labels = _lay_out(fields, cfg["label_width"], cfg["max_lines"], locality_idx,
                      cfg["allow_date_dot"], cfg["allow_coord_dot"],
                      cfg["font_name"], cfg["font_size"])

    # Keep a minimum physical label height for easier cutting/handling.
    for lines in labels:
        while len(lines) < cfg["min_lines"]:
            lines.append("")

    return labels


def format_event_labels(event, qty, settings=None):
    """Return a list of (lines, qty) tuples for one event.

    Usually one entry. More than one when the event needs it:

    * splitHostLabel is on and the event has a host — the host is moved to its
      own label even if it would have fit, and
    * the remaining content still cannot be squeezed into maxLines, in which
      case it overflows onto continuation labels.

    Both can happen at once, so this may return three or more labels.
    """
    split = settings.get("splitHostLabel", False) if settings else False
    host = event.get("host")

    if split and host:
        # Host moved off by request. The main label may still overflow on its
        # own, so it goes through the same ladder.
        labels = format_event_all_labels(event, settings, exclude_host=True)

        cfg = _label_config(settings)
        host_labels = _lay_out([(HOST, host)], cfg["label_width"],
                               cfg["max_lines"], None,
                               cfg["allow_date_dot"], cfg["allow_coord_dot"],
                               cfg["font_name"], cfg["font_size"])
        for lines in host_labels:
            while len(lines) < cfg["min_lines"]:
                lines.append("")

        return [(lines, qty) for lines in labels + host_labels]

    return [(lines, qty) for lines in format_event_all_labels(event, settings)]
