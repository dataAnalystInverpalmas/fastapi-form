# Portal de Datos Inverpalmas

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-green.svg)](https://fastapi.tiangolo.com/)
[![Vue.js 3](https://img.shields.io/badge/Vue-3+-brightgreen.svg)](https://vuejs.org/)

Aplicación web fullstack para gestión y análisis de datos de producción agrícola. Integra procesos ETL automatizados, consultas dinámicas y reportes en tiempo real.

## 📋 Descripción

Portal integral de datos para **Inverpalmas** que permite:

- **Consultas dinámicas** de datos de producción y cultivos
- **Procesos ETL automatizados** para extracción y transformación de datos DBF
- **Generación de reportes** en Excel con análisis complejos
- **Dashboard interactivo** con visualización de datos
- **Gestión de ejecuciones ETL** con seguimiento en tiempo real
- **Análisis de anomalías** en datos de producción

## 🛠️ Stack Tecnológico

### Backend
- **FastAPI** - Framework web moderno y rápido
- **Python 3.10+** - Lenguaje principal
- **Pydantic** - Validación de datos y configuración
- **SQLAlchemy** - ORM para base de datos
- **MariaDB/MySQL** - Base de datos
- **Simpledbf** - Lectura de archivos DBF
- **Pandas/Openpyxl** - Procesamiento de datos y Excel

### Frontend
- **Vue.js 3** - Framework JavaScript reactivo
- **Vite** - Build tool moderno
- **Tailwind CSS** - Estilos CSS utilitarios
- **Axios** - Cliente HTTP

## 📦 Requisitos

- **Python 3.10+**
- **Node.js 16+** (para frontend)
- **MariaDB/MySQL 5.7+**
- Acceso a rutas de red compartidas (\\svrinverpalmas\...)
- **Git** (recomendado)

## 🚀 Instalación y Configuración

### 1. Clonar o descargar el repositorio

```bash
cd c:\Users\ESTADISTICA\Documents\fastapi-form
```

### 2. Configurar Backend

```bash
# Crear entorno virtual
python -m venv venv

# Activar entorno virtual
venv\Scripts\activate  # Windows

# Instalar dependencias
pip install -r requirements.txt
```

### 3. Configurar variables de entorno

Crea un archivo `.env` en la raíz del proyecto:

```env
# Información de la aplicación
APP_NAME=Portal de Datos Inverpalmas
DEBUG=False

# Base de datos
DB_HOST=localhost
DB_PORT=3306
DB_USER=usuario
DB_PASSWORD=contraseña
DB_NAME=informes

# Rutas de archivos (ajusta según tu entorno)
DEFAULT_DBF_PATH=\\svrinverpalmas\produc\LD_BCULT\hijos2026.dbf
EXCEL_OUTPUT_DIR=\\svrinverpalmas\Usuarios\Outputs
```

Ver `app/core/settings.py` para documentación completa de todas las variables.

### 4. Configurar Frontend

```bash
cd frontend

# Instalar dependencias
npm install

# (Opcional) Instalar dependencias globales de Marp si usas presentaciones
npm install -g @marp-team/marp-cli
```

### 5. Inicializar Base de Datos

```bash
# Crear base de datos e inicializar esquemas
python -m app.core.db
```

## ▶️ Ejecución

### Modo Desarrollo

**Terminal 1 - Backend:**
```bash
# Asegúrate de estar en la raíz del proyecto con venv activado
python main.py
# La aplicación estará en http://localhost:8000
```

**Terminal 2 - Frontend:**
```bash
cd frontend
npm run dev
# La aplicación estará en http://localhost:5173
```

### Modo Producción

```bash
# Backend con Uvicorn
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4

# Frontend
cd frontend
npm run build
# Servir archivos generados en dist/
```

## 📁 Estructura del Proyecto

```
fastapi-form/
├── app/                          # Código principal
│   ├── __init__.py
│   ├── main.py                  # Punto de entrada FastAPI
│   ├── core/                    # Configuración central
│   │   ├── config.py
│   │   ├── db.py               # Configuración de base de datos
│   │   └── settings.py         # Variables de configuración
│   ├── routes/                 # Endpoints y rutas web
│   │   ├── api.py              # APIs REST
│   │   └── web.py              # Rutas web (templates)
│   └── services/               # Lógica de negocio
│       ├── etl_*.py            # Servicios ETL
│       ├── etl_registry.py     # Registro de trabajos ETL
│       ├── etl_runner.py       # Ejecutor de ETL
│       ├── dbf_reader.py       # Lector de archivos DBF
│       ├── date_service.py     # Servicios de fechas
│       ├── pivot_service.py    # Servicios de pivoteo
│       ├── query_processes.py  # Procesamiento de consultas
│       ├── dbf_loaders/        # Cargadores específicos de DBF
│       │   └── load_*_generator.py
│       └── etl_jobs/           # Trabajos ETL específicos
│           └── *_generator.py
├── frontend/                    # Aplicación Vue.js
│   ├── src/
│   │   ├── components/         # Componentes Vue
│   │   ├── views/              # Páginas/Vistas
│   │   ├── composables/        # Composables (lógica reutilizable)
│   │   ├── router/             # Configuración de rutas
│   │   └── App.vue             # Componente raíz
│   └── vite.config.js          # Configuración Vite
├── templates/                   # Templates HTML para web routes
├── static/                      # Archivos estáticos (CSS, JS)
├── load/                        # Notebooks Jupyter para análisis
│   └── *.ipynb
├── requirements.txt            # Dependencias Python
├── main.py                      # Punto de entrada alternativo
└── README.md                    # Este archivo
```

## 🔄 Procesos ETL Principales

### Base de Datos Directa (DBF Loaders)
- **Cargas MGCOL**: Colores y variedades
- **Cargas MFIES**: Festivales
- **Cargas MCOSE**: Cosechas
- **Cargas MVARI**: Variedades de flores
- **Cargas Lonas**: Datos de lonas (2024-2026)
- **Cargas Fusarium**: Histórico de fusarium
- **Cargas Tabla Nacional**: Datos nacionales

### Procesos Transformación (ETL Jobs)
- **Producto Procesado**: ETL de `pprocesado_*.dbf`
- **Proyecciones**: Análisis de proyecciones 2024-2026
- **Producción Picos**: Análisis de producción por picos
- **Quipus vs Proyecciones**: Comparativa de datos
- **Dirigidas**: Análisis de dirigidas
- **Pedidos Surtidos**: Procesos de ventas
- **Comparar Tika**: Comparativa Tika/Producción/Despachos
- **Anomalías Lonas**: Detección de anomalías
- **Tabla Curvas Clavel**: Curvas de clavel

## 📊 Vistas y Funcionalidades

### Dashboard
- Visualización de métricas clave
- Gráficos de producción
- Estado de ETL jobs

### Consultas Dinámicas
- **Consultar**: Búsqueda libre de datos
- **Consultas Procesos**: Seguimiento de procesos ETL
- **Reporte Dinámico**: Generación de reportes personalizados

### Gestión ETL
- **Parámetros**: Configuración de ETL jobs
- **Ejecuciones**: Historial de ejecuciones
- **Cargas**: Cargas manuales de archivos DBF

## ⚙️ Configuración Avanzada

### Variables de Entorno Principales

```env
# Aplicación
APP_NAME=Portal de Datos Inverpalmas
APP_VERSION=1.0.0
DEBUG=False

# Base de datos
DB_HOST=localhost
DB_PORT=3306
DB_USER=usuario
DB_PASSWORD=contraseña
DB_NAME=informes

# ETL
ETL_MAX_WORKERS=3

# Zona horaria
TIMEZONE=America/Bogota

# Rutas personalizadas (ver settings.py para todas)
DEFAULT_DBF_PATH=ruta_archivo.dbf
EXCEL_OUTPUT_DIR=ruta_salida
```

Ver [app/core/settings.py](app/core/settings.py) para documentación completa de todas las variables de configuración.

## 🗄️ Base de Datos

### Configuración MariaDB/MySQL

```sql
-- Crear base de datos
CREATE DATABASE informes CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- Crear usuario (opcional)
CREATE USER 'usuario'@'localhost' IDENTIFIED BY 'contraseña';
GRANT ALL PRIVILEGES ON informes.* TO 'usuario'@'localhost';
FLUSH PRIVILEGES;
```

Las migraciones y esquemas se pueden gestionar con alembic o SQLAlchemy.

## 🧪 Testing

```bash
# Ejecutar tests
pytest

# Con cobertura
pytest --cov=app
```

## 📝 Notas de Desarrollo

### Lectura de DBF
- Los archivos DBF se codifican en `latin1`, `cp1252` o `utf-8`
- El servicio intenta múltiples codificaciones automáticamente
- Ver `services/dbf_reader.py`

### Procesos ETL
- Los ETL jobs se registran en `etl_registry.py`
- Se ejecutan con workers configurables (defecto: 3)
- Soportan ejecución paralela con control de recursos

### Frontend
- Usa Vue 3 Composition API
- Composables reutilizables en `src/composables/`
- Polling automático para ETL en `useEtlPolling.js`

## 🐛 Troubleshooting

### Problema: Error de conexión a base de datos
```
Solución: Verificar credenciales en .env y que MariaDB/MySQL esté corriendo
```

### Problema: Archivos DBF no se encuentran
```
Solución: Verificar rutas en .env y acceso a \\svrinverpalmas\...
```

### Problema: Frontend no se conecta con backend
```
Solución: Verificar que backend esté corriendo en http://localhost:8000
y revisar CORS en app/main.py
```

## 📚 Recursos Adicionales

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Vue 3 Documentation](https://vuejs.org/)
- [Pydantic Documentation](https://docs.pydantic.dev/)
- [SQLAlchemy Documentation](https://docs.sqlalchemy.org/)

## 👥 Autores

- Equipo de Datos - Inverpalmas

## 📄 Licencia

Privado - Inverpalmas. Todos los derechos reservados.

## 📞 Soporte

Para reportar problemas o sugerencias, contactar al equipo de desarrollo.

---

**Última actualización**: Abril 2026
**Versión de la aplicación**: 1.0.0
#   f a s t a p i - f o r m  
 