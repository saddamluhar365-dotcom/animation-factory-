from __future__ import annotations
from datetime import datetime, timezone
import math


def freshness(retrieved_at: str) -> float:
    try: age = max(0.0, (datetime.now(timezone.utc) - datetime.fromisoformat(retrieved_at.replace("Z", "+00:00"))).total_seconds() / 86400)
    except (ValueError, TypeError): return 0.0
    return 1.0 / (1.0 + age / 30.0)


def rank(items: list[dict], topic: str) -> list[dict]:
    terms = set(topic.lower().split())
    scored = []
    for item in items:
        text = f"{item.get('title','')} {item.get('summary','')} {item.get('content','')}".lower()
        relevance = len(terms & set(text.split())) / max(1, len(terms))
        score = relevance * 0.7 + freshness(item.get("retrieved_at", "")) * 0.3
        scored.append((score, item))
    return [item for _, item in sorted(scored, key=lambda x: x[0], reverse=True)]
