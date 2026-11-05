from __future__ import annotations

from datetime import datetime
import json
import time
from typing import Any

import mysql.connector

from app.core.db import db_connection
from app.services.etl.definition import ETLJobDefinition
from app.services.utils.date_service import get_bogota_now


STATUS_QUEUED = "queued"
STATUS_RUNNING = "running"
STATUS_SUCCESS = "success"
STATUS_FAILED = "failed"
STATUS_CANCELLED = "cancelado"

# Errores de bloqueo que MariaDB pide reintentar ("try restarting transaction").
_RETRYABLE_LOCK_ERRNOS = {1213, 1205}  # deadlock, lock wait timeout
_WRITE_ATTEMPTS = 4
_WRITE_RETRY_BASE_SECONDS = 0.2


def _execute_write(sql: str, params: tuple[Any, ...]) -> int:
    """Ejecuta un UPDATE sobre etl_job_runs reintentando si hay deadlock.

    Sin esto, un choque con el barrido de corridas colgadas (cada minuto) hacia
    fallar el UPDATE que marca 'success' y el job quedaba como fallido aunque
    ya habia escrito todos sus archivos y tablas.
    """
    for attempt in range(1, _WRITE_ATTEMPTS + 1):
        with db_connection() as connection:
            cursor = connection.cursor()
            try:
                cursor.execute(sql, params)
                affected = int(cursor.rowcount or 0)
                connection.commit()
                return affected
            except mysql.connector.Error as exc:
                connection.rollback()
                if exc.errno not in _RETRYABLE_LOCK_ERRNOS or attempt == _WRITE_ATTEMPTS:
                    raise
            finally:
                cursor.close()
        time.sleep(_WRITE_RETRY_BASE_SECONDS * attempt)
    return 0


def _column_exists(table_name: str, column_name: str) -> bool:
    with db_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = %s
              AND COLUMN_NAME = %s
            """,
            (table_name, column_name),
        )
        row = cursor.fetchone()
        cursor.close()
    return bool(row and int(row[0] or 0) > 0)


def ensure_etl_tables() -> None:
    with db_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS etl_jobs (
                job_id VARCHAR(80) PRIMARY KEY,
                name VARCHAR(150) NOT NULL,
                description TEXT NULL,
                allows_parallel TINYINT(1) NOT NULL DEFAULT 1,
                timeout_seconds INT NOT NULL DEFAULT 900,
                is_active TINYINT(1) NOT NULL DEFAULT 1,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS etl_job_runs (
                run_id BIGINT AUTO_INCREMENT PRIMARY KEY,
                job_id VARCHAR(80) NOT NULL,
                status VARCHAR(20) NOT NULL,
                triggered_by VARCHAR(80) NOT NULL DEFAULT 'web',
                params_json LONGTEXT NULL,
                started_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                finished_at DATETIME NULL,
                duration_seconds INT NULL,
                output_path TEXT NULL,
                error_message TEXT NULL,
                INDEX idx_etl_runs_job_started (job_id, started_at),
                INDEX idx_etl_runs_status (status)
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS etl_job_last_params (
                job_id VARCHAR(80) PRIMARY KEY,
                params_json LONGTEXT NULL,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            )
            """
        )

        # Compatibilidad para tablas existentes creadas antes del soporte de params_json.
        if not _column_exists("etl_job_runs", "params_json"):
            cursor.execute("ALTER TABLE etl_job_runs ADD COLUMN params_json LONGTEXT NULL")
        connection.commit()
        cursor.close()


def upsert_job_definition(job: ETLJobDefinition) -> None:
    with db_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO etl_jobs (job_id, name, description, allows_parallel, timeout_seconds, is_active)
            VALUES (%s, %s, %s, %s, %s, 1)
            ON DUPLICATE KEY UPDATE
                name = VALUES(name),
                description = VALUES(description),
                allows_parallel = VALUES(allows_parallel),
                timeout_seconds = VALUES(timeout_seconds),
                is_active = 1
            """,
            (
                job.job_id,
                job.name,
                job.description,
                1 if job.allows_parallel else 0,
                job.timeout_seconds,
            ),
        )
        connection.commit()
        cursor.close()


def list_jobs_with_state() -> list[dict[str, Any]]:
    with db_connection() as connection:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT
                j.job_id,
                j.name,
                j.description,
                j.allows_parallel,
                j.timeout_seconds,
                j.is_active,
                j.updated_at,
                r.status AS last_status,
                r.started_at AS last_started_at,
                r.run_id AS last_run_id,
                r.error_message AS last_error_message
            FROM etl_jobs AS j
            LEFT JOIN etl_job_runs AS r
                ON r.run_id = (
                    SELECT MAX(r2.run_id)
                    FROM etl_job_runs AS r2
                    WHERE r2.job_id = j.job_id
                )
            WHERE j.is_active = 1
            ORDER BY j.name
            """
        )
        rows = cursor.fetchall()
        cursor.close()
    return rows


