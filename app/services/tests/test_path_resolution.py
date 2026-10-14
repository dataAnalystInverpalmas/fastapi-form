import os
import re
import unittest
from unittest.mock import patch

from app.services.utils.dbf_reader import normalize_path
from app.services.utils.pathing import (
    get_configured_shares,
    get_share_mount_path,
    resolve_share_dir,
)

# Rutas UNC construidas asi para que el prefijo \\ quede explicito.
UNC = "\\" + "\\"


def docker_env():
    """Contexto que simula el contenedor: APP_ENV=docker."""
    return patch.dict(os.environ, {"APP_ENV": "docker"}, clear=False)


class NormalizePathTests(unittest.TestCase):
    def test_normalize_path_uses_container_mount_for_unc_paths(self) -> None:
        with docker_env():
            with patch("app.services.utils.dbf_reader.os.path.exists", side_effect=lambda path: path in {"/mnt/smb/produc", "/mnt/smb/produc/tabla.dbf"}):
                self.assertEqual(
                    normalize_path(UNC + r"172.10.18.2\produc\tabla.dbf"),
                    "/mnt/smb/produc/tabla.dbf",
                )

    def test_main_share_keeps_its_share_segment(self) -> None:
        # Regresion: con el host por nombre y SMB_SERVER en IP, el share
        # "produc" se perdia y la ruta quedaba en /mnt/smb/ld_bcult/...
        with docker_env():
            self.assertEqual(
                normalize_path(UNC + r"172.10.18.2\produc\ld_bcult\ld_mvari.dbf"),
                "/mnt/smb/produc/ld_bcult/ld_mvari.dbf",
            )

    def test_secondary_share_resolves_to_its_own_mount(self) -> None:
        with docker_env():
            self.assertEqual(
                normalize_path(UNC + r"172.10.18.2\Usuarios\Outputs\Subir_Proyeccion.xlsx"),
                "/mnt/smb/Usuarios/Outputs/Subir_Proyeccion.xlsx",
            )

    def test_share_name_is_matched_ignoring_case(self) -> None:
        # settings.py mezcla \\...\Usuarios\... y //.../usuarios/...: ambas
        # tienen que caer en el mismo directorio de montaje.
        with docker_env():
            self.assertEqual(
                normalize_path(UNC + r"172.10.18.2\usuarios\Hilder\Data\quipus.csv"),
                "/mnt/smb/Usuarios/Hilder/Data/quipus.csv",
            )

    def test_forward_slash_unc_paths_also_use_the_mount(self) -> None:
        # Varios settings (QUIPUS_TIKA_DIR, DIRIGIDAS_*, PEDIDOS_*) usan el
        # estilo //servidor/share/...; antes no se resolvian en el contenedor.
        with docker_env():
            self.assertEqual(
                normalize_path("//172.10.18.2/usuarios/Hilder/Data/tika/quipus"),
                "/mnt/smb/Usuarios/Hilder/Data/tika/quipus",
            )

    def test_newfact_share_resolves(self) -> None:
        with docker_env():
            self.assertEqual(
                normalize_path("//172.10.18.2/newfact/DINAMICA/PEDIDOS_surtido.dbf"),
                "/mnt/smb/newfact/DINAMICA/PEDIDOS_surtido.dbf",
            )

    def test_server_alias_resolves_like_the_ip(self) -> None:
        # Un operador puede escribir el nombre del servidor desde /config.
        with docker_env():
            self.assertEqual(
                normalize_path(UNC + r"svrinverpalmas\produc\tabla.dbf"),
                "/mnt/smb/produc/tabla.dbf",
            )

    def test_unknown_share_of_known_server_keeps_share_segment(self) -> None:
        # Un share que todavia no esta en SMB_SHARES apunta al lugar correcto:
        # basta montarlo, no hay que tocar rutas.
        with docker_env():
            self.assertEqual(
                normalize_path(UNC + r"172.10.18.2\contabilidad\x.dbf"),
                "/mnt/smb/contabilidad/x.dbf",
            )

    def test_unknown_server_is_namespaced_under_mount_root(self) -> None:
        with docker_env():
            self.assertEqual(
                normalize_path(UNC + r"otroservidor\share\x.dbf"),
                "/mnt/smb/otroservidor/share/x.dbf",
            )

    def test_windows_runtime_leaves_unc_paths_untouched(self) -> None:
        with patch.dict(os.environ, {"APP_ENV": "local"}, clear=False):
            with patch("app.services.utils.pathing.os.path.exists", return_value=False):
                self.assertEqual(
                    normalize_path(UNC + r"172.10.18.2\produc\tabla.dbf"),
                    UNC + r"172.10.18.2\produc\tabla.dbf",
                )


