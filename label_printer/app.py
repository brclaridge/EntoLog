import glob
import os
import re
import tempfile
import threading
import time
import uuid
import json
from datetime import datetime, date
from urllib import error as url_error
from urllib import request as url_request

from flask import Flask, render_template, request, send_file, redirect, url_for, flash, jsonify


def _parse_datetime(value):
    """Try to parse a date or datetime and return a date-only ISO string YYYY-MM-DD or None."""
    if not value or not value.strip():
        return None
    v = value.strip()

    # If already a YYYY-MM-DD, accept as-is
    try:
        d = date.fromisoformat(v)
        return d.isoformat()
    except Exception:
        pass

    # Try datetime ISO (with optional Z/offset/fractional seconds)
    try:
        dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
        return dt.date().isoformat()
    except Exception:
        pass

    # Fallback common formats
    for fmt in (
        "%Y-%m-%d",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y/%m/%d",
        "%m/%d/%Y %H:%M",
        "%m/%d/%Y %H:%M:%S",
        "%m/%d/%Y",
        "%m-%d-%Y",
        "%m.%d.%Y",
    ):
        try:
            dt = datetime.strptime(v, fmt)
            return dt.date().isoformat()
        except Exception:
            continue

    return None


COORD_MAX_DECIMALS = 5  # ~1 m precision; avoids false precision on labels


def _coord_decimal_places(raw):
    """Count the decimal places in a coordinate string (trailing zeros kept)."""
    s = str(raw or "").strip().replace(",", ".")
    if "." in s:
        return len(s.split(".", 1)[1])
    return 0


def _normalize_decimal_coord(value, decimals=None, max_places=COORD_MAX_DECIMALS):
    """Normalize a decimal coordinate for storage.

    Formats to ``decimals`` places, capped at ``max_places`` to avoid false
    precision. ``decimals`` defaults to ``max_places`` (used for DMS/DDM
    conversions). Trailing zeros are NEVER stripped — a value is only ever
    padded, never trimmed. (The old behaviour forced every coordinate to 6
    decimal places.)
    """
    if decimals is None:
        decimals = max_places
    decimals = max(0, min(decimals, max_places))
    return f"{value:.{decimals}f}"


def _parse_number_component(raw):
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    s = s.replace(",", ".")
    m = re.search(r"[-+]?\d+(?:\.\d+)?", s)
    if not m:
        return None
    try:
        return float(m.group(0))
    except Exception:
        return None


def _signed_with_direction(value, direction):
    d = (direction or "").strip().upper()
    if d in ("S", "W"):
        return -abs(value)
    if d in ("N", "E"):
        return abs(value)
    return value


def _parse_dms_coordinate(degrees_raw, minutes_raw, seconds_raw, direction, is_lat):
    if not any([degrees_raw, minutes_raw, seconds_raw, direction]):
        return None
    deg_val = _parse_number_component(degrees_raw)
    minutes_val = _parse_number_component(minutes_raw)
    seconds_val = _parse_number_component(seconds_raw)
    if deg_val is None:
        return None
    deg = abs(deg_val)
    minutes = abs(minutes_val if minutes_val is not None else 0.0)
    seconds = abs(seconds_val if seconds_val is not None else 0.0)
    if minutes >= 60 or seconds >= 60:
        return None
    value = deg + (minutes / 60.0) + (seconds / 3600.0)
    value = _signed_with_direction(value, direction)
    limit = 90 if is_lat else 180
    if abs(value) > limit:
        return None
    return value


def _parse_dm_coordinate(degrees_raw, decimal_minutes_raw, direction, is_lat):
    if not any([degrees_raw, decimal_minutes_raw, direction]):
        return None
    deg_val = _parse_number_component(degrees_raw)
    dec_minutes_val = _parse_number_component(decimal_minutes_raw)
    if deg_val is None or dec_minutes_val is None:
        return None
    deg = abs(deg_val)
    dec_minutes = abs(dec_minutes_val)
    if dec_minutes >= 60:
        return None
    value = deg + (dec_minutes / 60.0)
    value = _signed_with_direction(value, direction)
    limit = 90 if is_lat else 180
    if abs(value) > limit:
        return None
    return value


def _has_any_coord_value(*values):
    for value in values:
        if value is not None and str(value).strip():
            return True
    return False


def _parse_decimal_coordinate(raw, is_lat):
    value = _parse_number_component(raw)
    if value is None:
        return None
    limit = 90 if is_lat else 180
    if abs(value) > limit:
        return None
    return value

def _safe_int(s):
    """Parse string to int, return None on failure."""
    if not s or not s.strip():
        return None
    try:
        return int(s.strip())
    except (ValueError, TypeError):
        return None


def _safe_float(s):
    """Parse string to float, return None on failure."""
    if not s or not s.strip():
        return None
    try:
        return float(s.strip())
    except (ValueError, TypeError):
        return None


import local_store
from label_formatter import format_event, format_event_labels, _format_date, _format_date_range, abbreviate_state
from pdf_generator import generate_pdf, calculate_label_layout
from print_settings import load_settings, save_settings, FONT_CHOICES, FONT_SIZE_CHOICES, MIN_LINES_CHOICES, MAX_LINES_CHOICES, LABEL_WIDTH_CHOICES, DATE_FORMAT_CHOICES

app = Flask(__name__)
app.config["TEMPLATES_AUTO_RELOAD"] = True
app.secret_key = os.urandom(24)


@app.template_filter("daterange")
def daterange_filter(start_iso, end_iso, fmt="roman"):
    """Format a date range with compression."""
    return _format_date_range(start_iso, end_iso, fmt)