def create_run(job_id: str, triggered_by: str = "web") -> int:
    return create_run_with_params(job_id=job_id, triggered_by=triggered_by, params=None)


def create_run_with_params(
    job_id: str,
    triggered_by: str = "web",
    params: dict[str, Any] | None = None,
) -> int:
    params_json = json.dumps(params or {}, ensure_ascii=True)
    with db_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO etl_job_runs (job_id, status, triggered_by, params_json)
            VALUES (%s, %s, %s, %s)
            """,
            (job_id, STATUS_QUEUED, triggered_by, params_json),
        )
        connection.commit()
        run_id = cursor.lastrowid
        cursor.close()
    return int(run_id)


def upsert_last_job_params(job_id: str, params: dict[str, Any] | None) -> None:
    payload = json.dumps(params or {}, ensure_ascii=True)
    with db_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO etl_job_last_params (job_id, params_json)
            VALUES (%s, %s)
            ON DUPLICATE KEY UPDATE params_json = VALUES(params_json)
            """,
            (job_id, payload),
        )
        connection.commit()
        cursor.close()


def get_last_job_params(job_id: str) -> dict[str, Any]:
    with db_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT params_json
            FROM etl_job_last_params
            WHERE job_id = %s
            """,
            (job_id,),
        )
        row = cursor.fetchone()
        cursor.close()

    if not row:
        return {}

    raw = row[0]
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8", errors="ignore")
    if isinstance(raw, str):
        try:
            value = json.loads(raw)
            if isinstance(value, dict):
                return value
        except Exception:  # noqa: BLE001
            return {}
    return {}


def update_run_started(run_id: int) -> None:
    _execute_write(
        """
        UPDATE etl_job_runs
        SET status = %s, started_at = %s
        WHERE run_id = %s
        """,
        (STATUS_RUNNING, get_bogota_now(), run_id),
    )


def update_run_success(run_id: int, output_path: str | None) -> None:
    """Marca la corrida como exitosa, salvo que ya haya sido cancelada por el usuario."""
    now = get_bogota_now()
    _execute_write(
        """
        UPDATE etl_job_runs
        SET
            status = %s,
            finished_at = %s,
            duration_seconds = TIMESTAMPDIFF(SECOND, started_at, %s),
            output_path = %s,
            error_message = NULL
        WHERE run_id = %s AND status != %s
        """,
        (STATUS_SUCCESS, now, now, output_path, run_id, STATUS_CANCELLED),
    )


def update_run_failed(run_id: int, error_message: str) -> None:
    """Marca la corrida como fallida, salvo que ya haya sido cancelada por el usuario."""
    now = get_bogota_now()
    _execute_write(
        """
        UPDATE etl_job_runs
        SET
            status = %s,
            finished_at = %s,
            duration_seconds = TIMESTAMPDIFF(SECOND, started_at, %s),
            error_message = %s
        WHERE run_id = %s AND status != %s
        """,
        (STATUS_FAILED, now, now, error_message[:2000], run_id, STATUS_CANCELLED),
    )


def update_run_cancelled(run_id: int, message: str) -> bool:
    """Marca una corrida 'queued'/'running' como cancelada. Devuelve False si ya habia terminado."""
    now = get_bogota_now()
    affected = _execute_write(
        """
        UPDATE etl_job_runs
        SET
            status = %s,
            finished_at = %s,
            duration_seconds = TIMESTAMPDIFF(SECOND, started_at, %s),
            error_message = %s
        WHERE run_id = %s AND status IN (%s, %s)
        """,
        (STATUS_CANCELLED, now, now, message[:2000], run_id, STATUS_QUEUED, STATUS_RUNNING),
    )
    return affected > 0


def count_by_status() -> dict[str, int]:
    """Devuelve conteos KPI para el dashboard.

    queued/running: all-time activos.
    success/failed: últimos 7 días.
    """
    with db_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT
                SUM(status = 'queued')  AS queued,
                SUM(status = 'running') AS running,
                SUM(status = 'success' AND started_at >= DATE_SUB(NOW(), INTERVAL 7 DAY)) AS success,
                SUM(status = 'failed'  AND started_at >= DATE_SUB(NOW(), INTERVAL 7 DAY)) AS failed
            FROM etl_job_runs
            """
        )
        row = cursor.fetchone()
        cursor.close()
    return {
        "queued":  int(row[0] or 0),
        "running": int(row[1] or 0),
        "success": int(row[2] or 0),
        "failed":  int(row[3] or 0),
    }


