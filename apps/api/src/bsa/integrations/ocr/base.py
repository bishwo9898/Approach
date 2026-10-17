"""Optical character recognition, behind an adapter.

The engine is swappable because the two places this runs cannot share one: a
coach's Mac has Apple's Vision framework, which reads this table essentially
perfectly, and a Linux container does not. What must *not* vary is everything
downstream -- `bsa.domain.screenshot_table` turns recognized lines into rows and
never learns which engine produced them.

An engine's only job is to return positioned text. It makes no judgement about
what the text means.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class TextLine:
    """One recognized line, boxed in image pixels with a top-left origin.

    Position is the whole point. A table is reconstructed from where text sits,
    not from the order an engine happens to emit it in, so an engine that
    cannot report boxes cannot be used here.
    """

    text: str
    confidence: float
    x: float
    y: float
    width: float
    height: float

    @property
    def center_x(self) -> float:
        return self.x + self.width / 2

    @property
    def center_y(self) -> float:
        return self.y + self.height / 2


class OcrUnavailableError(RuntimeError):
    """The configured engine cannot run here.

    Raised rather than falling back to a weaker engine: a silent downgrade
    would change how accurately athlete data is read without anyone choosing it.
    """


@runtime_checkable
class OcrEngine(Protocol):
    name: str

    def read(self, image: Path) -> list[TextLine]:
        """Every line of text in the image, with its box."""
        ...
