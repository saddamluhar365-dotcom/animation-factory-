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


def set_api(provider: str, key: str) -> None:
    config = load_config()
    config.setdefault("apis", {}).setdefault(provider, [])
    if key and key not in config["apis"][provider]:
        config["apis"][provider].append(key)
    save_config(config)


def get_keys(provider: str) -> list[str]:
    return load_config().get("apis", {}).get(provider, [])
