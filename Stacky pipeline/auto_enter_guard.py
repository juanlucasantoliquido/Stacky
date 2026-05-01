"""
auto_enter_guard.py — Detección de comandos destructivos en prompts pendientes
antes de disparar Ctrl+Enter.

Modos:
    - advisory (default): loguea pero deja pasar.
    - blocking: aborta el press si matchea.
    - off: desactivado.

La configuración vive en ``config.json`` bajo la clave ``auto_approve``:

    {
      "auto_approve": {
        "mode": "advisory",
        "dry_run": true,
        "dry_run_expires_at": "2026-04-23T12:00:00Z"
      }
    }

El guard expone una API pura (``check``) y helpers para leer la config.
"""

from __future__ import annotations

import json
import logging
import re
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

logger = logging.getLogger("stacky.auto_enter.guard")

_BASE_DIR    = Path(__file__).resolve().parent
_CONFIG_PATH = _BASE_DIR / "config.json"
_CONFIG_LOCK = threading.RLock()

Mode = Literal["advisory", "blocking", "off"]

DESTRUCTIVE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\brm\s+-rf\b", re.IGNORECASE),                              "rm -rf"),
    (re.compile(r"\brmdir\s+/s\b", re.IGNORECASE),                            "rmdir /s"),
    (re.compile(r"\bRMDIR\s+/S\s+/Q\b", re.IGNORECASE),                       "rmdir /s /q"),
    (re.compile(r"\bdel\s+/[fs]\b", re.IGNORECASE),                           "del /f o /s"),
    (re.compile(r"git\s+push\s+.*--force(?:\b|-with-lease\b)", re.IGNORECASE),"git push --force"),
    (re.compile(r"git\s+reset\s+--hard\b", re.IGNORECASE),                    "git reset --hard"),
    (re.compile(r"\bDROP\s+(?:TABLE|DATABASE|SCHEMA|INDEX)\b", re.IGNORECASE),"DROP"),
    (re.compile(r"\bTRUNCATE\s+TABLE\b", re.IGNORECASE),                      "TRUNCATE"),
    (re.compile(r"\bsudo\b", re.IGNORECASE),                                  "sudo"),
    (re.compile(r"\bformat\s+[a-z]:\b", re.IGNORECASE),                       "format drive"),
    (re.compile(r"\bshutdown\b", re.IGNORECASE),                              "shutdown"),
    (re.compile(r"\bDELETE\s+FROM\b", re.IGNORECASE),                         "DELETE FROM sin WHERE"),
]


@dataclass
class GuardConfig:
    mode:                Mode
    dry_run:             bool
    dry_run_expires_at:  datetime | None


# ── API pública ──────────────────────────────────────────────────────────────

def check(text: str | None) -> tuple[bool, str | None]:
    """
    Retorna ``(matched, pattern_label)``.

    ``text`` nullable: un None o vacío siempre retorna ``(False, None)``.
    """
    if not text:
        return False, None
    try:
        for rx, label in DESTRUCTIVE_PATTERNS:
            if rx.search(text):
                return True, label
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("[AutoEnterGuard] check falló: %s", exc)
    return False, None


def load_config() -> GuardConfig:
    """Lee ``auto_approve`` desde ``config.json`` y devuelve un ``GuardConfig``."""
    defaults = GuardConfig(mode="advisory", dry_run=True, dry_run_expires_at=None)
    try:
        with _CONFIG_LOCK:
            raw = _CONFIG_PATH.read_text(encoding="utf-8")
        data = json.loads(raw)
        section = data.get("auto_approve") or {}
    except FileNotFoundError:
        return defaults
    except Exception as exc:
        logger.debug("[AutoEnterGuard] no se pudo leer config.json: %s", exc)
        return defaults

    mode = section.get("mode", defaults.mode)
    if mode not in ("advisory", "blocking", "off"):
        mode = "advisory"

    dry_run = bool(section.get("dry_run", defaults.dry_run))

    expires: datetime | None = None
    raw_expires = section.get("dry_run_expires_at")
    if isinstance(raw_expires, str) and raw_expires:
        try:
            expires = datetime.fromisoformat(raw_expires.replace("Z", "+00:00"))
        except ValueError:
            expires = None

    return GuardConfig(mode=mode, dry_run=dry_run, dry_run_expires_at=expires)  # type: ignore[arg-type]


def ensure_defaults_persisted() -> GuardConfig:
    """
    Garantiza que ``config.json`` tenga la sección ``auto_approve`` con valores
    por defecto (mode=advisory, dry_run=True, expires=now+48h). Si ya existe,
    no la sobreescribe. Retorna el ``GuardConfig`` resultante.
    """
    with _CONFIG_LOCK:
        try:
            raw  = _CONFIG_PATH.read_text(encoding="utf-8")
            data = json.loads(raw)
        except Exception as exc:
            logger.debug("[AutoEnterGuard] no se pudo leer config.json: %s", exc)
            return load_config()

        changed = False
        section = data.get("auto_approve")
        if not isinstance(section, dict):
            section = {}
            data["auto_approve"] = section
            changed = True

        if "mode" not in section:
            section["mode"] = "advisory"
            changed = True
        if "dry_run" not in section:
            section["dry_run"] = True
            changed = True
        if "dry_run_expires_at" not in section:
            expires = datetime.now(timezone.utc) + timedelta(hours=48)
            section["dry_run_expires_at"] = expires.strftime("%Y-%m-%dT%H:%M:%SZ")
            changed = True

        if changed:
            try:
                tmp = _CONFIG_PATH.with_suffix(".json.tmp")
                tmp.write_text(
                    json.dumps(data, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
                tmp.replace(_CONFIG_PATH)
                logger.info("[AutoEnterGuard] config.json.auto_approve inicializado")
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("[AutoEnterGuard] no se pudo persistir config: %s", exc)

    return load_config()


def dry_run_expired(cfg: GuardConfig | None = None) -> bool:
    """
    Retorna True si ``dry_run=True`` y ``dry_run_expires_at`` ya pasó.
    Útil para que el daemon emita ``auto_enter_dry_run_expired``.
    """
    cfg = cfg or load_config()
    if not cfg.dry_run:
        return False
    if cfg.dry_run_expires_at is None:
        return False
    now = datetime.now(timezone.utc)
    expires = cfg.dry_run_expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    return now >= expires


def snippet(text: str | None, limit: int = 200) -> str:
    """Devuelve los primeros ``limit`` chars de ``text`` (o '')."""
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return text[:limit] + "..."
