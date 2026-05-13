"""
Entrypoint simple para Uvicorn.

Deja tu comando igual:
`uvicorn main:app --reload`
"""

from app.main import app  # noqa: F401
