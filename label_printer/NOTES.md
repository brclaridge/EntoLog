# Notes

## Italics invert when a `*...*` span wraps across lines

**Status:** known bug, not fixed. Found 2026-08-03.

`draw_rich_line` in `pdf_generator.py:67` decides italics one line at a time:
it splits the line on `*` and italicises the odd-indexed pieces. That has no
memory of whether the previous line ended inside an italic span, so any span
that wraps comes out backwards on the continuation line.

Real example from `data/collectingEvents.json`:

```
'collected as caterpillar in *P.'    → "P." italic — correct
'tremuloides* leaf roll, emerged'    → "tremuloides" UPRIGHT, " leaf roll…" ITALIC
```

The species epithet prints roman and the plain English prints italic.

**Scope:** 14 lines across the current 180 events. All of them are `host`
values, which in practice hold prose rearing notes with italicised taxon names
(`reared from *Anacampsis niveopulvella* collected as cat. in *P. tremuloides*
leaf roll`), not bare binomials. Pre-dates the layout ladder — a field wider
than the label has always wrapped.

**Detect:** any output line with an odd number of `*` has an unclosed span.

**Two ways to fix:**

1. Track italic state across lines in `draw_rich_line` — carry a flag from the
   end of one line into the start of the next.
2. Re-balance markers in `_do_wrap` (`label_formatter.py`) — close the span at
   the break and reopen it on the next line, so every line is self-contained.

(2) keeps `draw_rich_line` stateless and makes the line list correct on its own,
which is easier to test. Either way, add a case to `tests/test_label_layout.py`
asserting no emitted line has an odd `*` count.

## Related, deliberately not done

Overflow splits on whole-field boundaries, so a field that doesn't fit in the
remaining space moves entirely to the continuation label. This leaves label 1
under the cap on 11 of 16 overflowing events. Reviewed and accepted — letting
fields straddle labels would pack tighter but split one sentence across two
slips.
