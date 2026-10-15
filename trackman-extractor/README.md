# TrackMan table capture

Automates the "screenshot, scroll, screenshot" routine for TrackMan Baseball Pro's
Table view on macOS, for one athlete or for everyone who hit in a date range.
**Phase 1 (this code): screenshots only.** Phase 2 (table extraction to CSV) will
read the folders this produces.

It only drives the TrackMan window you are already logged into, exactly as you would
by hand. It does not use TrackMan's API, FTP, exports or network traffic.

```bash
# everyone who hit between two dates
python main.py --list-sessions --from 2026-10-01 --to 2026-10-15   # read, don't click
python main.py --capture-range --from 2026-10-01 --to 2026-10-15
```

## How it works

```
screenshot the table area ─► same as the last page? ─► yes, twice in a row ─► stop (bottom)
        ▲                          │ no
        │                          ▼
   wait 0.8 s ◄── scroll 70% ◄── save page_NNN.png, check it overlaps the previous page
```

* **Lightweight.** No screen recording, no OCR, no polling. macOS's own `screencapture`
  writes each image straight to disk. Between pages the program keeps only a ~0.6 MB
  grayscale fingerprint and spends its time asleep. Each comparison takes about 5 ms.
* **No skipped rows.** Each scroll moves about 70% of the table, so pages overlap. After
  every scroll the program checks that the bottom rows of the previous page appear again
  in the new one. If they don't, it logs a warning and marks that page in `metadata.json`.
  It also records exactly how many pixels each scroll moved (`scroll_shift_px`), which
  Phase 2 uses to drop the repeated rows.
* **Finding the bottom.** When a scroll no longer changes the picture
  (`unchanged_frames_required` times in a row, default 2), the table has ended. Unchanged
  frames are not saved.
* **Region relative to the window.** The capture area is stored relative to the TrackMan
  window, so moving the window is fine. If the window is resized, the run stops.

## Setup (once)

```bash
cd trackman-extractor
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

### macOS permissions (exactly two)

Grant both to **the app you run the command from** (Terminal, iTerm or VS Code), not to
Python. Then **quit and reopen that app**, because macOS only applies these at launch.

| Permission | System Settings → Privacy & Security → | Why |
|---|---|---|
| **Accessibility** | Accessibility | To move the mouse onto the table and send scroll events. |
| **Screen Recording** | Screen & System Audio Recording | To screenshot TrackMan's window. Without it macOS silently returns blank images, which is why the program checks for it first. |

Not needed: **Input Monitoring**. That permission is what a global ESC hotkey would
require, so there is no ESC hotkey; use the stop methods below. **Automation** isn't
needed either, because TrackMan is focused with `open -b`, not AppleScript.

`python main.py --dry-run` checks everything. If a permission is missing it asks macOS
to show the prompt and to list your terminal in Settings.

> Run it from the macOS **Terminal** app if you can. Granting Screen Recording to VS Code
> also lets every VS Code extension capture your screen.

## Stopping a run

* **Move the mouse into any corner of the screen** (PyAutoGUI failsafe). This is checked
  every 0.1 s, even while waiting.
* **Ctrl+C** in the terminal.
* If another window covers the table, the program brings TrackMan forward. If the
  window stays covered, it stops.

Pages already saved are never deleted. `metadata.json` is updated after every page and
records `"status": "interrupted"`.

## Calibrate (once, and again whenever you change the TrackMan window size)

Make the TrackMan window as large as you'll always use it. A bigger window means more
rows per page, and **every column of the Hit table must be visible without
scrolling sideways**, because horizontal scrolling isn't handled yet. Open any player's
Hit → Table view, then:

1. **Mark the table area**: `.venv/bin/python main.py --pick-region`
   Keep the terminal focused and hover the mouse over TrackMan:
   * top-left corner: include the **column-name row** (PITCH SPEED…). The program finds
     sticky headers on its own, and Phase 2 needs the column names on every page.
   * bottom-right corner: the last fully visible row. Leave out the "Not assigned" legend
     and include the full width of the last column.

   This writes the `region:` block in `config.yaml`.
2. **Check the area**: `.venv/bin/python main.py --test-region` saves one screenshot to
   `captures/_calibration/` and opens it. Nothing should be cut off.
3. **Check the scroll**: `.venv/bin/python main.py --calibrate-scroll` scrolls once,
   measures how far the rows actually moved, scrolls back, and tells you what to change.
   For example:
   `Scrolling 420 points moved the table 420 points: 77% of the 542-point scrolling area, so consecutive pages overlap by 23%.`
   If TrackMan ignores pixel scrolling or scrolls the wrong way, this says which setting
   to change (`scroll.unit: line` or `scroll.invert: true`).

## Test with one player

1. In TrackMan, open the player → Hit → Table. You can leave it scrolled anywhere,
   because the program scrolls to the top first.
2. `.venv/bin/python main.py --dry-run` should end with `Ready.`
3. `.venv/bin/python main.py --capture-current-player "Jordan Avery"`
   Take your hand off the mouse during the 3-second countdown.

```
[INFO] Starting capture for Jordan Avery (Hit table)
[INFO] Scrolling to the top of the table
[INFO] Captured page 1
[INFO] Captured page 2
[INFO] Captured page 3
[INFO] No movement detected (1/2)
[INFO] No movement detected (2/2)
[INFO] Bottom reached
[INFO] Completed Jordan Avery - 3 pages
```

4. Check the result: look at the first and last rows of each page and the next one. They
   should repeat a few rows, and the last page should end at the table's last row. Run it
   on 2–3 players before trusting it on more.

## Capturing everyone who hit in a date range

Switching athlete means driving TrackMan's own UI, which needs two things Phase 1
did not: knowing *who* to capture, and knowing *how* to get to them.

### Discover by reading, navigate by typing

**Who** comes from TrackMan's History list. A hand-written list of athletes is
wrong the moment somebody new hits, so `--list-sessions` reads the list instead,
using macOS's own Vision OCR — no Tesseract, nothing to download.

**How** is typing, not clicking rows. Clicking row *n* of a list depends on row
height, scroll position and the list not having reflowed. Typing a name into the
search field and clicking the first result does not. So discovery reads, and
navigation types.

Reading can get a name wrong, so the two are separate steps and the thing between
them is **a text file you can edit**:

```
python main.py --list-sessions ──► rosters/roster_<from>_<to>.txt ──► --capture-range
                (clicks nothing)        (read it, fix it)