@app.template_filter("formatdate")
def formatdate_filter(iso_str, fmt="roman"):
    """Format a single date."""
    return _format_date(iso_str, fmt)


@app.template_filter("romandate")
def romandate_filter(iso_str):
    """Format a single date using Roman numeral months (legacy filter)."""
    return _format_date(iso_str)


_cached_events = None


def _fetch_inat_observation(observation_id):
    obs_id = str(observation_id or "").strip()
    if not obs_id.isdigit():
        raise ValueError("Observation ID must be numeric")
    endpoint = f"https://api.inaturalist.org/v1/observations/{obs_id}"
    req = url_request.Request(
        endpoint,
        headers={
            "Accept": "application/json",
            "User-Agent": "FieldCollect-Label-Printer/1.0",
        },
    )
    with url_request.urlopen(req, timeout=10) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    results = payload.get("results") or []
    if not results:
        raise LookupError("Observation not found")
    return results[0]


def _parse_inat_coordinates(observation):
    geojson = observation.get("geojson") or {}
    coords = geojson.get("coordinates") or []
    if isinstance(coords, list) and len(coords) >= 2:
        lon_val = _parse_decimal_coordinate(coords[0], False)
        lat_val = _parse_decimal_coordinate(coords[1], True)
        if lat_val is not None and lon_val is not None:
            return (
                _normalize_decimal_coord(lat_val, _coord_decimal_places(coords[1])),
                _normalize_decimal_coord(lon_val, _coord_decimal_places(coords[0])),
            )

    location = str(observation.get("location") or "").strip()
    if location and "," in location:
        parts = [p.strip() for p in location.split(",")]
        if len(parts) >= 2:
            lat_val = _parse_decimal_coordinate(parts[0], True)
            lon_val = _parse_decimal_coordinate(parts[1], False)
            if lat_val is not None and lon_val is not None:
                return (
                    _normalize_decimal_coord(lat_val, _coord_decimal_places(parts[0])),
                    _normalize_decimal_coord(lon_val, _coord_decimal_places(parts[1])),
                )

    return None, None


def _inat_prefill_fields(observation, observation_id):
    created_at = (
        _parse_datetime(observation.get("observed_on"))
        or _parse_datetime(observation.get("time_observed_at"))
        or _parse_datetime(observation.get("created_at"))
    )

    latitude, longitude = _parse_inat_coordinates(observation)

    accuracy = (
        observation.get("public_positional_accuracy")
        if observation.get("public_positional_accuracy") is not None
        else observation.get("positional_accuracy")
    )
    try:
        gps_accuracy = float(accuracy) if accuracy is not None else None
    except Exception:
        gps_accuracy = None

    observer = observation.get("user") or {}
    observer_name = str(observer.get("name") or observer.get("login") or "").strip()

    description = str(observation.get("description") or "").strip()
    source_url = f"https://www.inaturalist.org/observations/{observation_id}"
    note_parts = []
    if description:
        note_parts.append(description)
    note_parts.append(f"iNaturalist observation: {source_url}")

    locality = str(observation.get("place_guess") or "").strip()

    payload = {
        "createdAt": created_at or "",
        "latitude": latitude or "",
        "longitude": longitude or "",
        "gpsAccuracy": str(int(gps_accuracy)) if gps_accuracy is not None and gps_accuracy.is_integer() else (str(gps_accuracy) if gps_accuracy is not None else ""),
        "locality": locality,
        "collectors": observer_name,
        "notes": "\n\n".join(note_parts).strip(),
        "collectionTechnique": "iNaturalist observation",
    }
    return payload


_GENERAL_ID_RE = re.compile(r"^(\d{6})-(\d{3})$")


def _yymmdd(iso_value):
    """'2026-08-26' (or a longer ISO datetime) -> '260826'; '' if unusable."""
    v = (iso_value or "")[:10]
    if len(v) != 10 or v[4] != "-" or v[7] != "-":
        return ""
    return v[2:4] + v[5:7] + v[8:10]


def _trap_event_id(trap_code, end_iso):
    """Trap sample ID: trap code + bottle-collection (end) date, e.g. SAM2-260826."""
    code = (trap_code or "").strip()
    end = _yymmdd(end_iso)
    if not code or not end:
        return ""
    return f"{code}-{end}"


def _next_general_id(date_iso, exclude_uuid=None):
    """Next free YYMMDD-NNN for a one-day event on this date."""
    prefix = _yymmdd(date_iso)
    if not prefix:
        return ""
    used = 0
    for e in _cached_events or []:
        if exclude_uuid and e.get("uuid") == exclude_uuid:
            continue
        m = _GENERAL_ID_RE.match((e.get("collectionCode") or "").strip())
        if m and m.group(1) == prefix:
            used = max(used, int(m.group(2)))
    return f"{prefix}-{used + 1:03d}"


def _is_trap_sample(event):
    """Explicit checkbox wins; older records fall back to having a date range."""
    if "isTrapSample" in event:
        return bool(event.get("isTrapSample"))
    return bool(event.get("startDateTime") and event.get("endDateTime"))


def _roll_event_id(event, exclude_uuid=None):
    """Event ID for a freshly duplicated event, or None to keep the current one."""
    if _is_trap_sample(event):
        if event.get("trapCode"):
            return _trap_event_id(event.get("trapCode"), event.get("endDateTime"))
        return None
    code = (event.get("collectionCode") or "").strip()
    if _GENERAL_ID_RE.match(code):
        return _next_general_id(event.get("createdAt"), exclude_uuid) or None
    return None


def _load_events():
    global _cached_events
    try:
        _cached_events = local_store.load_events()
    except Exception as e:
        flash(f"Error loading events: {e}", "error")
        _cached_events = []
    return _cached_events


