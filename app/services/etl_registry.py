from __future__ import annotations

from app.services.etl_catalog import build_job_catalog
from app.services.etl_definition import ETLJobDefinition


JOBS: dict[str, ETLJobDefinition] = build_job_catalog()


def get_job(job_id: str) -> ETLJobDefinition | None:
    return JOBS.get(job_id)


def list_jobs() -> list[ETLJobDefinition]:
    return list(JOBS.values())
