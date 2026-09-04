# Revisión técnica del proyecto

Última actualización: 2 de septiembre de 2026.

Este documento resume el estado técnico conocido del Portal de Datos Inverpalmas. No sustituye una prueba de aceptación en el entorno productivo.

## Estado actual

- FastAPI inicia con un context manager `lifespan`; allí registra los jobs, configura el scheduler y recupera ejecuciones obsoletas.
- MySQL usa `MySQLConnectionPool` con cinco conexiones reutilizables.
- El catálogo ETL está separado en `app/services/etl/catalog.py`, `registry.py`, `runner.py`, `repository.py` y `params.py`.
- El registro de jobs se inicializa de forma lazy al primer acceso.
- Vue 3 se sirve en desarrollo con Vite y, después del build, bajo `/app/`. La interfaz legacy Jinja2 continúa disponible.
- Los pipelines de producción, calidades y fusarium generan la finca sintética `000`. El reporte de productividad consume esos resúmenes y mantiene separadas las columnas `ciclo` y `Pico`.

## Riesgos pendientes

### Dependencia de rutas de red

Varios jobs leen DBF y CSV desde rutas SMB/UNC. La aplicación puede arrancar sin el montaje disponible, pero los jobs que necesiten esos archivos fallarán. En Docker, `scripts/entrypoint.sh` intenta montar el recurso CIFS y expone el estado mediante `/health`.

### Configuración sensible

Las credenciales y rutas deben configurarse en `.env`, a partir de `.env.example`. El archivo `.env` real no debe versionarse ni incluirse en logs o capturas de diagnóstico.

### Dependencias entre jobs

La UI muestra las dependencias declaradas en el catálogo y el endpoint `/api/etl/flow` expone nodos y aristas. La advertencia de una dependencia faltante no bloquea por sí sola la ejecución; quien opera el proceso debe respetar el orden requerido.

### Compatibilidad de datos

Los archivos DBF dependen de codificaciones y esquemas externos. Cualquier cambio en tablas, nombres de columnas o rangos de fechas debe validarse con los tests del job afectado y con una muestra real no productiva.

## Validación recomendada

Desde la raíz del repositorio:

```powershell
venv\Scripts\python.exe -m unittest discover -s app\services\tests -p "test_*.py"
```

Para validar el frontend y el contenedor:

```powershell
cd frontend
npm ci
npm run build
cd ..
docker compose config
```

Las suites focalizadas de producción, fusarium, calidades y productividad se describen también en el [README principal](README.md).
