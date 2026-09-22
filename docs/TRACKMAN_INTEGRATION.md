# TrackMan Integration

## Status: CSV ingestion, against a schema we invented

**The most important thing in this document:** the column names the parser
currently understands are **synthetic**. They are ours, modelled on the *shape*
we expect from a TrackMan event export. They are **not** real TrackMan column
names and no attempt has been made to guess them.

Nothing in this repository was built by inspecting, reverse engineering or
scraping a TrackMan product. Everything here runs on synthetic fixtures.

| Path | Status |
|---|---|
| CSV ingestion | **Implemented** against synthetic schema `synthetic.v1` |
| FTP retrieval | Interface defined, not implemented — no credentials |
| Data API | Not implemented — no credentials, no documentation |
| Webhook / play-by-play feed | Not implemented — availability unconfirmed |

## The provider interface

```python
class TrackmanProvider(Protocol):
    name: str
    def discover_sessions(self, *, since=None, until=None) -> Iterable[str]: ...
    def fetch_payload(self, reference: str) -> SourcePayload: ...
    def parse(self, payload: SourcePayload) -> ParseResult: ...
```

Split into three deliberately:

- `discover_sessions` is the **only** part that differs between a directory
  listing, an FTP poll and an API query.
- `fetch_payload` returns bytes we archive *before* interpreting them.
- `parse` is pure — bytes in, normalized objects out — so it can be replayed over
  the archive when the mapping changes.

`IngestionService` depends on this Protocol, never on a concrete provider.
Enabling FTP changes one object passed to a constructor.

## Adding the real schema (Phase 2)

When an authorized real export is available:

1. Run `python -m bsa.scripts.inspect_csv <file>` first. It lists every column,
   flags the ones that look like fields we need, and writes nothing.
2. Add a `ColumnMap` in `apps/api/src/bsa/integrations/trackman/mapping.py` with
   the real column names. Where the vendor reports a different unit from the one
   we store, set `source_unit` on that column:

   ```python
   "velocity_mph": NumericColumn(
       "ReleaseVelocity", Unit.MPH, 20.0, 110.0, source_unit="m/s"
   )
   ```

   This is the single most dangerous thing to get wrong: a velocity read as mph
   when it is metres per second is out by a factor of 2.24, and every resulting
   number still looks plausible. `min_value`/`max_value` are always expressed in
   the canonical unit, so the bounds do not move when the source unit does.
3. Register it in `COLUMN_MAPS` under a new version key.
4. Confirm `detect_schema` distinguishes it from `synthetic.v1` by its required
   columns.
5. Reprocess the archived raw imports — the originals are in object storage
   precisely so this does not require re-exporting from TrackMan.

Nothing outside that file should need to change. That separation is the entire
reason the file exists, and
`tests/integration/test_new_schema_support.py` proves it: it registers a schema
sharing no column names with ours, in different units, and asserts the whole
pipeline through to personal records still works.

**Do not** delete `synthetic.v1`. It backs the seed data and the test suite, and
it keeps a concrete example next to the documentation.

## `synthetic.v1`

One row per tracked pitch. Batted-ball columns are populated only when the ball
was put in play. Sample files: `samples/trackman/`.

| Column | Domain field | Unit |
|---|---|---|
| `SessionUID` | `sessions.external_session_id` | — |
| `SessionDate` | `sessions.session_date` | — |
| `SessionType`, `Venue` | session attributes | — |
| `SourceStatus` | `Preliminary` / `Verified` | — |
| `PitchUID` | `external_event_id` (both tables) | — |
| `PitchNo`, `UTCDateTime` | ordering, `event_at` | — |
| `PitcherId`, `PitcherName` | pitcher identity | — |
| `BatterId`, `BatterName` | batter identity | — |
| `TaggedPitchType`, `AutoPitchType` | `pitch_type`, `auto_pitch_type` | — |
| `PitchCall` | `pitch_call`, `is_strike` | — |
| `RelSpeed` | `velocity_mph` | mph |
| `SpinRate` | `spin_rate_rpm` | rpm |
| `SpinAxis` | `spin_axis_deg` | deg |
| `HorzBreak`, `InducedVertBreak` | movement | in |
| `RelHeight`, `RelSide`, `Extension` | release | ft |
| `PlateLocHeight`, `PlateLocSide` | plate location | ft |
| `VertApprAngle`, `HorzApprAngle` | approach angles | deg |
| `ExitSpeed` | `exit_velocity_mph` | mph |
| `Angle`, `Direction` | launch angle / direction | deg |
| `Distance` | `distance_ft` | ft |
| `HangTime` | `hang_time_s` | s |
| `HitSpinRate` | `hit_spin_rate_rpm` | rpm |
| `ContactPositionX/Y/Z` | contact position | ft |
| `TaggedHitType` | `batted_ball_type` | — |
| `Drill`, `Grip`, `Intent`, `BallType`, `BallWeightOz`, `TrainingBlock`, `Tags` | `training_context` JSONB | — |