def _save_events():
    global _cached_events
    if _cached_events is not None:
        try:
            local_store.save_events(_cached_events)
        except Exception as e:
            flash(f"Error saving: {e}", "error")


def _photos_for_event(event_uuid):
    """Return list of photo filenames matching this event's UUID."""
    if not event_uuid:
        return []
    pattern = os.path.join(local_store.PHOTOS_DIR, f"{event_uuid}_*")
    return sorted(os.path.basename(p) for p in glob.glob(pattern))


def _photo_counts():
    """Return dict of uuid → photo count for all events."""
    counts = {}
    try:
        for fname in os.listdir(local_store.PHOTOS_DIR):
            parts = fname.split("_", 1)
            if len(parts) == 2:
                uid = parts[0]
                counts[uid] = counts.get(uid, 0) + 1
    except FileNotFoundError:
        pass
    return counts


def _collect_suggestions():
    if _cached_events is None:
        _load_events()
    techniques = set()
    collectors = set()
    countries = set()
    states = set()
    counties = set()
    localities = set()
    hosts = set()
    dates = set()
    for event in _cached_events or []:
        technique = event.get("collectionTechnique")
        if technique:
            techniques.add(technique)
        for collector in event.get("collectors", []) or []:
            if collector:
                collectors.add(collector)
        country = event.get("country")
        if country:
            countries.add(country)
        state = event.get("stateProvince")
        if state:
            states.add(state)
        county = event.get("county")
        if county:
            counties.add(county)
        locality = event.get("locality")
        if locality:
            localities.add(locality)
        host = event.get("host")
        if host:
            hosts.add(host)
        for dkey in ("createdAt", "startDateTime", "endDateTime"):
            dval = event.get(dkey)
            if dval and len(dval) >= 10:
                dates.add(dval[:10])
    # Build geo profiles: unique combos of country/state/county/locality
    geo_seen = set()
    geo_profiles = []
    for event in _cached_events or []:
        country = event.get("country") or ""
        state = event.get("stateProvince") or ""
        county = event.get("county") or ""
        locality = event.get("locality") or ""
        if not any([country, state, county, locality]):
            continue
        key = (country, state, county, locality)
        if key not in geo_seen:
            geo_seen.add(key)
            geo_profiles.append({
                "country": country,
                "state": state,
                "county": county,
                "locality": locality,
            })

    # Build collector groups: full comma-separated collector strings
    collector_groups = set()
    for event in _cached_events or []:
        coll_list = event.get("collectors") or []
        if len(coll_list) > 1:
            collector_groups.add(", ".join(coll_list))

    return {
        "techniques": sorted(techniques),
        "collectors": sorted(collectors),
        "collector_groups": sorted(collector_groups),
        "countries": sorted(countries),
        "states": sorted(states),
        "counties": sorted(counties),
        "localities": sorted(localities),
        "hosts": sorted(hosts),
        "dates": sorted(dates, reverse=True),
        "geo_profiles": geo_profiles,
    }


@app.route("/photos/<filename>")
def serve_photo(filename):
    if ".." in filename or "/" in filename:
        return "Invalid filename", 400
    photo_path = os.path.join(local_store.PHOTOS_DIR, filename)
    if not os.path.isfile(photo_path):
        return "Not found", 404
    return send_file(photo_path)


# Query string of the last list view (search, sort, selection), so going back
# to the list from the edit form restores it. Single-user desktop app, so a
# module global is enough.
_last_list_query = ""


def _list_url():
    base = url_for("index")
    return f"{base}?{_last_list_query}" if _last_list_query else base


@app.context_processor
def _inject_list_url():
    return {"list_url": _list_url, "list_event_id": _list_event_id}


def _list_event_id(event):
    """What the list's Event ID column shows. Trap samples: trap code + end
    date (SAM2-260826), or SAM2-… while the sample is still out."""
    if _is_trap_sample(event) and event.get("trapCode"):
        return _trap_event_id(event["trapCode"], event.get("endDateTime")) or f'{event["trapCode"]}-…'
    return event.get("collectionCode") or ""


