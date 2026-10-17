"""Tesseract text recognition, for where Apple's Vision is not available.

Used by the containerised API.

The work here is turning Tesseract's output into the shape the table reader
expects. Tesseract reports one box per **word**, so "PITCH SPEED" arrives as
two boxes and a header match on "pitch speed" finds nothing; grouping by its
own line numbers goes too far the other way and merges a whole table row into
one string. Neither is a cell.

So words are regrouped into cells: joined when the gap between them is an
ordinary space, split when it is a column gap. The threshold is a multiple of
text height rather than a pixel count, so it holds at any zoom or display
scale -- the same reason the table reader measures rows that way.

A caveat worth stating plainly: this engine has not been measured against real
TrackMan screenshots the way the Vision engine has, where 60 pitches came back
with 349 of 349 readable values correct. Everything downstream validates what
it is given -- ranges, column assignment, and the pitch-number sequence -- so a
worse reader produces more refusals rather than wrong numbers. But if the
conversion runs here, expect to confirm more rows by hand.
"""

from __future__ import annotations

from pathlib import Path

from bsa.integrations.ocr.base import OcrUnavailableError, TextLine


class TesseractOcrEngine:
    name = "tesseract"

    #: Treat the image as a single uniform block. A table's cells are not
    #: paragraphs, and the default page-segmentation mode invents a reading
    #: order that scrambles columns.
    CONFIG = "--psm 6"

    def read(self, image: Path) -> list[TextLine]:
        try:
            import pytesseract
            from PIL import Image
        except ImportError as exc:  # pragma: no cover -- not installed
            raise OcrUnavailableError(
                "Tesseract support is not installed. The API image needs the "
                "tesseract-ocr package plus pytesseract and pillow."
            ) from exc

        try:
            data = pytesseract.image_to_data(
                Image.open(image),
                config=self.CONFIG,
                output_type=pytesseract.Output.DICT,
            )
        except Exception as exc:  # pragma: no cover -- binary missing or image unreadable
            raise OcrUnavailableError(f"Tesseract could not read {image.name}: {exc}") from exc

        words: list[TextLine] = []
        for index, text in enumerate(data["text"]):
            word = (text or "").strip()
            if not word:
                continue
            confidence = float(data["conf"][index])
            words.append(
                TextLine(
                    text=word,
                    # Tesseract reports -1 where it has no opinion.
                    confidence=max(confidence, 0.0) / 100.0,
                    x=float(data["left"][index]),
                    y=float(data["top"][index]),
                    width=float(data["width"][index]),
                    height=float(data["height"][index]),
                )
            )
        return group_words_into_cells(words)


#: A gap wider than this many multiples of text height separates columns
#: rather than words. An ordinary space runs about a third of the height; the
#: gap between table columns is several times it, so the two do not overlap and
#: the exact value is not delicate.
COLUMN_GAP_RATIO = 1.2

#: Words on the same visual line, as a fraction of text height. Matches the
#: tolerance the table reader uses for the same reason.
SAME_LINE_RATIO = 0.6


def group_words_into_cells(
    words: list[TextLine],
    *,
    column_gap_ratio: float = COLUMN_GAP_RATIO,
    same_line_ratio: float = SAME_LINE_RATIO,
) -> list[TextLine]:
    """Join words into cells, splitting where a column gap falls.

    Pure and separately testable, because this is where a Tesseract reading
    goes wrong: too eager and two columns merge into one unparseable cell, too
    shy and "PITCH SPEED" never matches a header.
    """
    if not words:
        return []

    rows: list[list[TextLine]] = []
    for word in sorted(words, key=lambda w: (w.center_y, w.x)):
        placed = False
        for row in rows:
            reference = sum(w.height for w in row) / len(row)
            if abs(word.center_y - row[0].center_y) <= reference * same_line_ratio:
                row.append(word)
                placed = True
                break
        if not placed:
            rows.append([word])

    cells: list[TextLine] = []
    for row in rows:
        ordered = sorted(row, key=lambda w: w.x)
        group = [ordered[0]]
        for word in ordered[1:]:
            previous = group[-1]
            gap = word.x - (previous.x + previous.width)
            if gap > previous.height * column_gap_ratio:
                cells.append(_join(group))
                group = [word]
            else:
                group.append(word)
        cells.append(_join(group))
    return cells


def _join(group: list[TextLine]) -> TextLine:
    left = min(w.x for w in group)
    top = min(w.y for w in group)
    right = max(w.x + w.width for w in group)
    bottom = max(w.y + w.height for w in group)
    return TextLine(
        text=" ".join(w.text for w in group),
        confidence=min(w.confidence for w in group),
        x=left,
        y=top,
        width=right - left,
        height=bottom - top,
    )
