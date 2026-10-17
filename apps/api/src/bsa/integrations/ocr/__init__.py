"""OCR engine selection."""

from __future__ import annotations

from bsa.core.config import Settings
from bsa.core.errors import IntegrationNotConfiguredError
from bsa.integrations.ocr.base import OcrEngine, OcrUnavailableError, TextLine

__all__ = ["OcrEngine", "OcrUnavailableError", "TextLine", "get_ocr_engine"]


def get_ocr_engine(settings: Settings) -> OcrEngine:
    """The configured engine.

    There is no automatic fallback. If the configured engine cannot run, the
    request fails and says so: quietly switching to a weaker reader would
    change how accurately an athlete's numbers are read without anyone
    choosing it, and the output looks identical either way.
    """
    kind = settings.ocr_engine.lower()
    if kind == "vision":
        from bsa.integrations.ocr.vision import VisionOcrEngine

        return VisionOcrEngine()
    if kind == "tesseract":
        from bsa.integrations.ocr.tesseract import TesseractOcrEngine

        return TesseractOcrEngine()
    raise IntegrationNotConfiguredError(f"unknown OCR engine {kind!r}")