@app.route("/")
def index():
    global _cached_events, _last_list_query
    _last_list_query = request.query_string.decode("utf-8", "replace")
    if _cached_events is None:
        _load_events()
    sort1 = request.args.get("sort1", "").strip()
    sort2 = request.args.get("sort2", "").strip()
    sort3 = request.args.get("sort3", "").strip()
    sort4 = request.args.get("sort4", "").strip()
    if not sort1 and not sort2 and not sort3 and not sort4:
        # Default: keep active events near the top.
        sort1 = "status"
    query = request.args.get("q", "").strip()
    selected = [s for s in request.args.getlist("selected") if s]
    selected_set = set(selected)
    events = [{"idx": i, "event": e} for i, e in enumerate(_cached_events or [])]

    def event_is_archived(event):
        if "archived" in event:
            return bool(event.get("archived"))
        # Backward compatibility with older saved state.
        return bool(event.get("labelsPrinted"))

    def field_value(event, field):
        if not field:
            return ""
        if field == "date":
            if event.get("startDateTime") and event.get("endDateTime"):
                return str(event.get("startDateTime") or "")
            return str(event.get("createdAt") or "")
        if field == "type":
            return "Trap Sample" if _is_trap_sample(event) else "General"
        if field == "state":
            return str(event.get("stateProvince") or "")
        if field == "county":
            return str(event.get("county") or "")
        if field == "locality":
            return str(event.get("locality") or "")
        if field == "country":
            return str(event.get("country") or "")
        if field == "technique":
            return str(event.get("collectionTechnique") or "")
        if field == "collectors":
            return ", ".join(event.get("collectors") or [])
        if field == "code":
            if _is_trap_sample(event) and event.get("trapCode"):
                # Group a trap's samples together, in end-date order.
                return f'{event["trapCode"]} {event.get("endDateTime") or "9999"}'
            return str(event.get("collectionCode") or "")
        if field in ("status", "printed"):
            return "1" if event_is_archived(event) else "0"
        return str(event.get(field) or "")

    def sort_key(field):
        def key(item):
            v = field_value(item["event"], field).strip().lower()
            return v
        return key

    for field in (sort4, sort3, sort2, sort1):
        if field:
            events.sort(key=sort_key(field))

    def searchable_text(event):
        parts = [
            event.get("collectionCode"),
            event.get("trapCode"),
            event.get("country"),
            event.get("stateProvince"),
            event.get("county"),
            event.get("locality"),
            event.get("host"),
            event.get("collectionTechnique"),
            event.get("notes"),
            event.get("createdAt"),
            event.get("startDateTime"),
            event.get("endDateTime"),
            str(event.get("latitude") or ""),
            str(event.get("longitude") or ""),
        ]
        collectors = ", ".join(event.get("collectors") or [])
        if collectors:
            parts.append(collectors)
        return " ".join([p for p in parts if p]).lower()

    search_results = []
    if query:
        q = query.lower()
        for item in events:
            if q in searchable_text(item["event"]):
                search_results.append(item)

    selected_items = [item for item in events if item["event"].get("uuid") in selected_set]
    search_results = [item for item in search_results if item["event"].get("uuid") not in selected_set]
    if query:
        search_ids = {item["event"].get("uuid") for item in search_results}
        all_items = [
            item for item in events
            if item["event"].get("uuid") not in selected_set and item["event"].get("uuid") not in search_ids
        ]
    else:
        all_items = [item for item in events if item["event"].get("uuid") not in selected_set]

    active_all_items = [item for item in all_items if not event_is_archived(item["event"])]
    archived_all_items = [item for item in all_items if event_is_archived(item["event"])]

    settings = load_settings()
    return render_template(
        "index.html",
        selected_items=selected_items,
        search_results=search_results,
        active_all_items=active_all_items,
        archived_all_items=archived_all_items,
        sort1=sort1,
        sort2=sort2,
        sort3=sort3,
        sort4=sort4,
        q=query,
        selected=selected,
        photo_counts=_photo_counts(),
        date_format=settings.get("dateFormat", "roman"),
    )




@app.route("/event/new")
def new_event():
    suggestions = _collect_suggestions()
    return render_template(
        "event_form.html",
        event=None,
        idx=None,
        photos=[],
        is_trap=False,
        copied=False,
        general_ids=_general_ids(),
        technique_options=suggestions["techniques"],
        collector_options=suggestions["collectors"],
        collector_group_options=suggestions["collector_groups"],
        country_options=suggestions["countries"],
        state_options=suggestions["states"],
        county_options=suggestions["counties"],
        locality_options=suggestions["localities"],
        host_options=suggestions["hosts"],
        date_options=suggestions["dates"],
        geo_profiles=suggestions["geo_profiles"],
    )


@app.route("/event/<int:idx>/edit")
def edit_event(idx):
    global _cached_events
    if _cached_events is None:
        _load_events()
    if idx < 0 or idx >= len(_cached_events):
        flash("Event not found", "error")
        return redirect(_list_url())
    suggestions = _collect_suggestions()
    event = _cached_events[idx]
    photos = _photos_for_event(event.get("uuid"))
    return render_template(
        "event_form.html",
        event=event,
        idx=idx,
        photos=photos,
        is_trap=_is_trap_sample(event),
        copied=request.args.get("copied") == "1",
        general_ids=_general_ids(exclude_uuid=event.get("uuid")),
        technique_options=suggestions["techniques"],
        collector_options=suggestions["collectors"],
        collector_group_options=suggestions["collector_groups"],
        country_options=suggestions["countries"],
        state_options=suggestions["states"],
        county_options=suggestions["counties"],
        locality_options=suggestions["localities"],
        host_options=suggestions["hosts"],
        date_options=suggestions["dates"],
        geo_profiles=suggestions["geo_profiles"],
    )


@app.route("/inat/observation")
def fetch_inat_observation():
    observation_id = request.args.get("id", "").strip()
    if not observation_id:
        return jsonify({"error": "Missing observation ID"}), 400
    if not observation_id.isdigit():
        return jsonify({"error": "Observation ID must be numeric"}), 400
    try:
        observation = _fetch_inat_observation(observation_id)
        payload = _inat_prefill_fields(observation, observation_id)
        return jsonify({"ok": True, "fields": payload})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except LookupError as e:
        return jsonify({"error": str(e)}), 404
    except url_error.HTTPError as e:
        if e.code == 404:
            return jsonify({"error": "Observation not found"}), 404
        return jsonify({"error": f"iNaturalist request failed ({e.code})"}), 502
    except url_error.URLError:
        return jsonify({"error": "Unable to reach iNaturalist"}), 502
    except Exception:
        return jsonify({"error": "Unexpected error while fetching observation"}), 500


