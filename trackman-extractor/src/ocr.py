"""Reading text off the screen with macOS's own Vision framework.

Vision ships with macOS, so there is no Tesseract to install and no model to
download. It is also markedly better than Tesseract on UI text: on a real
TrackMan capture it returns player names at confidence 1.00.

This is used for two things, both of which are *reads* -- nothing here moves
the mouse:

* discovering which athletes appear in the History list for a date range, and
* waiting until a screen has actually finished loading, instead of sleeping for
  a guessed number of seconds.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


class OcrError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class TextLine:
    """One line Vision recognized, with its box in image pixels, top-left origin."""

    text: str
    confidence: float
    x: float
    y: float
    width: float
    height: float

    @property
    def center(self) -> tuple[float, float]:
        return self.x + self.width / 2, self.y + self.height / 2


def _load_cgimage(path: Path):
    import Quartz

    url = Quartz.CFURLCreateWithFileSystemPath(
        None, str(path), Quartz.kCFURLPOSIXPathStyle, False
    )
    source = Quartz.CGImageSourceCreateWithURL(url, None)
    if source is None:
        raise OcrError(f"Could not read {path}")
    image = Quartz.CGImageSourceCreateImageAtIndex(source, 0, None)
    if image is None:
        raise OcrError(f"{path} is not an image Vision can read")
    return image


def recognize(path: Path, *, fast: bool = False) -> list[TextLine]:
    """Every line of text in an image, ordered top to bottom.

    `fast` trades accuracy for speed and is right for "has this screen loaded
    yet" polling, where the answer is a yes/no on a word we already know.
    """
    try:
        import Vision
    except ImportError as exc:  # pragma: no cover - depends on the install
        raise OcrError(
            "macOS Vision is not available. Install it with:\n"
            "  .venv/bin/pip install pyobjc-framework-Vision"
        ) from exc

    import Quartz

    image = _load_cgimage(path)
    width = float(Quartz.CGImageGetWidth(image))
    height = float(Quartz.CGImageGetHeight(image))

    request = Vision.VNRecognizeTextRequest.alloc().init()
    request.setRecognitionLevel_(
        Vision.VNRequestTextRecognitionLevelFast
        if fast
        else Vision.VNRequestTextRecognitionLevelAccurate
    )
    request.setUsesLanguageCorrection_(False)  # names and ids are not dictionary words

    handler = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(image, {})
    ok, error = handler.performRequests_error_([request], None)
    if not ok:
        raise OcrError(f"Vision could not read {path}: {error}")

    lines: list[TextLine] = []
    for observation in request.results() or []:
        candidates = observation.topCandidates_(1)
        if not candidates:
            continue
        candidate = candidates[0]
        box = observation.boundingBox()
        # Vision boxes are normalized with the origin at the BOTTOM-left.
        # Everything else in this project uses top-left pixels.
        lines.append(
            TextLine(
                text=candidate.string(),
                confidence=float(candidate.confidence()),
                x=box.origin.x * width,
                y=(1.0 - box.origin.y - box.size.height) * height,
                width=box.size.width * width,
                height=box.size.height * height,
            )
        )
    lines.sort(key=lambda line: (round(line.y), line.x))
    return lines


def find(lines: list[TextLine], pattern: str | re.Pattern[str]) -> TextLine | None:
    """The first line matching `pattern`, searched case-insensitively."""
    regex = pattern if isinstance(pattern, re.Pattern) else re.compile(pattern, re.I)
    return next((line for line in lines if regex.search(line.text)), None)


def contains(lines: list[TextLine], pattern: str | re.Pattern[str]) -> bool:
    return find(lines, pattern) is not None


def group_into_rows(lines: list[TextLine], tolerance: float = 0.6) -> list[list[TextLine]]:
    """Group lines that sit on the same visual row.

    Vision returns each word or cell separately, so a table row arrives as
    several lines at nearly the same y. `tolerance` is a fraction of line
    height, which keeps the grouping correct whatever the display scale.
    """
    rows: list[list[TextLine]] = []
    for line in sorted(lines, key=lambda item: item.y):
        if rows:
            last = rows[-1]
            reference = last[0]
            if abs(line.y - reference.y) <= tolerance * max(reference.height, 1.0):
                last.append(line)
                continue
        rows.append([line])
    for row in rows:
        row.sort(key=lambda item: item.x)
    return rows
