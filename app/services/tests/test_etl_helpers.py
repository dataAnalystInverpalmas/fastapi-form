import unittest
from datetime import date
from unittest.mock import MagicMock, patch

import pandas as pd

from app.services.etl.helpers import save_snapshot


class SaveSnapshotTests(unittest.TestCase):
    @patch("app.services.etl.helpers.dataframe_to_sql")
    @patch("app.services.etl.helpers.db_connection")
    def test_save_snapshot_deletes_same_date_rows_then_appends_with_date_column(
        self, mock_db_connection, mock_dataframe_to_sql
    ) -> None:
        mock_cursor = MagicMock()
        mock_connection = MagicMock()
        mock_connection.cursor.return_value = mock_cursor
        mock_db_connection.return_value.__enter__.return_value = mock_connection

        df = pd.DataFrame({"finca": ["001"], "valor": [1.5]})
        snapshot_date = date(2026, 9, 14)

        save_snapshot(df, "tabla_historico", "fecha_corte", snapshot_date)

        mock_cursor.execute.assert_called_once_with(
            "DELETE FROM `tabla_historico` WHERE `fecha_corte` = %s",
            (snapshot_date,),
        )
        mock_connection.commit.assert_called_once()

        mock_dataframe_to_sql.assert_called_once()
        saved_df, table_name = mock_dataframe_to_sql.call_args[0]
        self.assertEqual(table_name, "tabla_historico")
        self.assertEqual(list(saved_df.columns)[0], "fecha_corte")
        self.assertEqual(saved_df.loc[0, "fecha_corte"], snapshot_date)
        self.assertEqual(saved_df.loc[0, "finca"], "001")
        # El DataFrame original no se muta.
        self.assertNotIn("fecha_corte", df.columns)

    @patch("app.services.etl.helpers.dataframe_to_sql")
    @patch("app.services.etl.helpers.db_connection")
    def test_save_snapshot_ignores_missing_table_error(
        self, mock_db_connection, mock_dataframe_to_sql
    ) -> None:
        import mysql.connector

        mock_cursor = MagicMock()
        mock_cursor.execute.side_effect = mysql.connector.errors.ProgrammingError(errno=1146)
        mock_connection = MagicMock()
        mock_connection.cursor.return_value = mock_cursor
        mock_db_connection.return_value.__enter__.return_value = mock_connection

        df = pd.DataFrame({"finca": ["001"]})
        save_snapshot(df, "tabla_nueva", "fecha_corte", date(2026, 9, 14))

        mock_dataframe_to_sql.assert_called_once()

    @patch("app.services.etl.helpers.dataframe_to_sql")
    @patch("app.services.etl.helpers.db_connection")
    def test_save_snapshot_reraises_unexpected_db_errors(
        self, mock_db_connection, mock_dataframe_to_sql
    ) -> None:
        import mysql.connector

        mock_cursor = MagicMock()
        mock_cursor.execute.side_effect = mysql.connector.errors.ProgrammingError(errno=1064)
        mock_connection = MagicMock()
        mock_connection.cursor.return_value = mock_cursor
        mock_db_connection.return_value.__enter__.return_value = mock_connection

        df = pd.DataFrame({"finca": ["001"]})
        with self.assertRaises(mysql.connector.errors.ProgrammingError):
            save_snapshot(df, "tabla_nueva", "fecha_corte", date(2026, 9, 14))

        mock_dataframe_to_sql.assert_not_called()


if __name__ == "__main__":
    unittest.main()
