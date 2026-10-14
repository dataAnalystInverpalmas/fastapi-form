"""Conexiones a la base de datos con connection pool."""
from __future__ import annotations

import time
from contextlib import contextmanager

import mysql.connector.errors
import mysql.connector.pooling

from app.core.settings import settings

_POOL_WAIT_SECONDS = 60
_POOL_RETRY_INTERVAL_SECONDS = 0.2

_pool: mysql.connector.pooling.MySQLConnectionPool | None = None


def _get_pool() -> mysql.connector.pooling.MySQLConnectionPool:
    global _pool
    if _pool is None:
        _pool = mysql.connector.pooling.MySQLConnectionPool(
            pool_name="fastapi_pool",
            pool_size=5,
            pool_reset_session=True,
            host=settings.DB_HOST,
            port=settings.DB_PORT,
            user=settings.DB_USER,
            password=settings.DB_PASSWORD,
            database=settings.DB_NAME,
        )
    return _pool


def _get_connection_waiting():
    # MySQLConnectionPool falla de inmediato si no hay conexiones libres. Varios
    # jobs arrancan a la vez (cron de las 10:00), asi que se espera a que se
    # libere una en vez de fallar y perder la corrida sin dejar registro.
    deadline = time.monotonic() + _POOL_WAIT_SECONDS
    while True:
        try:
            return _get_pool().get_connection()
        except mysql.connector.errors.PoolError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(_POOL_RETRY_INTERVAL_SECONDS)


@contextmanager
def db_connection():
    connection = _get_connection_waiting()
    try:
        yield connection
    finally:
        connection.close()  # Devuelve la conexión al pool
