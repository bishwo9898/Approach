"""All ORM models.

Imported as a unit so Alembic autogenerate and `Base.metadata.create_all` see
every table regardless of import order.
"""

from bsa.db.models.audit import AuditLog
from bsa.db.models.events import HitEvent, PitchEvent
from bsa.db.models.ingest import ImportIssue, RawImport, TrainingSession
from bsa.db.models.metrics import MetricDefinition, MetricObservation
from bsa.db.models.org import Organization, User
from bsa.db.models.player import ExternalPlayerIdentity, IdentityResolutionItem, Player
from bsa.db.models.records import PersonalRecord, PersonalRecordEvent
from bsa.db.models.sync import ExternalMetricMapping, SyncJob
from bsa.db.models.video import SessionVideo

__all__ = [
    "AuditLog",
    "ExternalMetricMapping",
    "ExternalPlayerIdentity",
    "HitEvent",
    "IdentityResolutionItem",
    "ImportIssue",
    "MetricDefinition",
    "MetricObservation",
    "Organization",
    "PersonalRecord",
    "PersonalRecordEvent",
    "PitchEvent",
    "Player",
    "RawImport",
    "SessionVideo",
    "SyncJob",
    "TrainingSession",
    "User",
]
