"""Plan 215 F2 — config de publish por (workspace_root, slug).

Persistencia idempotente en data/publish_configs.json con defaults sintetizados
(nunca hace falta configurar nada para publicar — G1) y validacion DURA de
`extra_args` (allowlist sin espacios ni metacaracteres — G6; el argv siempre es
lista, jamas shell).
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
from datetime import datetime, timezone
from pathlib import Path

from runtime_paths import data_dir

logger = logging.getLogger(__name__)

_LOCK = threading.Lock()

_MODES = ("auto", "dotnet_publish", "msbuild_pubxml", "build_only")
_CONFIGURATION_RE = re.compile(r"^[A-Za-z0-9._\-]{1,40}$")
_EXTRA_ARG_RE = re.compile(r"^[A-Za-z0-9/:=._,()\\\-]{1,120}$")
_PUBLISH_PROFILE_RE = re.compile(r"^[A-Za-z0-9._\- ]{1,80}$")
_MAX_EXTRA_ARGS = 8


def store_path() -> Path:
    return data_dir() / "publish_configs.json"


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_doc() -> dict:
    path = store_path()
    try:
        with open(path, "r", encoding="utf-8") as fh:
            doc = json.load(fh)
    except (OSError, ValueError) as exc:
        if os.path.exists(path):
            logger.warning("publish_configs.json ilegible/corrupto (%s); se usa {}", exc)
        return {}
    return doc if isinstance(doc, dict) else {}


def _save_doc(doc: dict) -> None:
    path = store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = str(path) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def default_config() -> dict:
    return {
        "mode": "auto",
        "configuration": "Release",
        "project_csproj": None,
        "publish_profile": None,
        "extra_args": [],
        "register_as_deploy_app": False,
        "updated_at": None,
    }


def validate_config(cfg: dict) -> list:
    """Lista de errores legibles; [] = valida."""
    cfg = cfg or {}
    errors: list = []
    if cfg.get("mode") not in _MODES:
        errors.append("mode inválido")
    if not _CONFIGURATION_RE.match(str(cfg.get("configuration") or "")):
        errors.append("configuration inválida")
    pc = cfg.get("project_csproj")
    if pc is not None and (
        not isinstance(pc, str) or not pc.lower().endswith((".csproj", ".vbproj"))
    ):
        errors.append("project_csproj debe ser .csproj/.vbproj o null")
    pp = cfg.get("publish_profile")
    if pp is not None and (not isinstance(pp, str) or not _PUBLISH_PROFILE_RE.match(pp)):
        errors.append("publish_profile inválido")
    extra = cfg.get("extra_args")
    if (
        not isinstance(extra, list)
        or len(extra) > _MAX_EXTRA_ARGS
        or any(not isinstance(a, str) or not _EXTRA_ARG_RE.match(a) for a in extra)
    ):
        errors.append("extra_args inválidos (máx 8; sin espacios ni ;|&<>\"')")
    if not isinstance(cfg.get("register_as_deploy_app"), bool):
        errors.append("register_as_deploy_app debe ser bool")
    return errors


def load_config(workspace_root: str, slug: str) -> dict:
    """SIEMPRE un dict completo: la guardada, o el default sintetizado."""
    doc = _load_doc()
    block = doc.get(os.path.normpath(workspace_root or "")) or {}
    saved = block.get(slug)
    cfg = default_config()
    if isinstance(saved, dict):
        cfg.update({k: v for k, v in saved.items() if k in cfg})
    return cfg


def save_config(workspace_root: str, slug: str, cfg: dict) -> dict:
    """Mergea sobre el default, valida y persiste. ValueError si es invalida."""
    merged = default_config()
    merged.update({k: v for k, v in (cfg or {}).items() if k in merged})
    errors = validate_config(merged)
    if errors:
        raise ValueError("; ".join(errors))
    merged["updated_at"] = _utcnow_iso()
    root = os.path.normpath(workspace_root or "")
    with _LOCK:
        doc = _load_doc()
        block = doc.get(root) or {}
        block[slug] = merged
        doc[root] = block
        _save_doc(doc)
    return merged
