"""Tests for the label layout ladder in label_formatter.

The ladder hands out one concession at a time — locality on its own line, then
compact packing, then flowing locality/collectors across lines, then breaking
the date, then the coordinates — and overflows onto a continuation label only
when none of those fit. Font size and label width are never adjusted.

These tests pin the ladder's ordering and its two hard guarantees: no label
exceeds maxLines, and no collection data is dropped.

Runnable without pytest:  python3 tests/test_label_layout.py
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from label_formatter import (  # noqa: E402
    format_event_labels,
    format_event_all_labels,
)


def settings(**overrides):
    base = {
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
    base.update(overrides)
    return base


SPARSE = {
    "country": "USA", "stateProvince": "CA", "county": "Inyo Co.",
    "locality": "Big Pine Creek",
    "latitude": 37.1, "longitude": -118.3,
    "startDateTime": "2025-06-01",
    "collectors": ["Brandon Claridge"],
}

HEAVY = {
    "country": "USA", "stateProvince": "CA", "county": "Santa Barbara Co.",
    "locality": ("Los Padres National Forest, Figueroa Mountain Rd, "
                 "3.2 km NE of Ranger Peak"),
    "elevation": 1120,
    "latitude": 34.73812, "longitude": -119.98421,
    "startDateTime": "2025-06-01", "endDateTime": "2025-06-14",
    "collectors": ["Brandon Claridge", "Jane Doe"],
    "collectionTechnique": "Malaise trap",
    "host": "Quercus agrifolia",
}


def _norm(text):
    """Strip whitespace and separators so a value can be found regardless of
    where the layout chose to break it."""
    return "".join(c for c in text if not c.isspace() and c != ";")


def _all_text(labels):
    return _norm("".join("".join(lines) for lines in labels))


# --- hard guarantees -------------------------------------------------------

def test_never_exceeds_max_lines():
    """The cap is absolute — this is the bug that started all this."""
    for max_lines in (4, 5, 6, 7):
        s = settings(maxLines=max_lines, minLines=min(4, max_lines))
        for event in (SPARSE, HEAVY):
            for lines in format_event_all_labels(event, s):
                assert len(lines) <= max_lines, (
                    f"maxLines={max_lines} produced {len(lines)} lines")


def test_never_below_min_lines():
    for min_lines in (3, 4, 5):
        s = settings(minLines=min_lines, maxLines=5)
        for event in (SPARSE, HEAVY):
            for lines in format_event_all_labels(event, s):
                assert len(lines) >= min_lines


def test_no_data_is_dropped_when_overflowing():
    """Overflow must move data to another label, never discard it."""
    labels = format_event_all_labels(HEAVY, settings())
    assert len(labels) > 1, "this fixture is meant to overflow"

    combined = _all_text(labels)
    for value in ("Santa Barbara Co.", "Los Padres National Forest",
                  "Ranger Peak", "1120m", "34.73812", "-119.98421",
                  "Malaise trap", "Quercus agrifolia"):
        assert _norm(value) in combined, f"lost {value!r}"
    assert _norm("B Claridge") in combined
    assert _norm("J Doe") in combined


def test_overflow_splits_on_a_field_boundary():
    """A continuation label starts with a whole field, not half of one."""
    labels = format_event_all_labels(HEAVY, settings())
    assert labels[1][0].startswith("Malaise trap")


# --- ladder ordering -------------------------------------------------------

def test_sparse_event_gets_locality_on_its_own_line():
    """Rung 1: when there is room, the locality sits alone under the header."""
    labels = format_event_all_labels(SPARSE, settings())
    assert len(labels) == 1
    assert labels[0][0] == "USA; CA; Inyo Co."
    assert labels[0][1].startswith("Big Pine Creek")


def test_prettier_rungs_are_preferred_on_the_overflow_label():
    """A label that fits without breaking a value must not break one.

    Regression: the first pass reused the most permissive rung for the head of
    an overflow, so it broke the coordinates even though the label spilled to a
    second slip anyway and had room to keep them intact.
    """
    labels = format_event_all_labels(HEAVY, settings())
    joined = " ".join(labels[0])
    assert "34.73812 -119.98421" in joined, "coords broken needlessly"
    assert "1–14.vi.2025" in joined, "date broken needlessly"


def test_coord_dot_break_can_be_declined():
    """Unticking the setting removes that rung; content overflows instead."""
    s = settings(allowCoordDotBreak=False, allowDateDotBreak=False)
    labels = format_event_all_labels(HEAVY, s)
    for lines in labels:
        for line in lines:
            assert not line.rstrip().endswith("-119."), "coords broken anyway"
    assert _norm("34.73812") in _all_text(labels)


# --- host handling ---------------------------------------------------------

def test_split_host_label_moves_host_to_its_own_label():
    s = settings(splitHostLabel=True)
    labels = format_event_all_labels(HEAVY, s, exclude_host=True)
    assert all("Quercus" not in " ".join(lines) for lines in labels)

    label_sets = format_event_labels(HEAVY, 10, s)
    assert label_sets[-1][0][0] == "Quercus agrifolia"


def test_quantity_is_carried_to_every_label():
    label_sets = format_event_labels(HEAVY, 7, settings(splitHostLabel=True))
    assert len(label_sets) > 1
    assert all(qty == 7 for _, qty in label_sets)


# --- degenerate input ------------------------------------------------------

def test_single_oversized_field_does_not_exceed_the_cap():
    """One locality longer than a whole label still has to be capped."""
    event = {"locality": "Ridge " * 120}
    labels = format_event_all_labels(event, settings())
    assert len(labels) > 1
    for lines in labels:
        assert len(lines) <= 5


def test_empty_event_produces_one_padded_label():
    labels = format_event_all_labels({}, settings())
    assert len(labels) == 1
    assert len(labels[0]) == 4
    assert all(line == "" for line in labels[0])


def test_works_without_settings():
    labels = format_event_all_labels(SPARSE)
    assert labels and all(len(lines) <= 5 for lines in labels)


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if not name.startswith("test_") or not callable(fn):
            continue
        try:
            fn()
            print(f"PASS  {name}")
        except AssertionError as exc:
            failures += 1
            print(f"FAIL  {name}: {exc}")
    print(f"\n{failures} failure(s)")
    sys.exit(1 if failures else 0)
