"""
Módulo de configuración legacy - mantiene compatibilidad hacia atrás.

Se recomienda usar `app.core.settings` en su lugar.
"""
from __future__ import annotations

from app.core.settings import settings

# Mantener compatibilidad hacia atrás
BASE_DIR = settings.BASE_DIR
DEFAULT_DBF_PATH = settings.DEFAULT_DBF_PATH

