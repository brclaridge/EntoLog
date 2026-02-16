import glob
import os
import re
import tempfile
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


def _normalize_decimal_coord(value):
    """Normalize coordinate formatting for consistent storage."""
    return f"{value:.6f}".rstrip("0").rstrip(".")


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

import local_store
from label_formatter import format_event, format_event_labels, _format_date, _format_date_range
from pdf_generator import generate_pdf
from print_settings import load_settings, save_settings, FONT_CHOICES, FONT_SIZE_CHOICES, MIN_LINES_CHOICES, MAX_LINES_CHOICES, DATE_FORMAT_CHOICES

app = Flask(__name__)
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
            return _normalize_decimal_coord(lat_val), _normalize_decimal_coord(lon_val)

    location = str(observation.get("location") or "").strip()
    if location and "," in location:
        parts = [p.strip() for p in location.split(",")]
        if len(parts) >= 2:
            lat_val = _parse_decimal_coordinate(parts[0], True)
            lon_val = _parse_decimal_coordinate(parts[1], False)
            if lat_val is not None and lon_val is not None:
                return _normalize_decimal_coord(lat_val), _normalize_decimal_coord(lon_val)

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
    return {
        "techniques": sorted(techniques),
        "collectors": sorted(collectors),
        "countries": sorted(countries),
        "states": sorted(states),
        "counties": sorted(counties),
        "localities": sorted(localities),
        "hosts": sorted(hosts),
    }


@app.route("/photos/<filename>")
def serve_photo(filename):
    if ".." in filename or "/" in filename:
        return "Invalid filename", 400
    photo_path = os.path.join(local_store.PHOTOS_DIR, filename)
    if not os.path.isfile(photo_path):
        return "Not found", 404
    return send_file(photo_path)


@app.route("/")
def index():
    global _cached_events
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
            return "Trap Sample" if event.get("startDateTime") and event.get("endDateTime") else "General"
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
        technique_options=suggestions["techniques"],
        collector_options=suggestions["collectors"],
        country_options=suggestions["countries"],
        state_options=suggestions["states"],
        county_options=suggestions["counties"],
        locality_options=suggestions["localities"],
        host_options=suggestions["hosts"],
    )


@app.route("/event/<int:idx>/edit")
def edit_event(idx):
    global _cached_events
    if _cached_events is None:
        _load_events()
    if idx < 0 or idx >= len(_cached_events):
        flash("Event not found", "error")
        return redirect(url_for("index"))
    suggestions = _collect_suggestions()
    event = _cached_events[idx]
    photos = _photos_for_event(event.get("uuid"))
    return render_template(
        "event_form.html",
        event=event,
        idx=idx,
        photos=photos,
        technique_options=suggestions["techniques"],
        collector_options=suggestions["collectors"],
        country_options=suggestions["countries"],
        state_options=suggestions["states"],
        county_options=suggestions["counties"],
        locality_options=suggestions["localities"],
        host_options=suggestions["hosts"],
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
        lat_str = _normalize_decimal_coord(lat_dd)
    if lon_dd is not None:
        lon_str = _normalize_decimal_coord(lon_dd)
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

    submitted_uuid = request.form.get("uuid", "").strip()

    event = {
        "uuid": submitted_uuid or str(uuid.uuid4()),
        "collectionCode": request.form.get("collectionCode", ""),
        "latitude": lat_str if lat_str else None,
        "longitude": lon_str if lon_str else None,
        "elevation": int(elev_str) if elev_str else None,
        "gpsAccuracy": float(accuracy_str) if accuracy_str else None,
        "createdAt": created_at,
        "country": request.form.get("country", ""),
        "stateProvince": request.form.get("stateProvince", ""),
        "county": request.form.get("county", ""),
        "locality": request.form.get("locality", ""),
        "host": request.form.get("host", ""),
        "collectionTechnique": request.form.get("collectionTechnique") or None,
        "notes": request.form.get("notes", ""),
        "startDateTime": start_dt,
        "endDateTime": end_dt,
        "collectors": collectors,
        "labelQuantity": int(qty_str) if qty_str else 10,
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
        _cached_events.append(event)
        flash("Collecting event added", "success")

    _save_events()
    return redirect(url_for("index"))


@app.route("/event/<int:idx>/delete", methods=["POST"])
def delete_event(idx):
    global _cached_events
    if _cached_events is None:
        _load_events()
    if 0 <= idx < len(_cached_events):
        _cached_events.pop(idx)
        _save_events()
        flash("Event deleted", "success")
    return redirect(url_for("index"))


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
            if not created_at:
                created_at = start_dt or end_dt
            if created_at:
                new_event["createdAt"] = created_at
            if start_raw or "startDateTime" in request.form:
                new_event["startDateTime"] = start_dt
            if end_raw or "endDateTime" in request.form:
                new_event["endDateTime"] = end_dt
        _cached_events.append(new_event)
        _save_events()
        flash("Event duplicated", "success")
    return redirect(url_for("index"))


@app.route("/event/qty", methods=["POST"])
def update_quantity():
    global _cached_events
    if _cached_events is None:
        _load_events()
    event_uuid = request.form.get("uuid", "").strip()
    qty_str = request.form.get("labelQuantity", "").strip()
    if not event_uuid or not qty_str:
        return "", 400
    qty = max(1, min(1000, int(qty_str)))
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
        return redirect(url_for("index"))
    output_path = os.path.join(tempfile.gettempdir(), "labels.pdf")
    generate_pdf(label_sets, output_path, settings)

    return send_file(output_path, as_attachment=True, download_name="labels.pdf")


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
    if "allowDateDotBreak" in data:
        current["allowDateDotBreak"] = bool(data["allowDateDotBreak"])
    if "allowCoordDotBreak" in data:
        current["allowCoordDotBreak"] = bool(data["allowCoordDotBreak"])
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
    if not phone_ip:
        flash("Please enter the phone IP address", "error")
        return redirect(url_for("index"))

    # Accept full URL (e.g. http://10.0.0.154:8080) or bare IP
    phone_ip = re.sub(r"^https?://", "", phone_ip).rstrip("/")
    phone_url = f"http://{phone_ip}"

    try:
        # 1. Fetch events from phone
        req = url_request.Request(
            f"{phone_url}/api/events",
            headers={"Accept": "application/json"},
        )
        with url_request.urlopen(req, timeout=10) as resp:
            phone_events = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        flash(f"Failed to connect to phone: {e}", "error")
        return redirect(url_for("index"))

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
            headers={"Accept": "application/json"},
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
                photo_req = url_request.Request(f"{phone_url}/api/photos/{filename}")
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
    return redirect(url_for("index"))


if __name__ == "__main__":
    debug = os.environ.get("FIELDCOLLECT_DEBUG", "0") == "1"
    port = int(os.environ.get("FIELDCOLLECT_PORT", "5000"))
    app.run(
        host="127.0.0.1",
        port=port,
        debug=debug,
        use_reloader=debug,
    )
