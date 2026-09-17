from __future__ import annotations

from pathlib import Path
from typing import Callable

from app.pipeline import run_project
from core.duration import validate_duration


class ShortsEngine:
    """Public orchestration facade; delegates every generation to the canonical pipeline."""

    def __init__(self, root: Path):
        self.root = root
        self.projects = root / "projects"
        self.projects.mkdir(parents=True, exist_ok=True)

    def create_project(self, instruction: str, duration: int, status_cb: Callable[[str], None] | None = None) -> Path:
        if not instruction or not instruction.strip():
            raise ValueError("instruction is required")
        duration = validate_duration(duration)
        return run_project(instruction.strip(), duration, status_cb or (lambda _status: None))
