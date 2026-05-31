from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class ETLJobDefinition:
    job_id: str
    name: str
    description: str
    allows_parallel: bool
    timeout_seconds: int
    runner: Callable[..., str]
    supports_params: bool = False
    default_params: dict[str, Any] | None = None
