# Data Model

17 tables. Internal identity is always a UUID — never a vendor id, never a name.

```
organizations
├── users ──────────────────────► players (PLAYER accounts only)
├── players
│   ├── external_player_identities   (provider, external_id) → one player
│   └── identity_resolution_items    unknown vendor athletes, awaiting a human
├── raw_imports
│   └── import_issues                every rejected or flagged source row
├── sessions
│   ├── pitch_events
│   └── hit_events ──► pitch_events (optional link)
├── metric_definitions
│   ├── metric_observations
│   ├── personal_records             current best (a projection)
│   ├── personal_record_events       immutable progression
│   └── external_metric_mappings ──► sync_jobs
└── audit_logs
```

## Conventions

- **UUID primary keys** on every domain table.
- **`organization_id` on every tenant-owned table**, always filtered on.
- **`created_at` / `updated_at`** on every table, server-defaulted.
- **Enums as `VARCHAR` + `CHECK`**, not native Postgres `ENUM`. Adding a value to
  a native enum needs `ALTER TYPE`, which is awkward to run transactionally and
  awkward to reverse. A checked varchar gives the same integrity with ordinary
  migrations.
- **JSONB for genuinely open-ended data** (training context, metric specs,
  audit metadata), with GIN indexes where it is queried.
- **Measured columns name their unit** (`velocity_mph`, `distance_ft`).
- **Measurements are nullable.** TrackMan does not report every field for every
  pitch, and a missing measurement must be distinguishable from a zero.

---

## Identity

### `organizations`
`id, name, slug (unique), timezone, created_at, updated_at`

`timezone` is load-bearing, not decoration — it defines what "today" means for
every dashboard default.

### `users`
`id, organization_id, auth_provider, auth_subject, email, display_name, role,
player_id?, active, last_seen_at`

- Unique `(auth_provider, auth_subject)`.
- No credential material is ever stored. Password security belongs to the auth
  provider.
- `player_id` is set only for `role = PLAYER` and is the entire basis of player
  self-access.

### `players`
`id, organization_id, first_name, last_name, preferred_name?, date_of_birth?,
graduation_year?, position?, bats?, throws?, active`

Deliberately minimal on PII. This system holds data about minors, so a field is
added only when a feature requires it. `date_of_birth` is nullable, exists only
for future age-band grouping, and nothing in Phase 1 reads it.

### `external_player_identities`
`id, organization_id, player_id, provider, external_id, external_display_name?,
metadata, verified_at?`

- **Unique `(organization_id, provider, external_id)`** — the load-bearing
  constraint. One vendor identity can point at exactly one athlete, ever.
- A player may hold several identities per provider (TrackMan has been known to
  issue a new id after a roster re-entry), which is why uniqueness is on the
  external side rather than on `(player, provider)`.
- `external_display_name` is stored for operator recognition **only**. It is
  never used to match athletes.

### `identity_resolution_items`
`id, organization_id, provider, external_id, external_display_name?, status,
occurrence_count, first_seen_import_id?, last_seen_at?, resolved_player_id?,
resolved_at?, resolved_by_user_id?, notes?`

The queue for unknown vendor athletes. `occurrence_count` accumulates across
re-runs so the dashboard can rank by how much data is stuck.

---

## Provenance

### `raw_imports`
`id, organization_id, provider, import_type, filename?, checksum, byte_size,
object_key?, status, source_status, correlation_id, started_at?, completed_at?,
rows_total, rows_accepted, rows_rejected, error_message?, metadata`

- **Unique `(organization_id, provider, checksum)`** — the idempotency key.
- `object_key` is opaque; rows never contain a filesystem path or bucket URL, so
  the storage backend can change with no data migration.
- `correlation_id` ties every log line of one ingestion together.

`status`: `RECEIVED · PROCESSING · SUCCESS · PARTIAL · FAILED · SKIPPED_DUPLICATE`

### `import_issues`
`id, raw_import_id, row_number?, code, field?, message, context`

