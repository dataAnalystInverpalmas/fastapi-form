import unittest
from unittest.mock import patch

from app.routes.api import api_etl_flow, api_list_etl_jobs
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
            job_id="proyecciones_csv",
            name="Proyecciones",
            description="Fuente base",
            allows_parallel=True,
            timeout_seconds=10,
            runner=lambda: "ok",
        )
        job_target = ETLJobDefinition(
            job_id="quipus_vs_proy",
            name="Quipus vs Proy",
            description="Derivado",
            allows_parallel=True,
            timeout_seconds=10,
            runner=lambda: "ok",
            depends_on=["proyecciones_csv"],
        )
        mock_list_jobs_from_catalog.return_value = [job_source, job_target]
        mock_list_jobs_with_state.return_value = [
            {
                "job_id": "proyecciones_csv",
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
                "job_id": "quipus_vs_proy",
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
        quipus = next(job for job in jobs if job["job_id"] == "quipus_vs_proy")

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
            job_id="proyecciones_csv",
            name="Proyecciones",
            description="Fuente base",
            allows_parallel=True,
            timeout_seconds=10,
            runner=lambda: "ok",
        )
        job_target = ETLJobDefinition(
            job_id="comparar_picos_demanda",
            name="Comparar picos",
            description="Analitica",
            allows_parallel=True,
            timeout_seconds=10,
            runner=lambda: "ok",
            depends_on=["proyecciones_csv"],
        )
        mock_list_jobs_from_catalog.return_value = [job_source, job_target]
        mock_list_jobs_with_state.return_value = [
            {
                "job_id": "proyecciones_csv",
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
                "job_id": "comparar_picos_demanda",
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
        comparar = next(job for job in jobs if job["job_id"] == "comparar_picos_demanda")

        self.assertEqual(comparar["dependency_status"], "missing")
        self.assertEqual(comparar["dependencies_total"], 1)
        self.assertEqual(comparar["dependencies_ready"], 0)
        self.assertEqual(len(comparar["missing_dependencies"]), 1)
        self.assertEqual(comparar["missing_dependencies"][0]["job_id"], "proyecciones_csv")

    @patch("app.routes.api.list_jobs_with_state")
    @patch("app.routes.api.list_jobs_from_catalog")
    def test_api_etl_flow_returns_nodes_and_edges(
        self,
        mock_list_jobs_from_catalog,
        mock_list_jobs_with_state,
    ) -> None:
        job_source = ETLJobDefinition(
            job_id="proyecciones_csv",
            name="Proyecciones",
            description="Fuente base",
            allows_parallel=True,
            timeout_seconds=10,
            runner=lambda: "ok",
        )
        job_target = ETLJobDefinition(
            job_id="quipus_vs_proy",
            name="Quipus vs Proy",
            description="Derivado",
            allows_parallel=True,
            timeout_seconds=10,
            runner=lambda: "ok",
            depends_on=["proyecciones_csv"],
            dependency_group="Producción",
            flow_group="03 - Derivados Semanales",
        )
        mock_list_jobs_from_catalog.return_value = [job_source, job_target]
        mock_list_jobs_with_state.return_value = [
            {
                "job_id": "proyecciones_csv",
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
                "job_id": "quipus_vs_proy",
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
        self.assertEqual(edge["from"], "proyecciones_csv")
        self.assertEqual(edge["to"], "quipus_vs_proy")
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
            job_id="proyecciones_csv",
            name="Proyecciones",
            description="Fuente base",
            allows_parallel=True,
            timeout_seconds=10,
            runner=lambda: "ok",
            dependency_group="Producción",
        )
        target = ETLJobDefinition(
            job_id="quipus_vs_proy",
            name="Quipus vs Proy",
            description="Derivado",
            allows_parallel=True,
            timeout_seconds=10,
            runner=lambda: "ok",
            depends_on=["proyecciones_csv"],
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
            job_id="proyecciones_csv",
            name="Proyecciones",
            description="Fuente base",
            allows_parallel=True,
            timeout_seconds=10,
            runner=lambda: "ok",
            dependency_group="Producción",
        )
        job_target = ETLJobDefinition(
            job_id="quipus_vs_proy",
            name="Quipus vs Proy",
            description="Derivado",
            allows_parallel=True,
            timeout_seconds=10,
            runner=lambda: "ok",
            depends_on=["proyecciones_csv"],
            dependency_group="Producción",
        )
        mock_list_jobs_from_catalog.return_value = [job_source, job_target]
        mock_list_jobs_with_state.return_value = []

        jobs = api_list_etl_jobs()

        self.assertEqual(jobs[0]["dependency_group"], "Producción")
        self.assertEqual(jobs[1]["dependency_group"], "Producción")


if __name__ == "__main__":
    unittest.main()
