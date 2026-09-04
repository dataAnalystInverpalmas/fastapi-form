import os
import unittest
from unittest.mock import patch

from app.services.utils.dbf_reader import normalize_path


class NormalizePathTests(unittest.TestCase):
    def test_normalize_path_uses_container_mount_for_unc_paths(self) -> None:
        with patch.dict(os.environ, {"APP_ENV": "docker"}, clear=False):
            with patch("app.services.utils.dbf_reader.os.path.exists", side_effect=lambda path: path in {"/mnt/smb/produc", "/mnt/smb/produc/tabla.dbf"}):
                self.assertEqual(
                    normalize_path(r"\\172.10.18.2\produc\tabla.dbf"),
                    "/mnt/smb/produc/tabla.dbf",
                )


if __name__ == "__main__":
    unittest.main()