`code`: `SCHEMA_UNKNOWN · MISSING_REQUIRED_FIELD · INVALID_VALUE · INVALID_UNIT ·
PLAYER_UNRESOLVED · AMBIGUOUS_SESSION`

One bad row must not fail a good file, and must not vanish either. `row_number`
is 1-based as an operator counts rows when they open the file.

---

## Events

### `sessions` (model `TrainingSession`)
`id, organization_id, provider, external_session_id, session_date, started_at?,
ended_at?, session_type?, venue?, source_status, verified_at?, imported_at,
raw_import_id?, metadata`

- **Unique `(organization_id, provider, external_session_id)`** — a verified
  republish updates this row in place; there is exactly one row per real session,
  ever.
- `session_date` is the facility-local calendar date and is what day/week/month
  rollups group on.
- Named `TrainingSession` in Python to avoid colliding with SQLAlchemy's
  `Session` in every module that touches both.

### `pitch_events`
`id, organization_id, session_id, player_id, external_event_id, pitch_number?,
event_at?, pitch_type?, auto_pitch_type?, pitch_call?, is_strike?,
velocity_mph?, spin_rate_rpm?, spin_axis_deg?, horizontal_break_in?,
vertical_break_in?, release_height_ft?, release_side_ft?, extension_ft?,
plate_location_height_ft?, plate_location_side_ft?,
vertical_approach_angle_deg?, horizontal_approach_angle_deg?,
training_context, source_status, raw_import_id?`

