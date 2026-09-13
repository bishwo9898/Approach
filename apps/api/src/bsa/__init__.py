"""Baseball player analytics platform.

Layering (dependencies point downward only):

    api        -- FastAPI routers, request/response schemas, auth dependencies
    services   -- application services, transaction boundaries, orchestration
    domain     -- pure business logic: units, metric engine, PR engine. No I/O.
    db         -- SQLAlchemy models and repositories
    integrations -- vendor adapters (TrackMan, Futures, object store, auth)
    core       -- configuration, logging, errors

`domain` imports nothing from `db`, `api`, or `integrations`.
"""

__version__ = "0.1.0"
