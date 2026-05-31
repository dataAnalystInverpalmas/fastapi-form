"""Conexiones a la base de datos con connection pool."""
from __future__ import annotations

from contextlib import contextmanager

import mysql.connector.pooling

from app.core.settings import settings

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


@contextmanager
def db_connection():
    connection = _get_pool().get_connection()
    try:
        yield connection
    finally:
        connection.close()  # Devuelve la conexión al pool
