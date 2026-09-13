"""Metric configuration endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from bsa.api import mappers, schemas
from bsa.api.deps import CurrentPrincipal, DbSession
from bsa.db.repositories import metrics as metrics_repo

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("", response_model=list[schemas.MetricDefinitionOut])
def list_metrics(
    db: DbSession, principal: CurrentPrincipal, enabled_only: bool = True
) -> list[schemas.MetricDefinitionOut]:
    """The organization's metric catalog.

    The dashboard reads this rather than hardcoding metric names, so changing
    the metric set is a data change, not a frontend deployment.
    """
    return [
        mappers.metric_definition(d)
        for d in metrics_repo.list_definitions(
            db, principal.organization_id, enabled_only=enabled_only
        )
    ]
