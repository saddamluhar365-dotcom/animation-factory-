from __future__ import annotations
import logging
import threading
import time
from dataclasses import dataclass
from app.storage import mask_key, update_key_status
from .contracts import KeyHealthStatus

logger = logging.getLogger(__name__)


@dataclass
class FalKeyRecord:
    raw_key: str
    masked: str
    status: KeyHealthStatus
    enabled: bool = True
    cooldown_until: float = 0.0
    error_count: int = 0
    success_count: int = 0
    label: str = ""

    def is_available(self) -> bool:
        if not self.enabled or self.status == KeyHealthStatus.INVALID:
            return False
        if self.status == KeyHealthStatus.RATE_LIMITED:
            if time.time() >= self.cooldown_until:
                self.status = KeyHealthStatus.ACTIVE
                return True
            return False
        return self.status == KeyHealthStatus.ACTIVE


class FalKeyPool:
    """Thread-safe multi-key health pool with rate-limit cooldown and failover."""

    def __init__(self, keys: list[str | dict] | None = None, default_cooldown: float = 60.0):
        self._lock = threading.Lock()
        self._keys: list[FalKeyRecord] = []
        self._index = 0
        self.default_cooldown = default_cooldown
        if keys:
            for k in keys:
                self.add_key(k)

    def add_key(self, item: str | dict, label: str = "") -> FalKeyRecord:
        with self._lock:
            if isinstance(item, dict):
                raw = item.get("raw_key", "").strip()
                status_str = item.get("status", "active")
                try:
                    status = KeyHealthStatus(status_str)
                except ValueError:
                    status = KeyHealthStatus.ACTIVE
                enabled = item.get("enabled", True)
                lbl = item.get("label") or label or f"FAL Key {len(self._keys) + 1}"
            else:
                raw = str(item).strip()
                status = KeyHealthStatus.ACTIVE
                enabled = True
                lbl = label or f"FAL Key {len(self._keys) + 1}"

            if not raw:
                raise ValueError("Cannot add empty FAL key")

            # Check if key already in pool
            for rec in self._keys:
                if rec.raw_key == raw:
                    rec.enabled = enabled
                    rec.status = status
                    return rec

            rec = FalKeyRecord(
                raw_key=raw,
                masked=mask_key(raw),
                status=status,
                enabled=enabled,
                label=lbl,
            )
            self._keys.append(rec)
            return rec

    def remove_key(self, identifier: str) -> None:
        with self._lock:
            self._keys = [
                k for k in self._keys
                if k.raw_key != identifier and k.masked != identifier
            ]

    def count(self) -> int:
        with self._lock:
            return len(self._keys)

    def active_count(self) -> int:
        with self._lock:
            return sum(1 for k in self._keys if k.is_available())

    def get_next_key(self) -> FalKeyRecord:
        with self._lock:
            if not self._keys:
                raise RuntimeError("No FAL API keys configured. Please add FAL keys in Settings -> APIs.")

            # Find available key using round-robin starting at _index
            n = len(self._keys)
            for i in range(n):
                idx = (self._index + i) % n
                rec = self._keys[idx]
                if rec.is_available():
                    self._index = (idx + 1) % n
                    return rec

            # If all are rate-limited, calculate min remaining wait time
            cooldowns = [
                k.cooldown_until - time.time()
                for k in self._keys
                if k.enabled and k.status == KeyHealthStatus.RATE_LIMITED
            ]
            if cooldowns:
                wait_time = max(1.0, min(cooldowns))
                raise RuntimeError(
                    f"All configured FAL API keys are temporarily rate-limited (HTTP 429). "
                    f"Retry in {wait_time:.1f}s or add additional FAL keys in Settings -> APIs."
                )

            raise RuntimeError("All configured FAL API keys are disabled or invalid. Check Settings -> APIs.")

    def mark_rate_limited(self, raw_key: str, cooldown_seconds: float | None = None) -> None:
        duration = cooldown_seconds if cooldown_seconds is not None else self.default_cooldown
        with self._lock:
            for rec in self._keys:
                if rec.raw_key == raw_key:
                    rec.status = KeyHealthStatus.RATE_LIMITED
                    rec.cooldown_until = time.time() + duration
                    rec.error_count += 1
                    logger.warning("FAL key %s rate-limited; cooldown for %.1fs", rec.masked, duration)
                    try:
                        update_key_status("fal", rec.raw_key, "rate_limited")
                    except Exception:
                        pass
                    break

    def mark_invalid(self, raw_key: str, reason: str = "") -> None:
        with self._lock:
            for rec in self._keys:
                if rec.raw_key == raw_key:
                    rec.status = KeyHealthStatus.INVALID
                    rec.enabled = False
                    rec.error_count += 1
                    logger.error("FAL key %s permanently invalid (%s); disabled in pool", rec.masked, reason)
                    try:
                        update_key_status("fal", rec.raw_key, "invalid")
                    except Exception:
                        pass
                    break

    def mark_success(self, raw_key: str) -> None:
        with self._lock:
            for rec in self._keys:
                if rec.raw_key == raw_key:
                    rec.status = KeyHealthStatus.ACTIVE
                    rec.success_count += 1
                    break

    def status_summary(self) -> dict[str, int]:
        with self._lock:
            summary = {"total": len(self._keys), "active": 0, "rate_limited": 0, "invalid": 0, "disabled": 0}
            for k in self._keys:
                if k.status == KeyHealthStatus.INVALID:
                    summary["invalid"] += 1
                elif not k.enabled or k.status == KeyHealthStatus.DISABLED:
                    summary["disabled"] += 1
                elif k.status == KeyHealthStatus.RATE_LIMITED:
                    summary["rate_limited"] += 1
                elif k.status == KeyHealthStatus.ACTIVE:
                    summary["active"] += 1
            return summary