@app.route("/event/save", methods=["POST"])
def save_event():
    global _cached_events
    if _cached_events is None:
        _load_events()

    idx = request.form.get("idx")
    # "Duplicate" on the edit page submits the form as it stands; the copy
    # gets a fresh uuid and the original stays as last saved.
    save_as_copy = request.form.get("saveAsCopy") == "1"
    source_idx = idx
    if save_as_copy:
        idx = None
    is_edit = idx is not None and idx != ""

    # Build event dict from form
    qty_str = request.form.get("labelQuantity", "").strip()
    lat_str = request.form.get("latitude", "").strip()
    lon_str = request.form.get("longitude", "").strip()

    lat_dms_deg = request.form.get("lat_dms_deg", "")
    lat_dms_min = request.form.get("lat_dms_min", "")
    lat_dms_sec = request.form.get("lat_dms_sec", "")
    lat_dms_dir = request.form.get("lat_dms_dir", "")
    lon_dms_deg = request.form.get("lon_dms_deg", "")
    lon_dms_min = request.form.get("lon_dms_min", "")
    lon_dms_sec = request.form.get("lon_dms_sec", "")
    lon_dms_dir = request.form.get("lon_dms_dir", "")
    lat_dm_deg = request.form.get("lat_dm_deg", "")
    lat_dm_min = request.form.get("lat_dm_min", "")
    lat_dm_dir = request.form.get("lat_dm_dir", "")
    lon_dm_deg = request.form.get("lon_dm_deg", "")
    lon_dm_min = request.form.get("lon_dm_min", "")
    lon_dm_dir = request.form.get("lon_dm_dir", "")

    lat_dd = None
    lon_dd = None

    lat_has_dms = _has_any_coord_value(lat_dms_deg, lat_dms_min, lat_dms_sec, lat_dms_dir)
    lon_has_dms = _has_any_coord_value(lon_dms_deg, lon_dms_min, lon_dms_sec, lon_dms_dir)
    lat_has_dm = _has_any_coord_value(lat_dm_deg, lat_dm_min, lat_dm_dir)
    lon_has_dm = _has_any_coord_value(lon_dm_deg, lon_dm_min, lon_dm_dir)

    lat_alt_used = lat_has_dms or lat_has_dm
    lon_alt_used = lon_has_dms or lon_has_dm

    if lat_has_dms:
        lat_dd = _parse_dms_coordinate(
            lat_dms_deg,
            lat_dms_min,
            lat_dms_sec,
            lat_dms_dir,
            True,
        )
    elif lat_has_dm:
        lat_dd = _parse_dm_coordinate(
            lat_dm_deg,
            lat_dm_min,
            lat_dm_dir,
            True,
        )
    elif lat_str:
        lat_dd = _parse_decimal_coordinate(lat_str, True)

    if lon_has_dms:
        lon_dd = _parse_dms_coordinate(
            lon_dms_deg,
            lon_dms_min,
            lon_dms_sec,
            lon_dms_dir,
            False,
        )
    elif lon_has_dm:
        lon_dd = _parse_dm_coordinate(
            lon_dm_deg,
            lon_dm_min,
            lon_dm_dir,
            False,
        )
    elif lon_str:
        lon_dd = _parse_decimal_coordinate(lon_str, False)

    if lat_alt_used and lat_dd is None:
        flash("Invalid latitude in DMS/DDM fields", "error")
        return redirect(request.referrer or url_for("index"))
    if lon_alt_used and lon_dd is None:
        flash("Invalid longitude in DMS/DDM fields", "error")
        return redirect(request.referrer or url_for("index"))

    if lat_dd is not None:
        # Keep the precision the user typed for a plain decimal; DMS/DDM
        # conversions use the default (5 places).
        lat_decimals = None if lat_alt_used else _coord_decimal_places(lat_str)
        lat_str = _normalize_decimal_coord(lat_dd, lat_decimals)
    if lon_dd is not None:
        lon_decimals = None if lon_alt_used else _coord_decimal_places(lon_str)
        lon_str = _normalize_decimal_coord(lon_dd, lon_decimals)
    elev_str = request.form.get("elevation", "").strip()
    accuracy_str = request.form.get("gpsAccuracy", "").strip()
    collectors_raw = request.form.get("collectors", "").strip()
    collectors = [c.strip() for c in collectors_raw.split(",") if c.strip()] if collectors_raw else []

    # Validate and normalize date fields
    created_raw = request.form.get("createdAt", "").strip()
    start_raw = request.form.get("startDateTime", "").strip()
    end_raw = request.form.get("endDateTime", "").strip()
    if created_raw:
        created_at = _parse_datetime(created_raw)
    elif start_raw and end_raw:
        # A date range is present — leave the single Event Date empty rather
        # than copying the range start into it. The label and list views both
        # use the range directly when start and end are set.
        created_at = None
    else:
        created_at = _parse_datetime(start_raw) or _parse_datetime(end_raw) or date.today().isoformat()
    start_dt = _parse_datetime(start_raw)
    end_dt = _parse_datetime(end_raw)

    errors = []
    if created_raw and created_at is None:
        errors.append("Invalid event date/time format")
    if start_raw and start_dt is None:
        errors.append("Invalid start date/time format")
    if end_raw and end_dt is None:
        errors.append("Invalid end date/time format")
    if errors:
        for msg in errors:
            flash(msg, "error")
        return redirect(request.referrer or url_for("index"))

    submitted_uuid = "" if save_as_copy else request.form.get("uuid", "").strip()
    is_trap = request.form.get("isTrapSample") == "1"
    trap_code = request.form.get("trapCode", "").strip() if is_trap else ""
    collection_code = request.form.get("collectionCode", "").strip()
    if is_trap and trap_code:
        # Trap sample IDs are always derived (the form hides the ID box).
        collection_code = _trap_event_id(trap_code, end_dt)

    event = {
        "uuid": submitted_uuid or str(uuid.uuid4()),
        "collectionCode": collection_code,
        "isTrapSample": is_trap,
        "trapCode": trap_code,
        "latitude": lat_str if lat_str else None,
        "longitude": lon_str if lon_str else None,
        "elevation": _safe_int(elev_str),
        "gpsAccuracy": _safe_float(accuracy_str),
        "createdAt": created_at,
        "country": request.form.get("country", ""),
        "stateProvince": abbreviate_state(request.form.get("stateProvince", "")),
        "county": request.form.get("county", ""),
        "locality": request.form.get("locality", ""),
        "host": request.form.get("host", ""),
        "collectionTechnique": request.form.get("collectionTechnique") or None,
        "notes": request.form.get("notes", ""),
        "startDateTime": start_dt,
        "endDateTime": end_dt,
        "collectors": collectors,
        "labelQuantity": _safe_int(qty_str) or 10,
        "modifiedAt": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
        "photos": [],
    }

    if is_edit:
        idx_int = int(idx)
        # Preserve photos and coordPrecision from original
        if 0 <= idx_int < len(_cached_events):
            event["photos"] = _cached_events[idx_int].get("photos", [])
            event["coordPrecision"] = _cached_events[idx_int].get("coordPrecision")
            event["archived"] = bool(_cached_events[idx_int].get("archived") or _cached_events[idx_int].get("labelsPrinted"))
            event["labelsPrinted"] = bool(event["archived"])
            _cached_events[idx_int] = event
        flash("Collecting event updated", "success")
    else:
        event["archived"] = False
        event["labelsPrinted"] = False
        if save_as_copy:
            if is_trap:
                # Next sample from the same trap: it starts when the last one ended.
                event["startDateTime"] = event["endDateTime"] or event["startDateTime"]
                event["endDateTime"] = None
                event["createdAt"] = event["startDateTime"]
            rolled = _roll_event_id(event)
            if rolled is not None:
                event["collectionCode"] = rolled
        _cached_events.append(event)
        if save_as_copy:
            event["coordPrecision"] = _source_coord_precision(source_idx)
            _save_events()
            flash("Duplicated — you're now editing the copy", "success")
            return redirect(url_for("edit_event", idx=len(_cached_events) - 1, copied=1))
        flash("Collecting event added", "success")

    _save_events()
    # Stay on the form after saving so the event can be duplicated or tweaked.
    target_idx = int(idx) if is_edit else len(_cached_events) - 1
    return redirect(url_for("edit_event", idx=target_idx))


