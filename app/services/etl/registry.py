from __future__ import annotations

from app.services.etl.catalog import build_job_catalog
from app.services.etl.definition import ETLJobDefinition


_JOBS: dict[str, ETLJobDefinition] | None = None


def _get_registry() -> dict[str, ETLJobDefinition]:
    global _JOBS
    if _JOBS is None:
        _JOBS = build_job_catalog()
    return _JOBS


def get_job(job_id: str) -> ETLJobDefinition | None:
    return _get_registry().get(job_id)


def list_jobs() -> list[ETLJobDefinition]:
    return list(_get_registry().values())