def count_running_jobs(job_id: str) -> int:
    with db_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM etl_job_runs
            WHERE job_id = %s AND status IN (%s, %s)
            """,
            (job_id, STATUS_QUEUED, STATUS_RUNNING),
        )
        row = cursor.fetchone()
        cursor.close()
    return int(row[0] if row else 0)


def _fail_runs_by_id(stale: list[tuple[int, int]], now: datetime) -> int:
    """Marca como fallidas las corridas dadas como (run_id, timeout_seconds).

    Se actualiza por llave primaria (run_id), igual que update_run_success. Un
    UPDATE filtrado por status bloqueaba primero el indice idx_etl_runs_status y
    luego la fila: orden inverso al de update_run_success, lo que producia
    deadlocks cuando ambos coincidian en el mismo segundo. Las condiciones se
    repiten en el UPDATE por si la corrida termino entre el SELECT y el UPDATE.
    """
    affected_rows = 0
    for run_id, timeout_seconds in stale:
        timeout_value = max(int(timeout_seconds or 0), 1)
        affected_rows += _execute_write(
            """
            UPDATE etl_job_runs
            SET
                status = %s,
                finished_at = %s,
                duration_seconds = TIMESTAMPDIFF(SECOND, started_at, %s),
                error_message = %s
            WHERE run_id = %s
              AND status IN (%s, %s)
              AND started_at <= DATE_SUB(%s, INTERVAL %s SECOND)
            """,
            (
                STATUS_FAILED,
                now,
                now,
                f"Timeout detectado automaticamente ({timeout_value} s).",
                run_id,
                STATUS_QUEUED,
                STATUS_RUNNING,
                now,
                timeout_value,
            ),
        )
    return affected_rows


def fail_stale_runs(job_id: str, timeout_seconds: int) -> int:
    """Marca como fallidas corridas queued/running que excedieron su timeout."""
    now = get_bogota_now()
    timeout_value = max(int(timeout_seconds or 0), 1)

    # Lectura sin bloqueos: solo identifica las candidatas.
    with db_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT run_id
            FROM etl_job_runs
            WHERE job_id = %s
              AND status IN (%s, %s)
              AND started_at <= DATE_SUB(%s, INTERVAL %s SECOND)
            """,
            (job_id, STATUS_QUEUED, STATUS_RUNNING, now, timeout_value),
        )
        stale = [(int(row[0]), timeout_value) for row in cursor.fetchall()]
        cursor.close()

    return _fail_runs_by_id(stale, now)


def fail_all_stale_runs() -> int:
    """Marca como fallidas todas las corridas queued/running que excedieron el timeout configurado del job."""
    now = get_bogota_now()

    # Lectura sin bloqueos: solo identifica las candidatas.
    with db_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT r.run_id, j.timeout_seconds
            FROM etl_job_runs AS r
            JOIN etl_jobs AS j
              ON j.job_id = r.job_id
            WHERE r.status IN (%s, %s)
              AND r.started_at <= DATE_SUB(%s, INTERVAL GREATEST(j.timeout_seconds, 1) SECOND)
            """,
            (STATUS_QUEUED, STATUS_RUNNING, now),
        )
        stale = [(int(row[0]), int(row[1] or 0)) for row in cursor.fetchall()]
        cursor.close()

    return _fail_runs_by_id(stale, now)


def list_recent_runs(limit: int = 50) -> list[dict[str, Any]]:
    with db_connection() as connection:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT
                run_id,
                job_id,
                status,
                triggered_by,
                started_at,
                finished_at,
                duration_seconds,
                params_json,
                output_path,
                error_message
            FROM etl_job_runs
            ORDER BY run_id DESC
            LIMIT %s
            """,
            (limit,),
        )
        rows = cursor.fetchall()
        cursor.close()
    return rows
