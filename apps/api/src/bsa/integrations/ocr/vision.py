"""Apple Vision text recognition.

Native to macOS, needs no model download and no network, and reads this
particular table at a confidence of 1.00 -- it is rendered UI text, which is
the easiest thing OCR ever sees.

Only available on macOS, which is where the coach taking the screenshots
already is.
"""

from __future__ import annotations

from pathlib import Path

from bsa.integrations.ocr.base import OcrUnavailableError, TextLine


class VisionOcrEngine:
    name = "vision"

    def read(self, image: Path) -> list[TextLine]:
        try:
            import Quartz
            import Vision
        except ImportError as exc:  # pragma: no cover -- not macOS
            raise OcrUnavailableError(
                "Apple Vision is unavailable here. It needs macOS and "
                "pyobjc-framework-Vision; set BSA_OCR_ENGINE=tesseract instead."
            ) from exc

        url = Quartz.CFURLCreateWithFileSystemPath(
            Quartz.kCFAllocatorDefault, str(image), Quartz.kCFURLPOSIXPathStyle, False
        )
        source = Quartz.CGImageSourceCreateWithURL(url, None)
        if source is None:
            raise OcrUnavailableError(f"{image.name} could not be read as an image")
        cg_image = Quartz.CGImageSourceCreateImageAtIndex(source, 0, None)
        if cg_image is None:
            raise OcrUnavailableError(f"{image.name} contains no decodable image")

        width = Quartz.CGImageGetWidth(cg_image)
        height = Quartz.CGImageGetHeight(cg_image)

        request = Vision.VNRecognizeTextRequest.alloc().init()
        request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
        # Player names and TrackMan ids are not dictionary words, and language
        # correction is happy to turn one into another.
        request.setUsesLanguageCorrection_(False)

        handler = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(cg_image, None)
        success, error = handler.performRequests_error_([request], None)
        if not success:  # pragma: no cover -- framework failure
            raise OcrUnavailableError(f"Vision failed on {image.name}: {error}")

        lines: list[TextLine] = []
        for observation in request.results() or []:
            candidate = observation.topCandidates_(1)
            if not candidate:
                continue
            box = observation.boundingBox()
            # Vision reports a normalized box with the origin at the BOTTOM
            # left. Everything downstream assumes pixels from the top left.
            lines.append(
                TextLine(
                    text=str(candidate[0].string()),
                    confidence=float(candidate[0].confidence()),
                    x=box.origin.x * width,
                    y=(1.0 - box.origin.y - box.size.height) * height,
                    width=box.size.width * width,
                    height=box.size.height * height,
                )
            )
        return lines
