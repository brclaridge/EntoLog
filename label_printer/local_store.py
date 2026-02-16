import json
import os

_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(_DIR, "data")
EVENTS_FILE = os.path.join(DATA_DIR, "collectingEvents.json")
PHOTOS_DIR = os.path.join(DATA_DIR, "photos")


def _ensure_dirs():
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(PHOTOS_DIR, exist_ok=True)


def load_events():
    _ensure_dirs()
    if not os.path.exists(EVENTS_FILE):
        return []
    with open(EVENTS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_events(events):
    _ensure_dirs()
    with open(EVENTS_FILE, "w", encoding="utf-8") as f:
        json.dump(events, f, indent=2, ensure_ascii=False)
