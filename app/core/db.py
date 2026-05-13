"""Conexiones a la base de datos."""
from __future__ import annotations

from contextlib import contextmanager

import mysql.connector

from app.core.settings import settings


def get_connection() -> mysql.connector.MySQLConnection:
    return mysql.connector.connect(
        host=settings.DB_HOST,
        port=settings.DB_PORT,
        user=settings.DB_USER,
        password=settings.DB_PASSWORD,
        database=settings.DB_NAME,
    )


@contextmanager
def db_connection() -> mysql.connector.MySQLConnection:
    connection = get_connection()
    try:
        yield connection
    finally:
        if connection.is_connected():
            connection.close()