def _general_ids(exclude_uuid=None):
    """All YYMMDD-NNN IDs in use, for the form's client-side numbering."""
    return [
        (e.get("collectionCode") or "").strip()
        for e in _cached_events or []
        if e.get("uuid") != exclude_uuid
        and _GENERAL_ID_RE.match((e.get("collectionCode") or "").strip())
    ]


def _source_coord_precision(source_idx):
    try:
        i = int(source_idx)
    except (TypeError, ValueError):
        return None
    if 0 <= i < len(_cached_events):
        return _cached_events[i].get("coordPrecision")
    return None


@app.route("/event/<int:idx>/delete", methods=["POST"])
def delete_event(idx):
    global _cached_events
    if _cached_events is None:
        _load_events()
    if 0 <= idx < len(_cached_events):
        _cached_events.pop(idx)
        _save_events()
        flash("Event deleted", "success")
    return redirect(_list_url())


@app.route("/event/<int:idx>/duplicate", methods=["POST"])
def duplicate_event(idx):
    global _cached_events
    if _cached_events is None:
        _load_events()
    if 0 <= idx < len(_cached_events):
        import copy
        new_event = copy.deepcopy(_cached_events[idx])
        new_event["uuid"] = str(uuid.uuid4())
        new_event["photos"] = []
        new_event["archived"] = False
        new_event["labelsPrinted"] = False
        new_event["modifiedAt"] = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        # Apply optional field overrides from the duplicate modal (parsed to date-only ISO)
        created_raw = request.form.get("createdAt", "").strip()
        start_raw = request.form.get("startDateTime", "").strip()
        end_raw = request.form.get("endDateTime", "").strip()
        if created_raw or start_raw or end_raw:
            created_at = _parse_datetime(created_raw) if created_raw else None
            start_dt = _parse_datetime(start_raw)
            end_dt = _parse_datetime(end_raw)
            # Don't copy the range start into the single Event Date when a full
            # range (start + end) was provided.
            if not created_at and not (start_raw and end_raw):
                created_at = start_dt or end_dt
            if created_at:
                new_event["createdAt"] = created_at
            # The modal shows all three dates, so a blank box means "clear it"
            # (e.g. the end date of the next trap sample isn't known yet).
            new_event["startDateTime"] = start_dt
            new_event["endDateTime"] = end_dt
        if _is_trap_sample(new_event) and not new_event.get("endDateTime"):
            new_event["createdAt"] = new_event.get("startDateTime")
        rolled = _roll_event_id(new_event)
        if rolled is not None:
            new_event["collectionCode"] = rolled
        _cached_events.append(new_event)
        _save_events()
        flash("Duplicated — you're now editing the copy", "success")
        return redirect(url_for("edit_event", idx=len(_cached_events) - 1, copied=1))
    return redirect(_list_url())


@app.route("/event/qty", methods=["POST"])
def update_quantity():
    global _cached_events
    if _cached_events is None:
        _load_events()
    event_uuid = request.form.get("uuid", "").strip()
    qty_str = request.form.get("labelQuantity", "").strip()
    if not event_uuid or not qty_str:
        return "", 400
    try:
        qty = max(1, min(1000, int(qty_str)))
    except (ValueError, TypeError):
        return "", 400
    for event in (_cached_events or []):
        if event.get("uuid") == event_uuid:
            event["labelQuantity"] = qty
            _save_events()
            return "", 204
    return "", 404