class SettingsPathsLiveOnSharesTests(unittest.TestCase):
    """Ningun default de Settings puede apuntar a una unidad local.

    Regresion: QUIPUS_EXCEL_OUTPUT_PATH apuntaba a C:\\Users\\...\\Qsync\\...
    (carpeta local de un equipo). En Windows funcionaba, pero dentro del
    contenedor esa ruta no existe y quipus_vs_proy / planos_proyeccion_hoja1
    fallaban. Todo archivo que compartan los jobs va en un share de SMB_SHARES.
    """

    LOCAL_DRIVE = re.compile(r"^[A-Za-z]:[\\/]")

    def test_no_default_points_to_a_local_drive(self) -> None:
        from app.core.settings import Settings

        offenders = [
            f"{name} = {field.default}"
            for name, field in Settings.model_fields.items()
            if isinstance(field.default, str) and self.LOCAL_DRIVE.match(field.default)
        ]
        self.assertEqual(offenders, [], f"Rutas locales en Settings: {offenders}")


class ConfiguredSharesTests(unittest.TestCase):
    """SMB_SHARES la leen pydantic y bash, asi que acepta varias formas."""

    def _shares(self, value):
        with patch("app.core.settings.settings.SMB_SHARES", value):
            return get_configured_shares()

    def test_parses_comma_separated_text(self) -> None:
        # Formato de docker-compose/.env: tiene que servirle tambien a bash.
        self.assertEqual(
            self._shares("produc,Usuarios,newfact"), ["produc", "Usuarios", "newfact"]
        )

    def test_parses_json_list_text(self) -> None:
        # Como lo escribiria quien asuma que sigue siendo un campo lista.
        self.assertEqual(
            self._shares('["produc","Usuarios","newfact"]'), ["produc", "Usuarios", "newfact"]
        )

    def test_parses_real_list(self) -> None:
        self.assertEqual(self._shares(["produc", "Usuarios"]), ["produc", "Usuarios"])

    def test_trims_spaces_and_ignores_empty_entries(self) -> None:
        self.assertEqual(self._shares(" produc , , Usuarios "), ["produc", "Usuarios"])

    def test_empty_value_yields_no_shares(self) -> None:
        self.assertEqual(self._shares(""), [])


class ShareMappingTests(unittest.TestCase):
    def test_resolve_share_dir_returns_configured_spelling(self) -> None:
        self.assertEqual(resolve_share_dir("usuarios"), "Usuarios")
        self.assertEqual(resolve_share_dir("PRODUC"), "produc")

    def test_resolve_share_dir_returns_none_for_unknown_share(self) -> None:
        self.assertIsNone(resolve_share_dir("contabilidad"))
        self.assertIsNone(resolve_share_dir(""))

    def test_main_share_honours_smb_mount_path(self) -> None:
        with patch("app.core.settings.settings.SMB_MOUNT_PATH", "/data/produc"):
            self.assertEqual(get_share_mount_path("produc").as_posix(), "/data/produc")

    def test_secondary_share_uses_mount_root(self) -> None:
        with patch("app.core.settings.settings.SMB_MOUNT_PATH", "/data/produc"):
            self.assertEqual(get_share_mount_path("Usuarios").as_posix(), "/mnt/smb/Usuarios")


if __name__ == "__main__":
    unittest.main()
