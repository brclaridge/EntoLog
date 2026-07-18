import sys
import types
import importlib.util
import os

# Provide minimal stubs to allow importing the app without external services
sys.modules['local_store'] = types.SimpleNamespace(
    load_events=lambda: [],
    save_events=lambda x: None,
    PHOTOS_DIR='/tmp/fieldcollect_test_photos',
)
sys.modules['label_formatter'] = types.SimpleNamespace(
    format_event=lambda e: [],
    format_event_labels=lambda e, q, s: [],
    _format_date=lambda s, *a, **k: s or "",
    _format_date_range=lambda a, b, *rest, **k: f"{a or ''} - {b or ''}".strip(" -"),
    abbreviate_state=lambda s: s,
)
sys.modules['pdf_generator'] = types.SimpleNamespace(
    generate_pdf=lambda *a, **k: None,
    calculate_label_layout=lambda *a, **k: None,
)
sys.modules['print_settings'] = types.SimpleNamespace(
    load_settings=lambda: {},
    save_settings=lambda x: None,
    FONT_CHOICES=[],
    FONT_SIZE_CHOICES=[],
    MIN_LINES_CHOICES=[],
    MAX_LINES_CHOICES=[],
    LABEL_WIDTH_CHOICES=[],
    DATE_FORMAT_CHOICES=[],
)

# Load the app module directly from file (no package __init__ required)
app_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'app.py'))
spec = importlib.util.spec_from_file_location('label_printer.app', app_path)
mod = importlib.util.module_from_spec(spec)
sys.modules['label_printer.app'] = mod
spec.loader.exec_module(mod)
app = mod.app


def run_test():
    client = app.test_client()

    # Minimal valid form with a date-only createdAt value
    form = {
        'createdAt': '2026-02-09',
        'latitude': '',
        'longitude': '',
        'coordPrecision': '5',
        'elevation': '',
        'gpsAccuracy': '',
        'collectionCode': '',
        'country': '',
        'stateProvince': '',
        'county': '',
        'locality': '',
        'host': '',
        'collectionTechnique': '',
        'notes': '',
        'startDateTime': '',
        'endDateTime': '',
        'collectors': '',
    }

    resp = client.post('/event/save', data=form, follow_redirects=True)
    print('POST /event/save status:', resp.status_code)
    body = resp.get_data(as_text=True)
    # Print any flash message fragments
    if 'Invalid' in body:
        print('Found validation error in response:')
        # Print a snippet around the error
        idx = body.find('Invalid')
        print(body[idx:idx+200])
    else:
        print('No validation error found in response.')


if __name__ == '__main__':
    run_test()
