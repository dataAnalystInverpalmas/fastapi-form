import unittest
from unittest.mock import patch

from app.routes.api import api_etl_flow, api_list_etl_jobs, api_list_proyecciones_jobs
from app.services.etl.definition import ETLJobDefinition


class ApiEtlJobsDependenciesTests(unittest.TestCase):
    @patch("app.routes.api.list_jobs_with_state")
    @patch("app.routes.api.list_jobs_from_catalog")
    def test_dependency_status_ready_when_previous_job_last_status_is_success(
        self,
        mock_list_jobs_from_catalog,
        mock_list_jobs_with_state,
    ) -> None:
        job_source = ETLJobDefinition(
            job_id="fuente_base_job",
            name="Proyecciones",
            description="Fuente base",
            allows_parallel=True,
            timeout_seconds=10,
            runner=lambda: "ok",
        )
        job_target = ETLJobDefinition(
            job_id="derivado_a_job",
            name="Quipus vs Proy",
            description="Derivado",
            allows_parallel=True,
            timeout_seconds=10,
            runner=lambda: "ok",
            depends_on=["fuente_base_job"],
        )
        mock_list_jobs_from_catalog.return_value = [job_source, job_target]
        mock_list_jobs_with_state.return_value = [
            {
                "job_id": "fuente_base_job",
                "name": "Proyecciones",
                "description": "Fuente base",
                "allows_parallel": 1,
                "timeout_seconds": 10,
                "is_active": 1,
                "updated_at": None,
                "last_status": "success",
                "last_started_at": None,
            },
            {
                "job_id": "derivado_a_job",
                "name": "Quipus vs Proy",
                "description": "Derivado",
                "allows_parallel": 1,
                "timeout_seconds": 10,
                "is_active": 1,
                "updated_at": None,
                "last_status": "failed",
                "last_started_at": None,
            },
        ]

        jobs = api_list_etl_jobs()
        quipus = next(job for job in jobs if job["job_id"] == "derivado_a_job")

        self.assertEqual(quipus["dependency_status"], "ready")
        self.assertEqual(quipus["dependencies_total"], 1)
        self.assertEqual(quipus["dependencies_ready"], 1)
        self.assertEqual(quipus["missing_dependencies"], [])

    @patch("app.routes.api.list_jobs_with_state")
    @patch("app.routes.api.list_jobs_from_catalog")
    def test_dependency_status_missing_when_previous_job_has_no_success(
        self,
        mock_list_jobs_from_catalog,
        mock_list_jobs_with_state,
    ) -> None:
        job_source = ETLJobDefinition(
            job_id="fuente_base_job",
            name="Proyecciones",
            description="Fuente base",
            allows_parallel=True,
            timeout_seconds=10,
            runner=lambda: "ok",
        )
        job_target = ETLJobDefinition(
            job_id="derivado_b_job",
            name="Comparar picos",
            description="Analitica",
            allows_parallel=True,
            timeout_seconds=10,
            runner=lambda: "ok",
            depends_on=["fuente_base_job"],
        )
        mock_list_jobs_from_catalog.return_value = [job_source, job_target]
        mock_list_jobs_with_state.return_value = [
            {
                "job_id": "fuente_base_job",
                "name": "Proyecciones",
                "description": "Fuente base",
                "allows_parallel": 1,
                "timeout_seconds": 10,
                "is_active": 1,
                "updated_at": None,
                "last_status": "failed",
                "last_started_at": None,
            },
            {
                "job_id": "derivado_b_job",
                "name": "Comparar picos",
                "description": "Analitica",
                "allows_parallel": 1,
                "timeout_seconds": 10,
                "is_active": 1,
                "updated_at": None,
                "last_status": "queued",
                "last_started_at": None,
            },
        ]

        jobs = api_list_etl_jobs()
        comparar = next(job for job in jobs if job["job_id"] == "derivado_b_job")

        self.assertEqual(comparar["dependency_status"], "missing")
        self.assertEqual(comparar["dependencies_total"], 1)
        self.assertEqual(comparar["dependencies_ready"], 0)
        self.assertEqual(len(comparar["missing_dependencies"]), 1)
        self.assertEqual(comparar["missing_dependencies"][0]["job_id"], "fuente_base_job")

    @patch("app.routes.api.list_jobs_with_state")
    @patch("app.routes.api.list_jobs_from_catalog")
    def test_api_etl_flow_returns_nodes_and_edges(
        self,
        mock_list_jobs_from_catalog,
        mock_list_jobs_with_state,
    ) -> None:
        job_source = ETLJobDefinition(
            job_id="fuente_base_job",
            name="Proyecciones",
            description="Fuente base",
            allows_parallel=True,
            timeout_seconds=10,
            runner=lambda: "ok",
        )
        job_target = ETLJobDefinition(
            job_id="derivado_a_job",
            name="Quipus vs Proy",
            description="Derivado",
            allows_parallel=True,
            timeout_seconds=10,
            runner=lambda: "ok",
            depends_on=["fuente_base_job"],
            dependency_group="Producción",
            flow_group="03 - Derivados Semanales",
        )
        mock_list_jobs_from_catalog.return_value = [job_source, job_target]
        mock_list_jobs_with_state.return_value = [
            {
                "job_id": "fuente_base_job",
                "name": "Proyecciones",
                "description": "Fuente base",
                "allows_parallel": 1,
                "timeout_seconds": 10,
                "is_active": 1,
                "updated_at": None,
                "last_status": "success",
                "last_started_at": None,
            },
            {
                "job_id": "derivado_a_job",
                "name": "Quipus vs Proy",
                "description": "Derivado",
                "allows_parallel": 1,
                "timeout_seconds": 10,
                "is_active": 1,
                "updated_at": None,
                "last_status": "queued",
                "last_started_at": None,
            },
        ]

        payload = api_etl_flow()

        self.assertEqual(len(payload["nodes"]), 2)
        self.assertEqual(len(payload["edges"]), 1)
        edge = payload["edges"][0]
        self.assertEqual(edge["from"], "fuente_base_job")
        self.assertEqual(edge["to"], "derivado_a_job")
        self.assertEqual(edge["dependency_group"], "Producción")
        self.assertTrue(edge["ready"])

    @patch("app.routes.api.list_jobs_with_state")
    @patch("app.routes.api.list_jobs_from_catalog")
    def test_api_etl_flow_can_filter_by_dependency_group(
        self,
        mock_list_jobs_from_catalog,
        mock_list_jobs_with_state,
    ) -> None:
        source = ETLJobDefinition(
            job_id="fuente_base_job",
            name="Proyecciones",
            description="Fuente base",
            allows_parallel=True,
            timeout_seconds=10,
            runner=lambda: "ok",
            dependency_group="Producción",
        )
        target = ETLJobDefinition(
            job_id="derivado_a_job",
            name="Quipus vs Proy",
            description="Derivado",
            allows_parallel=True,
            timeout_seconds=10,
            runner=lambda: "ok",
            depends_on=["fuente_base_job"],
            dependency_group="Producción",
            flow_group="03 - Derivados Semanales",
        )
        other = ETLJobDefinition(
            job_id="load_process_siembras",
            name="Procesar Siembras",
            description="Otra dependencia",
            allows_parallel=True,
            timeout_seconds=10,
            runner=lambda: "ok",
            dependency_group="Siembras",
        )
        mock_list_jobs_from_catalog.return_value = [source, target, other]
        mock_list_jobs_with_state.return_value = []

        payload = api_etl_flow(group="Producción")

        self.assertEqual(len(payload["nodes"]), 2)
        self.assertEqual(len(payload["edges"]), 1)
        self.assertTrue(all(node["dependency_group"] == "Producción" for node in payload["nodes"]))

    @patch("app.routes.api.list_jobs_with_state")
    @patch("app.routes.api.list_jobs_from_catalog")
    def test_api_etl_jobs_include_dependency_group_metadata(
        self,
        mock_list_jobs_from_catalog,
        mock_list_jobs_with_state,
    ) -> None:
        job_source = ETLJobDefinition(
            job_id="fuente_base_job",
            name="Proyecciones",
            description="Fuente base",
            allows_parallel=True,
            timeout_seconds=10,
            runner=lambda: "ok",
            dependency_group="Producción",
        )
        job_target = ETLJobDefinition(
            job_id="derivado_a_job",
            name="Quipus vs Proy",
            description="Derivado",
            allows_parallel=True,
            timeout_seconds=10,
            runner=lambda: "ok",
            depends_on=["fuente_base_job"],
            dependency_group="Producción",
        )
        mock_list_jobs_from_catalog.return_value = [job_source, job_target]
        mock_list_jobs_with_state.return_value = []

        jobs = api_list_etl_jobs()

        self.assertEqual(jobs[0]["dependency_group"], "Producción")
        self.assertEqual(jobs[1]["dependency_group"], "Producción")

    @patch("app.routes.api.list_jobs_with_state")
    @patch("app.routes.api.list_jobs_from_catalog")
    def test_proyecciones_jobs_excluded_from_main_etl_listing(
        self,
        mock_list_jobs_from_catalog,
        mock_list_jobs_with_state,
    ) -> None:
        other = ETLJobDefinition(
            job_id="tabla_curvas_clavel",
            name="Tabla Curvas Clavel",
            description="No es de proyecciones",
            allows_parallel=True,
            timeout_seconds=10,
            runner=lambda: "ok",
        )
        proyeccion = ETLJobDefinition(
            job_id="planos_proyeccion",
            name="Plano de Proyeccion",
            description="Job real de proyecciones",
            allows_parallel=True,
            timeout_seconds=10,
            runner=lambda: "ok",
        )
        mock_list_jobs_from_catalog.return_value = [other, proyeccion]
        mock_list_jobs_with_state.return_value = []

        etl_jobs = api_list_etl_jobs()
        proyecciones_jobs = api_list_proyecciones_jobs()

        self.assertEqual([job["job_id"] for job in etl_jobs], ["tabla_curvas_clavel"])
        self.assertEqual([job["job_id"] for job in proyecciones_jobs], ["planos_proyeccion"])


    @patch("app.routes.api.list_jobs_with_state")
    @patch("app.routes.api.list_jobs_from_catalog")
    def test_proyecciones_listing_is_ordered_by_flow_step_not_by_name(
        self,
        mock_list_jobs_from_catalog,
        mock_list_jobs_with_state,
    ) -> None:
        def build(job_id: str, name: str) -> ETLJobDefinition:
            return ETLJobDefinition(
                job_id=job_id,
                name=name,
                description="x",
                allows_parallel=True,
                timeout_seconds=10,
                runner=lambda: "ok",
            )

        # Se pasan en orden alfabetico inverso al del flujo para comprobar que
        # el orden viene de PROYECCIONES_JOB_ORDER y no del nombre.
        mock_list_jobs_from_catalog.return_value = [
            build("proyecciones_csv", "A Proyecciones a CSV"),
            build("planos_proyeccion_hoja1", "B Subir Proyeccion"),
            build("planos_proyeccion", "C Plano de Proyeccion"),
            build("quipus_vs_proy", "D Quipus vs Proyecciones"),
        ]
        mock_list_jobs_with_state.return_value = []

        jobs = api_list_proyecciones_jobs()

        self.assertEqual(
            [job["job_id"] for job in jobs],
            ["quipus_vs_proy", "planos_proyeccion", "planos_proyeccion_hoja1", "proyecciones_csv"],
        )
        self.assertEqual([job["flow_step"] for job in jobs], [1, 2, 3, 4])

    @patch("app.routes.api.list_jobs_with_state")
    @patch("app.routes.api.list_jobs_from_catalog")
    def test_shared_proyecciones_jobs_stay_in_main_etl_listing(
        self,
        mock_list_jobs_from_catalog,
        mock_list_jobs_with_state,
    ) -> None:
        def build(job_id: str) -> ETLJobDefinition:
            return ETLJobDefinition(
                job_id=job_id,
                name=job_id,
                description="x",
                allows_parallel=True,
                timeout_seconds=10,
                runner=lambda: "ok",
            )

        mock_list_jobs_from_catalog.return_value = [
            build("quipus_vs_proy"),
            build("proyecciones_csv"),
            build("planos_proyeccion"),
            build("planos_proyeccion_hoja1"),
        ]
        mock_list_jobs_with_state.return_value = []

        etl_ids = {job["job_id"] for job in api_list_etl_jobs()}

        # quipus_vs_proy y proyecciones_csv los consumen otros flujos: siguen
        # visibles en ETL Jobs aunque tambien esten en el modulo Proyecciones.
        self.assertEqual(etl_ids, {"quipus_vs_proy", "proyecciones_csv"})

    @patch("app.routes.api.list_jobs_with_state")
    @patch("app.routes.api.list_jobs_from_catalog")
    def test_jobs_listing_exposes_manual_steps(
        self,
        mock_list_jobs_from_catalog,
        mock_list_jobs_with_state,
    ) -> None:
        job = ETLJobDefinition(
            job_id="planos_proyeccion_hoja1",
            name="Subir Proyeccion",
            description="x",
            allows_parallel=True,
            timeout_seconds=10,
            runner=lambda: "ok",
            manual_before=["Confirma el tipo"],
            manual_after=["Borra la proyeccion por tipo y flor"],
        )
        mock_list_jobs_from_catalog.return_value = [job]
        mock_list_jobs_with_state.return_value = []

        payload = api_list_proyecciones_jobs()[0]

        self.assertEqual(payload["manual_before"], ["Confirma el tipo"])
        self.assertEqual(payload["manual_after"], ["Borra la proyeccion por tipo y flor"])

    @patch("app.routes.api.list_jobs_with_state")
    @patch("app.routes.api.list_jobs_from_catalog")
    def test_jobs_listing_exposes_manual_steps_for_jobs_with_state(
        self,
        mock_list_jobs_from_catalog,
        mock_list_jobs_with_state,
    ) -> None:
        job = ETLJobDefinition(
            job_id="planos_proyeccion_hoja1",
            name="Subir Proyeccion",
            description="x",
            allows_parallel=True,
            timeout_seconds=10,
            runner=lambda: "ok",
            manual_before=["Confirma el tipo"],
            manual_after=["Borra la proyeccion por tipo y flor"],
        )
        mock_list_jobs_from_catalog.return_value = [job]
        mock_list_jobs_with_state.return_value = [
            {
                "job_id": "planos_proyeccion_hoja1",
                "name": "Subir Proyeccion",
                "description": "x",
                "allows_parallel": 1,
                "timeout_seconds": 10,
                "is_active": 1,
                "updated_at": None,
                "last_status": "success",
                "last_started_at": None,
            }
        ]

        payload = api_list_proyecciones_jobs()[0]

        self.assertEqual(payload["manual_before"], ["Confirma el tipo"])
        self.assertEqual(payload["manual_after"], ["Borra la proyeccion por tipo y flor"])
        self.assertEqual(payload["flow_step"], 3)


if __name__ == "__main__":
    unittest.main()
