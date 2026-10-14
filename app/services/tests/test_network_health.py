import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.services.utils.network_health import check_all_shares, is_mounted


def docker_runtime():
    """check_all_shares revisa montajes solo en el contenedor."""
    return patch("app.services.utils.network_health.is_docker_runtime", return_value=True)


def fake_filesystem(mounted: set[str], existing: set[str] | None = None):
    """Simula un contenedor donde solo `mounted` son montajes activos.

    `existing` permite un directorio que existe pero sin share montado (el
    caso tipico de un mount que fallo: entrypoint.sh creo la carpeta vacia).
    """
    existing_paths = (existing or set()) | mounted

    def _exists(self) -> bool:
        return self.as_posix() in existing_paths

    def _run(args, **kwargs):
        path = args[-1].replace("\\", "/")
        return SimpleNamespace(returncode=0 if path in mounted else 1)

    return patch("pathlib.Path.exists", autospec=True, side_effect=_exists), patch(
        "app.services.utils.network_health.subprocess.run", side_effect=_run
    )


class IsMountedTests(unittest.TestCase):
    def test_reports_mounted_share(self) -> None:
        exists_patch, run_patch = fake_filesystem({"/mnt/smb/produc"})
        with exists_patch, run_patch:
            ok, message = is_mounted("/mnt/smb/produc")
        self.assertTrue(ok)
        self.assertIn("/mnt/smb/produc", message)

    def test_reports_missing_directory(self) -> None:
        exists_patch, run_patch = fake_filesystem(set())
        with exists_patch, run_patch:
            ok, message = is_mounted("/mnt/smb/Usuarios")
        self.assertFalse(ok)
        self.assertIn("No existe", message)

    def test_reports_empty_directory_without_mount(self) -> None:
        # entrypoint.sh crea la carpeta antes de montar: si el mount falla, el
        # directorio existe vacio y eso NO debe contar como montado.
        exists_patch, run_patch = fake_filesystem(set(), existing={"/mnt/smb/Usuarios"})
        with exists_patch, run_patch:
            ok, message = is_mounted("/mnt/smb/Usuarios")
        self.assertFalse(ok)
        self.assertIn("no hay un share montado", message)


class CheckAllSharesTests(unittest.TestCase):
    def test_all_shares_mounted(self) -> None:
        exists_patch, run_patch = fake_filesystem(
            {"/mnt/smb/produc", "/mnt/smb/Usuarios", "/mnt/smb/newfact"}
        )
        with docker_runtime(), exists_patch, run_patch:
            todos_ok, detalle = check_all_shares()

        self.assertTrue(todos_ok)
        self.assertEqual([item["share"] for item in detalle], ["produc", "Usuarios", "newfact"])
        self.assertTrue(all(item["ok"] for item in detalle))

    def test_identifies_which_share_is_missing(self) -> None:
        # Este es el caso que antes pasaba desapercibido: produc montado y
        # Usuarios (41 de las rutas de settings) sin montar.
        exists_patch, run_patch = fake_filesystem({"/mnt/smb/produc", "/mnt/smb/newfact"})
        with docker_runtime(), exists_patch, run_patch:
            todos_ok, detalle = check_all_shares()

        self.assertFalse(todos_ok)
        faltantes = [item["share"] for item in detalle if not item["ok"]]
        self.assertEqual(faltantes, ["Usuarios"])

    def test_outside_docker_checks_unc_paths_not_linux_mounts(self) -> None:
        # Corriendo en Windows no hay nada montado: se llega a los shares
        # directo por UNC. Revisar /mnt/smb alli daba siempre "degraded" en
        # una instalacion sana.
        with patch("app.services.utils.network_health.is_docker_runtime", return_value=False), patch(
            "pathlib.Path.exists", autospec=True, side_effect=lambda self: True
        ):
            todos_ok, detalle = check_all_shares()

        self.assertTrue(todos_ok)
        self.assertEqual([item["share"] for item in detalle], ["produc", "Usuarios", "newfact"])
        for item in detalle:
            ruta = str(item["path"])
            # Ruta UNC al servidor, no un punto de montaje de Linux.
            self.assertIn("172.10.18.2", ruta)
            self.assertIn(str(item["share"]), ruta)
            self.assertNotIn("/mnt/smb", ruta)
            self.assertIn("Accesible", str(item["message"]))

    def test_outside_docker_reports_unreachable_share(self) -> None:
        with patch("app.services.utils.network_health.is_docker_runtime", return_value=False), patch(
            "pathlib.Path.exists", autospec=True, side_effect=lambda self: False
        ):
            todos_ok, detalle = check_all_shares()

        self.assertFalse(todos_ok)
        self.assertTrue(all("No se puede acceder" in str(item["message"]) for item in detalle))

    def test_each_share_reports_its_own_mount_path(self) -> None:
        exists_patch, run_patch = fake_filesystem(set())
        with docker_runtime(), exists_patch, run_patch:
            _, detalle = check_all_shares()

        rutas = {item["share"]: item["path"] for item in detalle}
        self.assertEqual(rutas["produc"], "/mnt/smb/produc")
        self.assertEqual(rutas["Usuarios"], "/mnt/smb/Usuarios")
        self.assertEqual(rutas["newfact"], "/mnt/smb/newfact")


if __name__ == "__main__":
    unittest.main()
