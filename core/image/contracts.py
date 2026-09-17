from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class ImageRouteStatus(str, Enum):
    CONFIGURED = "CONFIGURED"
    LIVE = "LIVE"
    INVALID_TOKEN = "INVALID_TOKEN"
    UNAUTHORIZED = "UNAUTHORIZED"
    QUOTA_EXHAUSTED = "QUOTA_EXHAUSTED"
    RATE_LIMITED = "RATE_LIMITED"
    MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    TEMPORARY_FAILURE = "TEMPORARY_FAILURE"


@dataclass
class ImageResult:
    path: Path
    model: str
    provider: str
    request_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    duration: float = 0.0
    retry_count: int = 0
    route_used: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "model": self.model,
            "provider": self.provider,
            "request_id": self.request_id,
            "metadata": self.metadata,
            "duration": round(self.duration, 3),
            "retry_count": self.retry_count,
            "route_used": self.route_used,
        }