```

`--list-sessions` also counts rows that showed an athlete id but no readable name,
and says so. A missing athlete is the one failure that would otherwise be
invisible — a row that was skipped looks exactly like a row that was never there.

### Setting it up

`--pick-region` and `--calibrate-scroll` are still needed; so is one more pass for
the controls used to switch athlete.

1. **Mark the controls**: `.venv/bin/python main.py --pick-ui`
   It asks for each one in turn — the HISTORY button, the "All players" dropdown,
   its search field, the first name under it, the Hit view, the Table view — and
   then for the History rows as an area to read. Press `s` to skip one and keep
   what is already saved.
2. **Check them**: `.venv/bin/python main.py --verify-ui` moves the pointer over
   each control and traces the area. **It clicks nothing.** If the pointer lands
   somewhere unexpected, run `--pick-ui` again for that one.

### Running it

```bash
# 1. Who hit? Reads the History list. Clicks nothing.
.venv/bin/python main.py --list-sessions --from 2026-10-01 --to 2026-10-15

# 2. Read rosters/roster_2026-10-01_2026-10-15.txt.
#    Fix a misread name, or delete a line to skip somebody.

# 3. Capture them all.
.venv/bin/python main.py --capture-range --from 2026-10-01 --to 2026-10-15
```

Dates take `YYYY-MM-DD`, `today` or `yesterday`. `--on DAY` is shorthand for a
single day. `--roster FILE` captures a list you wrote yourself, with no discovery
step at all.

One athlete failing does not end the run: it is recorded and the next one starts.
Afterwards, `--resume` does only the ones that did not finish:

```bash
.venv/bin/python main.py --capture-range --from 2026-10-01 --to 2026-10-15 --resume
```

Stopping on purpose — the failsafe corner or Ctrl+C — stops everything.

### Flows: how it gets around TrackMan

The click sequences live in `config.yaml` under `flows:`, not in Python, for the
same reason every other setting does. TrackMan will move something eventually, and
the fix should be a few lines of YAML.

```yaml
select_player:
  - click: player_filter
  - wait: 0.4
  - click: player_search
  - type: "{player}"          # the athlete's name
  - wait: 0.8
  - click: player_first_result
  - wait_for_text: "{player_regex}"   # their name, escaped for the regex
```

Actions: `click` (a `ui.targets` name), `type`, `press` (enter/escape/tab/up/down),
`wait` (seconds), `wait_for_text` (a regex to wait for), and
`scroll: {area:, amount:, direction:}`.

**Prefer `wait_for_text` to `wait`.** A fixed sleep is either too short — it clicks
a screen that has not loaded — or too long, and forty athletes take an hour.
Waiting for the text that proves the screen arrived is faster *and* more reliable.
When one times out it says what it was waiting for and suggests `--verify-ui`.

The flows shipped in `config.yaml` are a starting point written from screenshots,
**not something verified against a running TrackMan**. Expect to adjust them once.

### What it writes

```
captures/2026-10-09/
  _run_20261009_143022.json   what happened to each athlete
  jordan_avery/
    page_001.png  …  metadata.json
  riley_chen/
