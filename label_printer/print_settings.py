import json
import os

SETTINGS_PATH = os.path.join(os.path.dirname(__file__), "print_settings.json")

FONT_CHOICES = {
    "LiberationSansNarrow": "/usr/share/fonts/truetype/liberation/LiberationSansNarrow-Regular.ttf",
    "LiberationSans": "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "LiberationSerif": "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf",
    "LiberationMono": "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
}

FONT_ITALIC_CHOICES = {
    "LiberationSansNarrow": "/usr/share/fonts/truetype/liberation/LiberationSansNarrow-Italic.ttf",
    "LiberationSans": "/usr/share/fonts/truetype/liberation/LiberationSans-Italic.ttf",
    "LiberationSerif": "/usr/share/fonts/truetype/liberation/LiberationSerif-Italic.ttf",
    "LiberationMono": "/usr/share/fonts/truetype/liberation/LiberationMono-Italic.ttf",
}

FONT_SIZE_CHOICES = [3, 3.5, 4, 4.5, 5]

MIN_LINES_CHOICES = [3, 4, 5]

MAX_LINES_CHOICES = [4, 5, 6, 7]

LABEL_WIDTH_CHOICES = [1.5, 1.6, 1.76, 1.9, 2.0, 2.2, 2.5]  # cm

DATE_FORMAT_CHOICES = ["roman", "iso", "dmy"]

DEFAULTS = {
    "font": "LiberationSansNarrow",
    "fontSize": 4,
    "minLines": 4,
    "maxLines": 5,
    "labelWidth": 1.76,
    "allowDateDotBreak": True,
    "allowCoordDotBreak": True,
    "splitHostLabel": False,
    "dateFormat": "roman",
}


def load_settings():
    settings = dict(DEFAULTS)
    if os.path.exists(SETTINGS_PATH):
        try:
            with open(SETTINGS_PATH, "r") as f:
                saved = json.load(f)
            settings.update(saved)
        except (json.JSONDecodeError, OSError):
            pass
    if settings["font"] not in FONT_CHOICES:
        settings["font"] = DEFAULTS["font"]
    if settings["fontSize"] not in FONT_SIZE_CHOICES:
        settings["fontSize"] = DEFAULTS["fontSize"]
    if settings["minLines"] not in MIN_LINES_CHOICES:
        settings["minLines"] = DEFAULTS["minLines"]
    if settings.get("maxLines") not in MAX_LINES_CHOICES:
        settings["maxLines"] = DEFAULTS["maxLines"]
    if settings["minLines"] > settings["maxLines"]:
        settings["minLines"] = settings["maxLines"]
    if settings.get("labelWidth") not in LABEL_WIDTH_CHOICES:
        settings["labelWidth"] = DEFAULTS["labelWidth"]
    if settings.get("dateFormat") not in DATE_FORMAT_CHOICES:
        settings["dateFormat"] = DEFAULTS["dateFormat"]
    return settings


def save_settings(settings):
    with open(SETTINGS_PATH, "w") as f:
        json.dump(settings, f, indent=2)
