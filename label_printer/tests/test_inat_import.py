import os
import sys
import types
import importlib.util


sys.modules["local_store"] = types.SimpleNamespace(
    load_events=lambda: [],
    save_events=lambda x: None,
    PHOTOS_DIR="/tmp/fieldcollect_test_photos",
)
sys.modules["label_formatter"] = types.SimpleNamespace(
    format_event=lambda e: [],
    format_event_labels=lambda e, q, s: [],
    _format_date=lambda s: s or "",
    _format_date_range=lambda a, b: f"{a or ''} - {b or ''}".strip(" -"),
)
sys.modules["pdf_generator"] = types.SimpleNamespace(generate_pdf=lambda *a, **k: None)
sys.modules["print_settings"] = types.SimpleNamespace(
    load_settings=lambda: {},
    save_settings=lambda x: None,
    FONT_CHOICES=[],
    FONT_SIZE_CHOICES=[],
    MIN_LINES_CHOICES=[],
    MAX_LINES_CHOICES=[],
)

app_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app.py"))
spec = importlib.util.spec_from_file_location("label_printer.app", app_path)
mod = importlib.util.module_from_spec(spec)
sys.modules["label_printer.app"] = mod
spec.loader.exec_module(mod)
app = mod.app


def test_inat_observation_import():
    def fake_fetch(obs_id):
        assert obs_id == "12345"
        return {
            "observed_on": "2026-02-10",
            "geojson": {"coordinates": [-77.705, 38.825]},
            "public_positional_accuracy": 12,
            "place_guess": "Near Woods, Fairfax County, Virginia, United States",
            "description": "Found on oak leaves.",
            "user": {"name": "B Claridge", "login": "bclaridge"},
        }

    mod._fetch_inat_observation = fake_fetch
    client = app.test_client()
    resp = client.get("/inat/observation?id=12345")

    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["ok"] is True
    fields = payload["fields"]
    assert fields["createdAt"] == "2026-02-10"
    assert fields["latitude"] == "38.825"
    assert fields["longitude"] == "-77.705"
    assert fields["gpsAccuracy"] == "12"
    assert fields["locality"].startswith("Near Woods")
    assert fields["collectors"] == "B Claridge"
    assert "iNaturalist observation: https://www.inaturalist.org/observations/12345" in fields["notes"]
    assert fields["collectionTechnique"] == "iNaturalist observation"


def test_inat_observation_requires_numeric_id():
    client = app.test_client()
    resp = client.get("/inat/observation?id=abc")
    assert resp.status_code == 400
    payload = resp.get_json()
    assert "numeric" in payload["error"].lower()
