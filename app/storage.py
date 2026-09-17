from __future__ import annotations
import json
from pathlib import Path
from cryptography.fernet import Fernet

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)
SECRETS = DATA / "secrets.key"
CONFIG = DATA / "config.enc"


def _fernet() -> Fernet:
    if not SECRETS.exists():
        SECRETS.write_bytes(Fernet.generate_key())
    return Fernet(SECRETS.read_bytes())


def load_config() -> dict:
    if not CONFIG.exists():
        return {"apis": {}, "reference_profile": {}, "initialized": False}
    try:
        raw = _fernet().decrypt(CONFIG.read_bytes())
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return {"apis": {}, "reference_profile": {}, "initialized": False}


def save_config(config: dict) -> None:
    payload = json.dumps(config, ensure_ascii=False, indent=2).encode("utf-8")
    CONFIG.write_bytes(_fernet().encrypt(payload))


def mask_key(key: str) -> str:
    """Return a masked representation of an API key for safe display and logging."""
    if not key:
        return ""
    if len(key) <= 8:
        return "***" + key[-3:]
    return key[:4] + "..." + key[-4:]


def set_api(provider: str, key: str, label: str = "") -> None:
    add_key(provider, key, label=label)


def add_key(provider: str, key: str, label: str = "") -> None:
    """Add an API key to the provider pool without duplicates or hard limits."""
    key = (key or "").strip()
    if not key:
        return
    config = load_config()
    items = config.setdefault("apis", {}).setdefault(provider, [])
    
    # Check if key already exists
    for item in items:
        raw = item["raw_key"] if isinstance(item, dict) else str(item)
        if raw == key:
            if isinstance(item, dict) and not item.get("enabled", True):
                item["enabled"] = True
                item["status"] = "active"
                save_config(config)
            return

    # Count existing keys for default label
    key_num = len(items) + 1
    key_label = label or f"{provider.upper()} Key {key_num}"
    
    new_entry = {
        "raw_key": key,
        "masked": mask_key(key),
        "enabled": True,
        "status": "active",
        "label": key_label,
    }
    items.append(new_entry)
    save_config(config)


def remove_key(provider: str, key_identifier: str) -> None:
    """Remove a key by its raw value or masked representation."""
    config = load_config()
    items = config.get("apis", {}).get(provider, [])
    updated = []
    for item in items:
        raw = item["raw_key"] if isinstance(item, dict) else str(item)
        masked = item.get("masked", mask_key(raw)) if isinstance(item, dict) else mask_key(raw)
        if raw != key_identifier and masked != key_identifier:
            updated.append(item)
    config.setdefault("apis", {})[provider] = updated
    save_config(config)


def toggle_key(provider: str, key_identifier: str, enabled: bool) -> None:
    """Enable or disable a specific key in the pool."""
    config = load_config()
    items = config.get("apis", {}).get(provider, [])
    for item in items:
        if isinstance(item, dict):
            if item.get("raw_key") == key_identifier or item.get("masked") == key_identifier:
                item["enabled"] = bool(enabled)
                item["status"] = "active" if enabled else "disabled"
                break
    save_config(config)


def update_key_status(provider: str, key_identifier: str, status: str) -> None:
    """Update health status of a key (active, rate_limited, invalid, disabled)."""
    config = load_config()
    items = config.get("apis", {}).get(provider, [])
    for item in items:
        if isinstance(item, dict):
            if item.get("raw_key") == key_identifier or item.get("masked") == key_identifier:
                item["status"] = status
                if status == "invalid":
                    item["enabled"] = False
                break
    save_config(config)


def get_keys(provider: str) -> list[str]:
    """Return all active, enabled raw keys for the specified provider."""
    items = load_config().get("apis", {}).get(provider, [])
    keys = []
    for item in items:
        if isinstance(item, dict):
            if item.get("enabled", True) and item.get("status") != "invalid":
                raw = item.get("raw_key", "").strip()
                if raw:
                    keys.append(raw)
        elif isinstance(item, str) and item.strip():
            keys.append(item.strip())
    return keys


def get_keys_metadata(provider: str) -> list[dict]:
    """Return full metadata for all configured keys of the specified provider."""
    items = load_config().get("apis", {}).get(provider, [])
    result = []
    for idx, item in enumerate(items, 1):
        if isinstance(item, dict):
            raw = item.get("raw_key", "")
            result.append({
                "raw_key": raw,
                "masked": item.get("masked") or mask_key(raw),
                "enabled": item.get("enabled", True),
                "status": item.get("status", "active"),
                "label": item.get("label", f"{provider.upper()} Key {idx}"),
            })
        elif isinstance(item, str):
            result.append({
                "raw_key": item,
                "masked": mask_key(item),
                "enabled": True,
                "status": "active",
                "label": f"{provider.upper()} Key {idx}",
            })
    return result

