from __future__ import annotations
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def _key(url: str, title: str) -> str:
    return hashlib.sha256((url.strip() + "\0" + title.strip()).encode()).hexdigest()


class ResearchStore:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> list[dict]:
        if not self.path.exists(): return []
        try: return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError): return []

    def merge(self, items: list[dict]) -> list[dict]:
        existing = {x.get("id"): x for x in self.load() if x.get("id")}
        now = datetime.now(timezone.utc).isoformat()
        for item in items:
            item = dict(item)
            item["id"] = item.get("id") or _key(str(item.get("url", "")), str(item.get("title", "")))
            item.setdefault("retrieved_at", now)
            existing[item["id"]] = {**existing.get(item["id"], {}), **item}
        result = list(existing.values())
        self.path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        return result