@app.route("/event/archive", methods=["POST"])
def update_archived():
    global _cached_events
    if _cached_events is None:
        _load_events()
    event_uuid = request.form.get("uuid", "").strip()
    archived_raw = request.form.get("archived", "").strip().lower()
    if not event_uuid:
        return "", 400
    archived = archived_raw in ("1", "true", "yes", "on")
    for event in (_cached_events or []):
        if event.get("uuid") == event_uuid:
            event["archived"] = archived
            # Keep legacy key in sync for backward compatibility.
            event["labelsPrinted"] = archived
            _save_events()
            return "", 204
    return "", 404


@app.route("/generate", methods=["POST"])
def generate():
    global _cached_events
    if _cached_events is None:
        _load_events()

    settings = load_settings()

    selected = request.form.getlist("selected")
    quantities = request.form.to_dict(flat=False)

    label_sets = []
    event_by_uuid = {e.get("uuid"): e for e in (_cached_events or [])}
    for uuid_str in selected:
        event = event_by_uuid.get(uuid_str)
        if event is None:
            continue
        qty_key = f"qty_{uuid_str}"
        qty = int(quantities.get(qty_key, [10])[0])
        label_sets.extend(format_event_labels(event, qty, settings))
    if not label_sets:
        flash("No events selected", "error")
        return redirect(_list_url())
    output_path = os.path.join(tempfile.gettempdir(), "labels.pdf")
    generate_pdf(label_sets, output_path, settings)

    return send_file(output_path, as_attachment=True, download_name="labels.pdf")


@app.route("/api/estimate", methods=["POST"])
def api_estimate():
    global _cached_events
    if _cached_events is None:
        _load_events()
    
    import json
    data = request.get_json(silent=True) or {}
    selected = data.get("selected", [])
    
    settings = load_settings()
    events = []
    for uuid_str in selected:
        for event in (_cached_events or []):
            if event.get("uuid") == uuid_str:
                qty_key = f"qty_{uuid_str}"
                qty_str = data.get(qty_key, "10")
                try:
                    qty = int(qty_str)
                except (ValueError, TypeError):
                    qty = 10
                event["labelQuantity"] = qty
                events.append(event)
                break
    
    if not events:
        return jsonify({"pages": [], "total_pages": 0, "total_labels": 0})
    
    result = calculate_label_layout(events, settings)
    pages_data = []
    for page in result["pages"]:
        pages_data.append({
            "page_num": page["page_num"],
            "used_pct": page["used_pct"],
        })
    
    return jsonify({
        "pages": pages_data,
        "total_pages": result["total_pages"],
        "total_labels": result["total_labels"],
    })


@app.route("/settings")
def get_settings():
    return jsonify(load_settings())


@app.route("/settings", methods=["POST"])
def update_settings():
    data = request.get_json(silent=True) or {}
    current = load_settings()
    if "font" in data and data["font"] in FONT_CHOICES:
        current["font"] = data["font"]
    if "fontSize" in data:
        try:
            fs = float(data["fontSize"])
            if fs in FONT_SIZE_CHOICES:
                current["fontSize"] = fs
        except (ValueError, TypeError):
            pass
    if "minLines" in data:
        try:
            ml = int(data["minLines"])
            if ml in MIN_LINES_CHOICES:
                current["minLines"] = ml
        except (ValueError, TypeError):
            pass
    if "maxLines" in data:
        try:
            ml = int(data["maxLines"])
            if ml in MAX_LINES_CHOICES:
                current["maxLines"] = ml
        except (ValueError, TypeError):
            pass
    if "labelWidth" in data:
        try:
            lw = float(data["labelWidth"])
            if lw in LABEL_WIDTH_CHOICES:
                current["labelWidth"] = lw
        except (ValueError, TypeError):
            pass
    if "allowDateDotBreak" in data:
        current["allowDateDotBreak"] = bool(data["allowDateDotBreak"])
    if "allowCoordDotBreak" in data:
        current["allowCoordDotBreak"] = bool(data["allowCoordDotBreak"])
    if "splitHostLabel" in data:
        current["splitHostLabel"] = bool(data["splitHostLabel"])
    if "dateFormat" in data and data["dateFormat"] in DATE_FORMAT_CHOICES:
        current["dateFormat"] = data["dateFormat"]
    save_settings(current)
    return jsonify({"ok": True})


