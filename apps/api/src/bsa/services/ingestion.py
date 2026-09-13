"""The ingestion pipeline.

    payload -> checksum/dedupe -> archive raw bytes -> parse -> resolve players
      -> upsert session -> upsert events -> metrics -> personal records -> sync queue

Guarantees this module is responsible for:

  * **Idempotent.** The same bytes produce no second import. The same session
    produces no second session, no duplicated events, no repeated PR
    announcement.
  * **Non-destructive.** Raw bytes are archived before they are interpreted.
  * **Partially recoverable.** One unresolvable athlete or one malformed row
    does not fail the file; it is recorded and the rest proceeds.
  * **Honest.** Nothing is attributed to an athlete on a guess.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

import structlog
from sqlalchemy.orm import Session

from bsa.core.errors import ValidationError
from bsa.core.logging import get_logger
from bsa.db.models import Organization, RawImport
from bsa.db.repositories import imports as imports_repo
from bsa.db.repositories import players as players_repo
from bsa.db.repositories import sessions as sessions_repo
from bsa.domain.enums import ImportIssueCode, ImportStatus, SourceStatus
from bsa.integrations.storage.base import ObjectStore, build_object_key
from bsa.integrations.trackman.base import TrackmanProvider
from bsa.integrations.trackman.schema import (
    ParsedSession,
    ParseResult,
    RowIssue,
    SourcePayload,
)
from bsa.services import metrics as metrics_service
from bsa.services import records as records_service
from bsa.services import sync as sync_service

log = get_logger(__name__)


@dataclass(slots=True)
class ImportOutcome:
    """Everything an operator needs to understand what an import did."""

    raw_import_id: uuid.UUID
    status: ImportStatus
    correlation_id: str
    duplicate_of: uuid.UUID | None = None

    sessions_created: int = 0
    sessions_updated: int = 0
    pitch_events: int = 0
    hit_events: int = 0
    events_pruned: int = 0
    metric_observations: int = 0
    new_personal_records: int = 0
    sync_jobs_queued: int = 0

    rows_total: int = 0
    rows_accepted: int = 0
    rows_rejected: int = 0
    unresolved_players: list[str] = field(default_factory=list)
    issues: list[RowIssue] = field(default_factory=list)
    error_message: str | None = None

    @property
    def is_duplicate(self) -> bool:
        return self.status is ImportStatus.SKIPPED_DUPLICATE


class IngestionService:
    """Runs a TrackMan payload through to dashboards.

    Depends on the `TrackmanProvider` protocol, not on a concrete provider: when
    FTP or the Data API is enabled, only the object passed to this constructor
    changes.
    """

    def __init__(
        self,
        db: Session,
        organization: Organization,
        provider: TrackmanProvider,
        object_store: ObjectStore,
    ) -> None:
        self.db = db
        self.organization = organization
        self.provider = provider
        self.object_store = object_store

    # -- entry point ----------------------------------------------------------

    def ingest(self, payload: SourcePayload, *, force_reprocess: bool = False) -> ImportOutcome:
        """Ingest one payload end to end."""
        correlation_id = uuid.uuid4().hex[:16]
        structlog.contextvars.bind_contextvars(
            correlation_id=correlation_id,
            provider=self.provider.name,
            organization=self.organization.slug,
        )
        try:
            return self._ingest(payload, correlation_id, force_reprocess=force_reprocess)
        finally:
            structlog.contextvars.clear_contextvars()

    def reprocess(self, raw_import: RawImport) -> ImportOutcome:
        """Re-run a stored import from its archived bytes.

        This is what the raw archive exists for. Two cases need it:

          * An athlete who was unmapped at ingest time has since been resolved,
            and their held events must be recovered. Without this, mapping an
            athlete fixes nothing that already happened.
          * The parser or a metric changed and historical imports should be
            re-derived, without asking the facility to re-export from TrackMan.

        Goes through the ordinary pipeline, so it is as idempotent as a first
        run: reprocessing an import that needs nothing changes nothing.
        """
        if not raw_import.object_key:
            raise ValidationError("this import has no archived payload and cannot be reprocessed")

        try:
            data = self.object_store.get(raw_import.object_key)
        except (OSError, KeyError) as exc:
            raise ValidationError(
                f"the archived payload for this import could not be read: {exc}"
            ) from exc

        return self.ingest(
            SourcePayload(
                data=data,
                filename=raw_import.filename,
                import_type=raw_import.import_type,
            ),
            force_reprocess=True,
        )

    def _ingest(
        self, payload: SourcePayload, correlation_id: str, *, force_reprocess: bool
    ) -> ImportOutcome:
        checksum = hashlib.sha256(payload.data).hexdigest()
        started = datetime.now(UTC)

        existing = imports_repo.find_by_checksum(
            self.db, self.organization.id, self.provider.name, checksum
        )
        if existing is not None and not force_reprocess:
            # Byte-identical to something we already ingested. This is the
            # common case for a re-run, and it is a no-op, not an error.
            log.info("ingest.duplicate", checksum=checksum, raw_import_id=str(existing.id))
            return ImportOutcome(
                raw_import_id=existing.id,
                status=ImportStatus.SKIPPED_DUPLICATE,
                correlation_id=correlation_id,
                duplicate_of=existing.id,
            )

        raw_import = existing or RawImport(
            organization_id=self.organization.id,
            provider=self.provider.name,
            import_type=payload.import_type,
            filename=payload.filename,
            checksum=checksum,
            byte_size=len(payload.data),
            correlation_id=correlation_id,
        )
        raw_import.status = ImportStatus.PROCESSING
        raw_import.started_at = started
        raw_import.correlation_id = correlation_id
        if existing is None:
            self.db.add(raw_import)
        self.db.flush()

        # Archive before interpreting: if parsing is wrong, the source survives.
        raw_import.object_key = self._archive(payload, checksum)

        outcome = ImportOutcome(
            raw_import_id=raw_import.id,
            status=ImportStatus.PROCESSING,
            correlation_id=correlation_id,
        )

        try:
            parsed = self.provider.parse(payload)
        except Exception as exc:
            log.exception("ingest.parse_failed", checksum=checksum)
            return self._fail(raw_import, outcome, f"parse failed: {exc}")

        outcome.rows_total = parsed.rows_total
        outcome.rows_accepted = parsed.rows_accepted
        outcome.rows_rejected = parsed.rows_rejected
        outcome.issues = list(parsed.issues)

        if not parsed.sessions:
            imports_repo.add_issues(self.db, raw_import.id, parsed.issues)
            return self._fail(raw_import, outcome, "no usable sessions were found in this payload")

        for parsed_session in parsed.sessions:
            self._ingest_session(parsed_session, raw_import, outcome)

        imports_repo.add_issues(self.db, raw_import.id, outcome.issues)
        return self._finish(raw_import, outcome, parsed)

    # -- per-session ----------------------------------------------------------

    def _ingest_session(
        self, parsed: ParsedSession, raw_import: RawImport, outcome: ImportOutcome
    ) -> None:
        session, created = sessions_repo.upsert(
            self.db,
            self.organization.id,
            self.provider.name,
            parsed.external_session_id,
            session_date=parsed.session_date,
            source_status=parsed.source_status,
            started_at=parsed.started_at,
            ended_at=parsed.ended_at,
            session_type=parsed.session_type,
            venue=parsed.venue,
            raw_import_id=raw_import.id,
            metadata=parsed.metadata,
        )
        if created:
            outcome.sessions_created += 1
        else:
            outcome.sessions_updated += 1

        resolved, unresolved, held_counts = self._resolve_players(parsed, raw_import)
        outcome.unresolved_players.extend(sorted(unresolved))
        outcome.issues.extend(
            unresolved_issue(external_id, held_counts.get(external_id, 0))
            for external_id in sorted(unresolved)
        )

        pitch_rows = []
        kept_pitch_ids: set[str] = set()
        for pitch in parsed.pitches:
            player_id = resolved.get(pitch.external_player_id)
            if player_id is None:
                continue
            kept_pitch_ids.add(pitch.external_event_id)
            pitch_rows.append(
                {
                    "id": uuid.uuid4(),
                    "organization_id": self.organization.id,
                    "session_id": session.id,
                    "player_id": player_id,
                    "external_event_id": pitch.external_event_id,
                    "pitch_number": pitch.pitch_number,
                    "event_at": pitch.event_at,
                    "pitch_type": pitch.pitch_type,
                    "auto_pitch_type": pitch.auto_pitch_type,
                    "pitch_call": pitch.pitch_call,
                    "is_strike": pitch.is_strike,
                    "velocity_mph": pitch.velocity_mph,
                    "spin_rate_rpm": pitch.spin_rate_rpm,
                    "spin_axis_deg": pitch.spin_axis_deg,
                    "horizontal_break_in": pitch.horizontal_break_in,
                    "vertical_break_in": pitch.vertical_break_in,
                    "release_height_ft": pitch.release_height_ft,
                    "release_side_ft": pitch.release_side_ft,
                    "extension_ft": pitch.extension_ft,
                    "plate_location_height_ft": pitch.plate_location_height_ft,
                    "plate_location_side_ft": pitch.plate_location_side_ft,
                    "vertical_approach_angle_deg": pitch.vertical_approach_angle_deg,
                    "horizontal_approach_angle_deg": pitch.horizontal_approach_angle_deg,
                    "training_context": pitch.training_context,
                    "source_status": session.source_status,
                    "raw_import_id": raw_import.id,
                }
            )

        hit_rows = []
        kept_hit_ids: set[str] = set()
        for hit in parsed.hits:
            player_id = resolved.get(hit.external_player_id)
            if player_id is None:
                continue
            kept_hit_ids.add(hit.external_event_id)
            hit_rows.append(
                {
                    "id": uuid.uuid4(),
                    "organization_id": self.organization.id,
                    "session_id": session.id,
                    "player_id": player_id,
                    "external_event_id": hit.external_event_id,
                    "swing_number": hit.swing_number,
                    "event_at": hit.event_at,
                    "exit_velocity_mph": hit.exit_velocity_mph,
                    "launch_angle_deg": hit.launch_angle_deg,
                    "launch_direction_deg": hit.launch_direction_deg,
                    "distance_ft": hit.distance_ft,
                    "hang_time_s": hit.hang_time_s,
                    "hit_spin_rate_rpm": hit.hit_spin_rate_rpm,
                    "contact_position_x_ft": hit.contact_position_x_ft,
                    "contact_position_y_ft": hit.contact_position_y_ft,
                    "contact_position_z_ft": hit.contact_position_z_ft,
                    "batted_ball_type": hit.batted_ball_type,
                    "training_context": hit.training_context,
                    "source_status": session.source_status,
                    "raw_import_id": raw_import.id,
                }
            )

        outcome.pitch_events += sessions_repo.upsert_pitch_events(self.db, pitch_rows)
        outcome.hit_events += sessions_repo.upsert_hit_events(self.db, hit_rows)

        # A clean payload describes a whole session, so anything it omits has
        # been removed at the source and must stop feeding metrics.
        #
        # Pruning is skipped whenever we cannot trust our own reading of the
        # file. If rows were rejected, or athletes are unmapped, an event is
        # missing from `kept_*_ids` because *we* failed to read it -- not
        # because the source corrected itself. Deleting real measurements on
        # that basis would silently destroy data, so an imperfect import only
        # ever adds and updates.
        if self._payload_is_authoritative(parsed, unresolved, outcome):
            outcome.events_pruned += sessions_repo.prune_events_not_in(
                self.db, session.id, kept_pitch_ids, kept_hit_ids
            )

        sessions_repo.link_hits_to_pitches(self.db, session.id)
        self.db.flush()

        metric_outcome = metrics_service.recalculate_session(self.db, self.organization.id, session)
        outcome.metric_observations += metric_outcome.observation_count

        record_outcome = records_service.recalculate_for_players(
            self.db,
            organization_id=self.organization.id,
            player_ids=list(metric_outcome.calculated),
        )
        outcome.new_personal_records += len(record_outcome.new_events)

        jobs = sync_service.queue_for_record_events(
            self.db, organization_id=self.organization.id, events=record_outcome.new_events
        )
        outcome.sync_jobs_queued += len(jobs)

        log.info(
            "ingest.session.done",
            external_session_id=parsed.external_session_id,
            session_id=str(session.id),
            created=created,
            source_status=session.source_status.value,
            pitches=len(pitch_rows),
            hits=len(hit_rows),
            unresolved=len(unresolved),
        )

    @staticmethod
    def _payload_is_authoritative(
        parsed: ParsedSession, unresolved: set[str], outcome: ImportOutcome
    ) -> bool:
        """Whether this payload may be treated as the complete session.

        Requires that every row parsed and every athlete resolved. Anything less
        makes absence ambiguous, and ambiguity must never delete measurements.
        """
        if unresolved:
            return False
        if outcome.rows_rejected > 0:
            return False
        return bool(parsed.pitches or parsed.hits)

    # -- identity -------------------------------------------------------------

    def _resolve_players(
        self, parsed: ParsedSession, raw_import: RawImport
    ) -> tuple[dict[str, uuid.UUID], set[str], dict[str, int]]:
        """Map vendor athlete ids to our players, by explicit mapping only.

        An unmapped athlete is queued for a human and their events are held
        back. Attaching data to a name-similar player would be worse than
        losing it: the coach would never know to look.
        """
        names: dict[str, str | None] = {}
        occurrences: dict[str, int] = {}
        for pitch in parsed.pitches:
            names.setdefault(pitch.external_player_id, pitch.external_player_name)
            occurrences[pitch.external_player_id] = occurrences.get(pitch.external_player_id, 0) + 1
        for hit in parsed.hits:
            names.setdefault(hit.external_player_id, hit.external_player_name)
            occurrences[hit.external_player_id] = occurrences.get(hit.external_player_id, 0) + 1

        resolved: dict[str, uuid.UUID] = {}
        unresolved: set[str] = set()

        for external_id, display_name in names.items():
            player = players_repo.find_by_external_identity(
                self.db, self.organization.id, self.provider.name, external_id
            )
            if player is not None:
                resolved[external_id] = player.id
                continue

            unresolved.add(external_id)
            players_repo.record_unresolved(
                self.db,
                self.organization.id,
                self.provider.name,
                external_id,
                display_name=display_name,
                occurrences=occurrences.get(external_id, 0),
                import_id=raw_import.id,
            )
            log.warning(
                "ingest.player_unresolved",
                external_id=external_id,
                display_name=display_name,
                events_held=occurrences.get(external_id, 0),
            )

        self.db.flush()
        return resolved, unresolved, occurrences

    # -- bookkeeping ----------------------------------------------------------

    def _archive(self, payload: SourcePayload, checksum: str) -> str:
        key = build_object_key(
            self.organization.slug, self.provider.name, checksum, payload.filename
        )
        self.object_store.put(key, payload.data, content_type="text/csv")
        return key

    def _fail(self, raw_import: RawImport, outcome: ImportOutcome, message: str) -> ImportOutcome:
        raw_import.status = ImportStatus.FAILED
        raw_import.error_message = message
        raw_import.completed_at = datetime.now(UTC)
        raw_import.rows_total = outcome.rows_total
        raw_import.rows_accepted = outcome.rows_accepted
        raw_import.rows_rejected = outcome.rows_rejected
        self.db.flush()
        outcome.status = ImportStatus.FAILED
        outcome.error_message = message
        log.error("ingest.failed", reason=message, raw_import_id=str(raw_import.id))
        return outcome

    def _finish(
        self, raw_import: RawImport, outcome: ImportOutcome, parsed: ParseResult
    ) -> ImportOutcome:
        has_problems = bool(outcome.rows_rejected or outcome.unresolved_players)
        status = ImportStatus.PARTIAL if has_problems else ImportStatus.SUCCESS

        raw_import.status = status
        raw_import.completed_at = datetime.now(UTC)
        raw_import.rows_total = outcome.rows_total
        raw_import.rows_accepted = outcome.rows_accepted
        raw_import.rows_rejected = outcome.rows_rejected
        raw_import.source_status = (
            SourceStatus.VERIFIED
            if parsed.sessions
            and all(s.source_status is SourceStatus.VERIFIED for s in parsed.sessions)
            else SourceStatus.PRELIMINARY
        )
        raw_import.import_metadata = {
            **raw_import.import_metadata,
            "sessions_created": outcome.sessions_created,
            "sessions_updated": outcome.sessions_updated,
            "pitch_events": outcome.pitch_events,
            "hit_events": outcome.hit_events,
            "events_pruned": outcome.events_pruned,
            "metric_observations": outcome.metric_observations,
            "new_personal_records": outcome.new_personal_records,
            "unresolved_players": outcome.unresolved_players,
        }
        self.db.flush()

        outcome.status = status
        duration = (
            (raw_import.completed_at - raw_import.started_at).total_seconds()
            if raw_import.started_at
            else None
        )
        log.info(
            "ingest.completed",
            raw_import_id=str(raw_import.id),
            status=status.value,
            duration_s=duration,
            rows_total=outcome.rows_total,
            rows_rejected=outcome.rows_rejected,
            new_personal_records=outcome.new_personal_records,
        )
        return outcome


def unresolved_issue(external_id: str, count: int) -> RowIssue:
    """Issue row describing an athlete whose data is being held back."""
    return RowIssue(
        row_number=0,
        code=ImportIssueCode.PLAYER_UNRESOLVED,
        message=f"no player mapping for external id {external_id!r}; {count} events held",
        context={"external_id": external_id, "events_held": count},
    )
