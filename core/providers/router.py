from __future__ import annotations
from dataclasses import dataclass
from typing import Callable


@dataclass
class ProviderCandidate:
    provider: str
    key_id: str
    paid: bool = False
    enabled: bool = True
    healthy: bool = True
    priority: int = 100


class ProviderRouter:
    def __init__(self, paid_allowed: bool = False):
        self.paid_allowed = paid_allowed

    def eligible(self, candidates: list[ProviderCandidate]) -> list[ProviderCandidate]:
        return sorted((c for c in candidates if c.enabled and c.healthy and (self.paid_allowed or not c.paid)), key=lambda c: c.priority)

    def call(self, candidates: list[ProviderCandidate], operation: Callable[[ProviderCandidate], object]):
        last = None
        for candidate in self.eligible(candidates):
            try:
                return operation(candidate)
            except Exception as exc:
                last = exc
        raise RuntimeError(f"No eligible provider succeeded: {last}")
