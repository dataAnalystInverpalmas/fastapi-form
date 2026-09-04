from __future__ import annotations

from dataclasses import dataclass, field
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
    depends_on: list[str] = field(default_factory=list)
    dependency_note: str | None = None
    dependency_group: str | None = None
    flow_group: str | None = None
