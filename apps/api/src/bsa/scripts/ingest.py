"""CLI for ingesting a TrackMan CSV.

The same entry point a Cloud Run Job will call on a schedule once automated
retrieval exists. Everything it does goes through `IngestionService`, so a
manual import and an automated one follow exactly the same path.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlalchemy import select

from bsa.core.config import get_settings
from bsa.core.logging import configure_logging
from bsa.db.models import Organization
from bsa.db.session import session_scope
from bsa.integrations.storage import get_object_store
from bsa.integrations.trackman import get_trackman_provider
from bsa.integrations.trackman.schema import SourcePayload
from bsa.services.ingestion import IngestionService


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest a TrackMan CSV export.")
    parser.add_argument("path", type=Path, help="CSV file to ingest")
    parser.add_argument("--org", default="approach-baseball", help="organization slug")
    parser.add_argument(
        "--force",
        action="store_true",
        help="reprocess even if these exact bytes were already ingested",
    )
    args = parser.parse_args()

    settings = get_settings()
    configure_logging(settings.log_level)

    if not args.path.exists():
        print(f"error: {args.path} does not exist", file=sys.stderr)
        return 2

    with session_scope() as db:
        org = db.scalars(select(Organization).where(Organization.slug == args.org)).first()
        if org is None:
            print(
                f"error: no organization with slug {args.org!r}. Run the seed first.",
                file=sys.stderr,
            )
            return 2

        service = IngestionService(
            db, org, get_trackman_provider(settings), get_object_store(settings)
        )
        outcome = service.ingest(
            SourcePayload(
                data=args.path.read_bytes(),
                filename=args.path.name,
                import_type="csv_upload",
            ),
            force_reprocess=args.force,
        )

    print(f"\nimport {outcome.raw_import_id}  status={outcome.status.value}")
    if outcome.is_duplicate:
        print("  these exact bytes were already ingested; nothing changed.")
        return 0
    print(f"  rows              {outcome.rows_accepted}/{outcome.rows_total} accepted")
    print(
        f"  sessions          {outcome.sessions_created} created, "
        f"{outcome.sessions_updated} updated"
    )
    print(f"  events            {outcome.pitch_events} pitches, {outcome.hit_events} hits")
    print(f"  observations      {outcome.metric_observations}")
    print(f"  new PRs           {outcome.new_personal_records}")
    print(f"  Futures queued    {outcome.sync_jobs_queued}")
    if outcome.unresolved_players:
        print(f"  UNRESOLVED        {', '.join(outcome.unresolved_players)}")
    if outcome.error_message:
        print(f"  error             {outcome.error_message}")
    return 0 if outcome.status.value != "FAILED" else 1


if __name__ == "__main__":
    sys.exit(main())