rosters/roster_2026-10-01_2026-10-15.txt
```

The manifest is rewritten after every athlete, so a run that is interrupted still
leaves a complete record of what got done. `--resume` reads it.

## Output

```
captures/
  2026-10-04/
    jordan_avery/          (jordan_avery_2/ if you capture the same player again that day)
      page_001.png
      page_002.png
      metadata.json
logs/capture_2026-10-04.log
```

`metadata.json` (abridged):

```json
{
  "schema_version": 1,
  "player": "Jordan Avery",
  "source": "TrackMan Baseball Pro",
  "view": "Hit",
  "capture_date": "2026-10-04", "capture_time": "14:02:11",
  "status": "complete", "stop_reason": "bottom_reached",
  "pages": 3, "page_order": "top_to_bottom", "pixel_scale": 2.0,
  "screenshot_region": { "units": "points", "screen": {...}, "relative_to_window": {...}, "window": {...} },
  "scroll": { "unit": "pixel", "amount": 420, "target_fraction": 0.7 },
  "warnings": [],
  "files": [
    { "page": 2, "file": "page_002.png", "scroll_shift_px": 840,
      "overlap_with_previous": "overlap", "body_top_px": 96, "body_bottom_px": 1180 }
  ]
}
```

For Phase 2: image rows above `body_top_px` are the sticky column header. On page *n*, the
first `body_bottom_px − body_top_px − scroll_shift_px` pixels of the scrolling area repeat
page *n − 1*.

`captures/`, `logs/` and `players.txt` contain real athlete names and are gitignored.
**This repository is public. Never force-add them.**

## Tuning (`config.yaml`)

| Symptom | Change |
|---|---|
| "rows may have been skipped" warnings | lower `scroll.target_fraction` (or `scroll.amount`); raise `timing.wait_after_scroll` |
| Stops before the real bottom | raise `timing.wait_after_scroll` or `detection.unchanged_frames_required` |
| Keeps saving near-identical last pages | raise `detection.unchanged_threshold` a little (e.g. 0.005) |
| "window is … but was …" | resize TrackMan back, or re-run `--pick-region` |
| A flow times out waiting for text | run `--verify-ui`; the previous click probably missed |
| An athlete is missing from the roster file | add the line by hand; raise `timing.wait_after_scroll` if whole pages are missing |
| A name is misspelled in the roster file | fix the line — it is what `--capture-range` reads |
| Column headings read as athletes | tighten `history.name_pattern` |
| Typing into search gets truncated | raise `timing.type_interval` |
| Screens are slower than 15 s | raise `timing.wait_for_text_timeout` |

## Tests

```bash
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
```

The tests run the whole capture loop against a simulated TrackMan table (sticky header
and legend, mostly `-` cells, 2x Retina scale), so no app or permissions are needed.
The flow engine is covered the same way, through a recording stand-in for the mouse
and screen, including the paths that only happen when a screen never loads.

`test_roster.py` also holds the cases that came from running the reader against real
TrackMan screenshots: avatar initials merged into a name (`BD Sam Okafor`), a
date that lost its space (`1Oct 2026`), and an athlete whose id was read but whose
name was not.

## Layout

```
main.py                  command line
config.yaml              every tunable setting, including the flows

one athlete
  src/table_capture.py   the capture loop: screenshot, scroll, repeat
  src/compare.py         fingerprints, bottom detection, overlap check
  src/capture.py         screencapture wrapper

a roster
  src/run.py             --list-sessions and --capture-range, manifests, --resume
  src/roster.py          reading athletes and dates out of the History list
  src/steps.py           the flow engine (click / type / wait_for_text / scroll)
  src/live.py            the real mouse, keyboard and screen behind a flow
  src/ocr.py             macOS Vision text recognition
  src/ui.py              calibrated click points and readable areas

shared
  src/scrolling.py       scrolling, mouse, failsafe-aware waits
  src/macos.py           permissions, TrackMan window, focus, keep-awake
  src/calibrate.py       --dry-run, --pick-region/-ui, --test-region, --verify-ui
  src/metadata.py        metadata.json
  src/config.py          loads and validates config.yaml
```

## Roadmap

1. ✅ Single athlete: capture the open table.
2. ✅ A whole roster for a date range.
3. Phase 2: screenshots → rows → deduplicate overlaps → validate → CSV / PostgreSQL.
