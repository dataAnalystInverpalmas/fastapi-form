from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
import inspect
from typing import Any

from app.core.settings import settings
from app.services.etl import repository as etl_repository
from app.services.etl.registry import get_job, list_jobs


_executor: ThreadPoolExecutor | None = None


def _executor_instance() -> ThreadPoolExecutor:
    global _executor
    if _executor is None:
        _executor = ThreadPoolExecutor(max_workers=settings.ETL_MAX_WORKERS)
    return _executor


def bootstrap_jobs() -> None:
    etl_repository.ensure_etl_tables()
    jobs = list_jobs()
    for job in jobs:
        etl_repository.upsert_job_definition(job)
    for job in jobs:
        etl_repository.fail_stale_runs(job_id=job.job_id, timeout_seconds=job.timeout_seconds)


def _invoke_runner(job_runner, params: dict[str, Any] | None) -> str:
    signature = inspect.signature(job_runner)
    accepts_params = len(signature.parameters) > 0
    if accepts_params:
        return job_runner(params or {})
    return job_runner()


def _run_job(run_id: int, job_id: str, params: dict[str, Any] | None = None) -> None:
    job = get_job(job_id)
    if job is None:
        etl_repository.update_run_failed(run_id, f"Job desconocido: {job_id}")
        return

    etl_repository.update_run_started(run_id)
    runner_executor = ThreadPoolExecutor(max_workers=1)
    runner_future = runner_executor.submit(_invoke_runner, job.runner, params)

    try:
        timeout_seconds = max(int(job.timeout_seconds or 0), 1)
        output_path = runner_future.result(timeout=timeout_seconds)
        etl_repository.update_run_success(run_id, output_path=output_path)
    except FuturesTimeoutError:
        runner_future.cancel()
        etl_repository.update_run_failed(
            run_id,
            f"Job '{job_id}' excedio el timeout de {job.timeout_seconds} segundos.",
        )
    except Exception as exc:  # noqa: BLE001
        etl_repository.update_run_failed(run_id, str(exc))
    finally:
        runner_executor.shutdown(wait=False, cancel_futures=True)


def start_job(
    job_id: str,
    triggered_by: str = "web",
    params: dict[str, Any] | None = None,
) -> int:
    job = get_job(job_id)
    if job is None:
        raise ValueError(f"No existe el job '{job_id}'.")

    etl_repository.fail_stale_runs(job_id=job_id, timeout_seconds=job.timeout_seconds)

    if not job.allows_parallel and etl_repository.count_running_jobs(job_id) > 0:
        raise RuntimeError(f"El job '{job_id}' ya tiene una corrida en progreso.")

    run_id = etl_repository.create_run_with_params(
        job_id=job_id,
        triggered_by=triggered_by,
        params=params,
    )
    etl_repository.upsert_last_job_params(job_id=job_id, params=params)
    _executor_instance().submit(_run_job, run_id, job_id, params)
    return run_id
