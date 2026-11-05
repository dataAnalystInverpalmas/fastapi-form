import unittest
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import mysql.connector

from app.services.etl import repository


def _fake_db(cursors):
    """db_connection falso que entrega un cursor distinto en cada uso."""
    connections = []

    @contextmanager
    def fake_db_connection():
        connection = MagicMock()
        connection.cursor.return_value = cursors.pop(0)
        connections.append(connection)
        yield connection

    return fake_db_connection, connections


def _deadlock():
    return mysql.connector.errors.InternalError(
        msg="Deadlock found when trying to get lock; try restarting transaction",
        errno=1213,
    )


class ExecuteWriteRetryTest(unittest.TestCase):
    def setUp(self):
        patcher = patch.object(repository.time, "sleep")
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_reintenta_tras_deadlock_y_marca_success(self):
        failing = MagicMock()
        failing.execute.side_effect = _deadlock()
        ok = MagicMock()
        ok.rowcount = 1
        fake, connections = _fake_db([failing, ok])

        with patch.object(repository, "db_connection", fake):
            repository.update_run_success(1923, output_path="out.csv")

        self.assertEqual(len(connections), 2)
        connections[0].rollback.assert_called_once()
        connections[1].commit.assert_called_once()

    def test_no_reintenta_otros_errores(self):
        failing = MagicMock()
        failing.execute.side_effect = mysql.connector.errors.ProgrammingError(msg="x", errno=1064)
        fake, connections = _fake_db([failing])

        with patch.object(repository, "db_connection", fake):
            with self.assertRaises(mysql.connector.Error):
                repository.update_run_failed(1, "boom")

        self.assertEqual(len(connections), 1)

    def test_se_rinde_tras_varios_deadlocks(self):
        cursors = []
        for _ in range(repository._WRITE_ATTEMPTS):
            cursor = MagicMock()
            cursor.execute.side_effect = _deadlock()
            cursors.append(cursor)
        fake, connections = _fake_db(cursors)

        with patch.object(repository, "db_connection", fake):
            with self.assertRaises(mysql.connector.Error):
                repository.update_run_success(1, None)

        self.assertEqual(len(connections), repository._WRITE_ATTEMPTS)


class FailStaleRunsTest(unittest.TestCase):
    def test_barrido_actualiza_por_run_id(self):
        select_cursor = MagicMock()
        select_cursor.fetchall.return_value = [(10, 2400), (11, 900)]
        update_a = MagicMock(rowcount=1)
        update_b = MagicMock(rowcount=0)  # termino entre el SELECT y el UPDATE
        fake, _ = _fake_db([select_cursor, update_a, update_b])

        with patch.object(repository, "db_connection", fake):
            affected = repository.fail_all_stale_runs()

        self.assertEqual(affected, 1)
        for cursor, run_id in ((update_a, 10), (update_b, 11)):
            sql, params = cursor.execute.call_args.args
            self.assertIn("WHERE run_id = %s", sql)
            self.assertEqual(params[4], run_id)


if __name__ == "__main__":
    unittest.main()