@app.route("/sync/phone", methods=["POST"])
def sync_phone():
    global _cached_events
    if _cached_events is None:
        _load_events()

    phone_ip = request.form.get("phone_ip", "").strip()
    phone_token = request.form.get("phone_token", "").strip()
    if not phone_ip:
        flash("Please enter the phone IP address", "error")
        return redirect(_list_url())
    if not phone_token:
        flash("Please enter the phone's pairing code", "error")
        return redirect(_list_url())

    # Accept full URL (e.g. http://10.0.0.154:8080) or bare IP
    phone_ip = re.sub(r"^https?://", "", phone_ip).rstrip("/")
    phone_url = f"http://{phone_ip}"
    sync_headers = {"X-Sync-Token": phone_token}

    try:
        # 1. Fetch events from phone
        req = url_request.Request(
            f"{phone_url}/api/events",
            headers={**sync_headers, "Accept": "application/json"},
        )
        with url_request.urlopen(req, timeout=10) as resp:
            phone_events = json.loads(resp.read().decode("utf-8"))
    except url_error.HTTPError as e:
        if e.code == 401:
            flash("Failed to connect to phone: invalid pairing code", "error")
        else:
            flash(f"Failed to connect to phone: {e}", "error")
        return redirect(_list_url())
    except Exception as e:
        flash(f"Failed to connect to phone: {e}", "error")
        return redirect(_list_url())

    # 2. Merge phone events into local events (newer-wins)
    local_by_uuid = {}
    for i, ev in enumerate(_cached_events or []):
        uid = ev.get("uuid")
        if uid:
            local_by_uuid[uid] = i

    imported = 0
    updated = 0
    # Shared fields that both sides understand
    SHARED_FIELDS = {
        "collectionCode", "uuid", "latitude", "longitude", "elevation",
        "gpsAccuracy", "createdAt", "country", "stateProvince", "county",
        "locality", "host", "collectionTechnique", "notes", "startDateTime",
        "endDateTime", "collectors", "coordPrecision", "modifiedAt", "photos",
    }

    for phone_ev in phone_events:
        uid = phone_ev.get("uuid")
        if not uid:
            continue

        if "stateProvince" in phone_ev:
            phone_ev["stateProvince"] = abbreviate_state(phone_ev["stateProvince"])

        if uid in local_by_uuid:
            idx = local_by_uuid[uid]
            local_ev = _cached_events[idx]
            remote_mod = phone_ev.get("modifiedAt") or ""
            local_mod = local_ev.get("modifiedAt") or ""
            if remote_mod and remote_mod > local_mod:
                # Phone is newer: update shared fields, preserve desktop-only fields
                for key in SHARED_FIELDS:
                    if key in phone_ev:
                        local_ev[key] = phone_ev[key]
                local_ev["modifiedAt"] = remote_mod
                _cached_events[idx] = local_ev
                updated += 1
        else:
            # New event from phone: add with desktop defaults
            new_ev = {}
            for key in SHARED_FIELDS:
                if key in phone_ev:
                    new_ev[key] = phone_ev[key]
            new_ev["labelQuantity"] = 10
            new_ev["archived"] = False
            new_ev["labelsPrinted"] = False
            _cached_events.append(new_ev)
            local_by_uuid[uid] = len(_cached_events) - 1
            imported += 1

    # 3. Send merged events to phone
    try:
        export_events = json.dumps(_cached_events).encode("utf-8")
        req = url_request.Request(
            f"{phone_url}/api/events",
            data=export_events,
            headers={
                **sync_headers,
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with url_request.urlopen(req, timeout=30) as resp:
            resp.read()
    except Exception as e:
        flash(f"Sent events to phone failed: {e}", "error")

    # 4. Download photos from phone
    photo_count = 0
    try:
        req = url_request.Request(
            f"{phone_url}/api/photos",
            headers={**sync_headers, "Accept": "application/json"},
        )
        with url_request.urlopen(req, timeout=10) as resp:
            photo_list = json.loads(resp.read().decode("utf-8"))

        photos_dir = local_store.PHOTOS_DIR
        os.makedirs(photos_dir, exist_ok=True)

        for filename in photo_list:
            if ".." in filename or "/" in filename:
                continue
            local_path = os.path.join(photos_dir, filename)
            if os.path.exists(local_path):
                continue
            try:
                photo_req = url_request.Request(f"{phone_url}/api/photos/{filename}", headers=sync_headers)
                with url_request.urlopen(photo_req, timeout=30) as photo_resp:
                    with open(local_path, "wb") as f:
                        f.write(photo_resp.read())
                photo_count += 1
            except Exception:
                pass
    except Exception:
        pass

    # 5. Save merged events locally
    _save_events()

    parts = []
    if imported:
        parts.append(f"{imported} new events from phone")
    if updated:
        parts.append(f"{updated} events updated from phone")
    if photo_count:
        parts.append(f"{photo_count} photos downloaded")
    if not parts:
        parts.append("Everything up to date")
    flash("Sync complete: " + ", ".join(parts), "success")
    return redirect(_list_url())


# Auto-shutdown watchdog.
#
# The old approach exited 5s after a "tab closed" beacon, which misfired on
# tab switches, back/forward navigation and bfcache restores and killed the
# server mid-use. Instead we track activity: every request (including a periodic
# heartbeat from the open page) refreshes _last_activity, and a background
# watchdog exits only after IDLE_TIMEOUT with no activity at all. A briefly
# hidden or locked tab can't kill the server; a truly closed tab stops sending
# heartbeats and the process exits after the grace period.
IDLE_TIMEOUT = float(os.environ.get("FIELDCOLLECT_IDLE_TIMEOUT", "90"))  # seconds with zero requests before exit
_last_activity = time.monotonic()
_activity_lock = threading.Lock()


@app.before_request
def _mark_active():
    """Any incoming request means the app is still in use."""
    global _last_activity
    with _activity_lock:
        _last_activity = time.monotonic()


@app.route("/heartbeat", methods=["POST"])
def heartbeat():
    """Pinged periodically by the open page so an idle-but-open tab stays alive.
    Activity itself is recorded in the before_request hook."""
    return "", 204


def _start_idle_watchdog():
    """Exit the process once the browser has been gone for IDLE_TIMEOUT."""
    def _watch():
        while True:
            time.sleep(IDLE_TIMEOUT / 3.0)
            with _activity_lock:
                idle = time.monotonic() - _last_activity
            if idle > IDLE_TIMEOUT:
                os._exit(0)
    threading.Thread(target=_watch, daemon=True).start()


if __name__ == "__main__":
    debug = os.environ.get("FIELDCOLLECT_DEBUG", "0") == "1"
    port = int(os.environ.get("FIELDCOLLECT_PORT", "5000"))
    _start_idle_watchdog()
    app.run(
        host="127.0.0.1",
        port=port,
        debug=debug,
        use_reloader=debug,
    )