- **Unique `(session_id, external_event_id)`** — re-ingestion upserts.
- `pitch_type` (what the coach tagged) is kept separate from `auto_pitch_type`
  (what the vendor's classifier said). They disagree, and the coach's intent is
  the one that matters for "fastball velocity".
- `is_strike` is `NULL` for balls in play and hit-by-pitch — neither a strike nor
  a ball, so they are excluded from strike percentage entirely rather than
  counted as misses.

### `hit_events`
`id, organization_id, session_id, player_id, pitch_event_id?, external_event_id,
swing_number?, event_at?, exit_velocity_mph?, launch_angle_deg?,
launch_direction_deg?, distance_ft?, hang_time_s?, hit_spin_rate_rpm?,
contact_position_{x,y,z}_ft?, batted_ball_type?, training_context,
source_status, raw_import_id?`

- **Unique `(session_id, external_event_id)`**.
- A hit event needs no pitcher: machine-fed cage work has a batter and no
  pitcher, and a pitching machine must never enter the player table.

### `training_context` (JSONB, GIN-indexed, on both event tables)

Drill, grip, intent, ball type, ball weight, training block, coach tags. Schema-free
on purpose: the dimensions that will matter are not known yet, and this is the
raw material for Phase 8's training-effectiveness analytics. Keys that prove
load-bearing get promoted to real columns in a later migration.

Metric filters can already address these as `ctx.<key>` (e.g. `ctx.drill`), so
"does this drill correlate with improvement" is answerable without a schema
change.

---

## Analytics

### `metric_definitions`
`id, organization_id, key, display_name, description?, category, event_source,
aggregation, record_direction, data_type, unit, display_precision,
min_sample_size, spec, calculation_version, enabled, is_headline, sort_order,
metadata`

- **Unique `(organization_id, key)`**. `key` is the stable dotted identifier code
  refers to; `display_name` is free to change.
- `unit` is `NOT NULL`.
- `spec` is validated against `MetricSpec` before it is written.
- `calculation_version` is bumped by hand when a formula changes meaning.

`aggregation`: `MAX · MIN · AVG · SUM · COUNT · RATE`
`record_direction`: `HIGHER_IS_BETTER · LOWER_IS_BETTER · NONE`

`NONE` means tracked and charted but never a record — used where "better" is
genuinely coach- and athlete-dependent (spin rate), and for volume metrics
(pitch count), where throwing more pitches is not an achievement.

### `metric_observations`
`id, organization_id, player_id, metric_definition_id, period, period_start,
session_id?, value, sample_size, source_status, calculation_version,
calculated_at, context`

- **Unique `(player_id, metric_definition_id, period, period_start, session_id,
  calculation_version)`**.
- Phase 1 materializes only `period = SESSION`. These are the atoms: day/week/
  month rollups and the PR progression are all derived from this ordered series,
  so re-deriving them is cheap and always consistent with the events.
- `sample_size` travels with every value and is displayed with every chart. A
  96 mph average off two pitches is not the same claim as off forty.

### `personal_records`
`id, organization_id, player_id, metric_definition_id, value, sample_size,
session_id?, achieved_on, achieved_at?, source_status, calculation_version,
context, is_manual_override, override_reason?`

- **Unique `(player_id, metric_definition_id)`**.
- A projection of the last row of the progression. Always rebuilt from the event
  series, never incremented in place.
- `is_manual_override` pins a value an admin set by hand; the engine then leaves
  it alone.

### `personal_record_events`
`id, organization_id, player_id, metric_definition_id, session_id,
previous_value?, new_value, delta?, sample_size, achieved_on, achieved_at?,
source_status, calculation_version, context, superseded_at?, superseded_reason?`

- **Unique `(player_id, metric_definition_id, session_id)`** — what makes the PR
  engine idempotent. Re-importing a session rewrites its row rather than
  announcing the same achievement twice.
- `previous_value` is `NULL` for a first record; `delta` is then `NULL` too,
  because reporting "+86.6" for a first record is nonsense.
- `delta` preserves sign. An improvement on a lower-is-better metric is negative.
- `superseded_at` tombstones a record that corrected data no longer supports. The
  row **stays** — the audit trail must show what the coach was told at the time.

---

## Synchronization

### `external_metric_mappings`
`id, organization_id, metric_definition_id, destination, destination_field,
destination_unit?, destination_precision, enabled, metadata`

Unique `(organization_id, destination, metric_definition_id)`. `destination` is a
string, not an enum, so a second destination needs no migration.

### `sync_jobs`
`id, organization_id, player_id, metric_definition_id, personal_record_event_id?,
destination, destination_field, value, unit, status, attempt_count, last_error?,
last_attempted_at?, completed_at?, completed_by_user_id?`

- Unique `(player, metric, destination, personal_record_event)` — re-running
  ingestion refreshes the pending instruction rather than giving the coach the
  same item twice.
- `value` and `unit` are frozen at queue time, so the worklist shows what was
  intended even if the metric is later recalculated.
- A `SYNCED` job is never reopened by a recalculation: the coach already typed
  that value.

`status`: `PENDING · SYNCED · FAILED · MANUAL_REQUIRED`

---

## Audit

### `audit_logs`
`id, organization_id, actor_user_id?, actor_label, action, target_type,
target_id?, metadata`

`action`: `PLAYER_MAPPING_CREATED · PLAYER_MAPPING_CHANGED · METRIC_CREATED ·
METRIC_CHANGED · PR_OVERRIDDEN · FUTURES_SYNC_MANUALLY_CONFIRMED ·
IMPORT_REPROCESSED`

Scope is narrow on purpose: administrative actions that override or reshape
athlete-facing data. It is not a request log.

`actor_label` is stored alongside the user id so the log stays readable after a
user row is deactivated or renamed. Metadata is scrubbed of anything resembling a
credential before it is written — audit rows are the most widely-read table
during an incident.

---

## Questions this model answers directly

| Question | Path |
|---|---|
| What did Jake do today? | `sessions` by `organization_id + session_date`, joined to events |
| What is Jake's fastball PR, and when? | `personal_records` by `(player, metric)` |
| How has Jake's velocity moved over 30 days? | `metric_observations` windowed on `period_start` |
| What were Jake's last 10 sessions? | `sessions` via events, ordered by date |
| Who hit a PR today? | `personal_record_events` by `achieved_on`, `superseded_at IS NULL` |
| Who improved most this month? | Two windowed observation aggregates, compared |
| Who hasn't trained recently? | `players` left-joined against max session date |
| Does a drill correlate with improvement? | `training_context` GIN index + metric filters on `ctx.*` |
| Which Futures records need updating? | `sync_jobs` where status ≠ `SYNCED` |
