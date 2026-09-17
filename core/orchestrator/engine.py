from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path
from core.duration import validate_duration
from core.planner.planner import build_fallback_plan
from core.recovery.checkpoints import Checkpoints


class ShortsEngine:
    def __init__(self, root: Path):
        self.root = root
        self.projects = root / "projects"
        self.projects.mkdir(parents=True, exist_ok=True)

    def create_project(self, instruction: str, duration: int) -> Path:
        duration = validate_duration(duration)
        key = "short_" + datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        project = self.projects / key
        project.mkdir(parents=True)
        Checkpoints(project / "checkpoint.json").save("created", {"duration": duration})
        plan = build_fallback_plan(instruction, duration)
        (project / "plan.json").write_text(json.dumps({"duration": plan.duration, "title": plan.title, "scenes": [s.__dict__ for s in plan.scenes]}, default=lambda o: o.__dict__, ensure_ascii=False, indent=2), encoding="utf-8")
        Checkpoints(project / "checkpoint.json").save("planned")
        return project
