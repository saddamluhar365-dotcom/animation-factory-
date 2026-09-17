from __future__ import annotations
import json
from pathlib import Path


class Checkpoints:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def save(self, stage: str, payload: dict | None = None) -> None:
        self.path.write_text(json.dumps({"stage": stage, "payload": payload or {}}, ensure_ascii=False, indent=2), encoding="utf-8")

    def load(self) -> dict:
        if not self.path.exists(): return {"stage": "start", "payload": {}}
        try: return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError): return {"stage": "start", "payload": {}}