Required for schema detection: `SessionUID`, `SessionDate`, `PitchUID`,
`PitcherId`.

## Parsing rules

1. **Never guess.** An unrecognized header fails the whole file. A misread column
   is worse than a rejected file, because it produces numbers that look fine.
2. **Never silently drop.** Every rejected row writes an `import_issues` row with
   a code, the offending field, and the 1-based row number.
3. **Never trust units.** Every value passes through `bsa.core.units.convert`,
   including identity conversions.
4. **Range-guard implausible readings.** A 268 mph "fastball" is a tracking
   artifact. It is discarded with an issue rather than stored — an impossible
   value that reaches the metric engine can become a permanent personal record.
5. **Never resolve athletes in the parser.** It reports the vendor's id; mapping
   is a database concern, downstream.
6. **A pitcher is not required.** Machine-fed cage work has a batter and no
   pitcher. A pitching machine must never become a player.
7. **Default to preliminary.** Data we later learn is verified can be promoted;
   preliminary data labelled verified is a lie the coach cannot detect.
8. **Preserve unknown labels.** An unrecognized pitch type is stored upper-cased,
   not bucketed into `OTHER` — bucketing hides a mapping we still owe.

## Pipeline

```
payload
  → SHA-256 checksum; identical bytes → SKIPPED_DUPLICATE, no-op
  → archive raw bytes to object storage (before any interpretation)
  → detect schema; parse rows, collecting issues
  → resolve athletes by explicit mapping only; unknowns queued, events held
  → upsert session (never duplicate)
  → upsert events on (session, external_event_id)
  → prune events the payload omits — only if it parsed cleanly
  → recalculate metric observations
  → recompute PR progressions
  → queue Futures sync jobs for new records
```

Terminal status: `SUCCESS` · `PARTIAL` (rejected rows or unresolved athletes) ·
`FAILED` · `SKIPPED_DUPLICATE`.

## Open questions for TrackMan

Blocking Phase 2/3:

1. **Which delivery methods are enabled for this organization?** Data API,
   organization FTP export, webhook feed — or only manual export?
2. **What are the real column names and units** in the export this facility
   receives? A single authorized sample export unblocks the mapping immediately.
3. **What is the stable event identifier?** We assume a per-pitch UID stable
   across a verified republish. If it is not stable, event upsert needs a
   different key and reconciliation gets meaningfully harder.
4. **How is verified data signalled?** A status column, a separate file, a
   different directory, or an API field? We currently read a `SourceStatus`
   column and default to preliminary.
5. **Can a session id ever be reused or re-issued?** Our uniqueness constraint
   assumes not.
6. **Is athlete id stable across seasons and roster re-entry?** Our model already
   allows several identities per athlete per provider, but we need to know whether
   that is common or exceptional.
7. **Which custom/training metadata fields are actually configurable** in the
   facility's TrackMan setup, and how do they appear in the export?
8. **For FTP:** hostname, credentials, directory layout, file naming, retention
   window, and how soon after a session a file appears.
9. **For the API:** base URL, auth flow, rate limits, pagination, and whether it
   exposes the same fields as the export.
10. **Are preliminary values ever withdrawn without replacement** (a session
    deleted rather than corrected)?

Until 1–4 are answered, CSV ingestion against `synthetic.v1` is the honest
maximum, and everything downstream of the adapter is already built and tested
against it.
