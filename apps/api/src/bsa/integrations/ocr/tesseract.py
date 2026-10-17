"""Tesseract text recognition, for where Apple's Vision is not available.

Used by the containerised API. Configured for a uniform block of text, which
is what a rendered table is, and told to keep its confidence per word so the
caller can see how sure it was.

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

        lines: list[TextLine] = []
        for index, text in enumerate(data["text"]):
            word = (text or "").strip()
            if not word:
                continue
            confidence = float(data["conf"][index])
            lines.append(
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
        return lines
