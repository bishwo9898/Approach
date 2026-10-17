# Not in use

This project automated the *capture* step: driving TrackMan to take the
screenshots itself. It works, but the facility decided screenshots are taken by
hand, so nothing here runs as part of the app.

**What replaced it:** reading the screenshots, which is now in the API —
`bsa.domain.screenshot_table` for the table, `bsa.integrations.ocr` for the
engines. A coach uploads images on the Imports page and the pitches land on the
athlete they picked.

**What is worth keeping:** the capture flows in `config.yaml` and the UI
calibration in `src/ui.py`, if automated capture is ever wanted again. The OCR
here (`src/ocr.py`) has been superseded by `bsa.integrations.ocr.vision`, which
is the same Apple Vision call behind the API's adapter.
