"""Plan 177 F2 — Diff del working tree + intent store en disco para el Auto-PR
del Dev Resolutor de Incidencias.

Dos responsabilidades:
1. Enumerar EXACTAMENTE qué archivos tocó el agente en el working tree del
   proyecto activo, vía snapshot ANTES del run + delta por HASH DESPUÉS (no barre
   los cambios dirty preexistentes del operador).
2. Persistir el "intent" del PR (consentimiento del checkbox + baseline + repo)
   keyeado por `execution_id` en disco — NO en `AgentExecution.metadata_json`, que
   el runner también escribe (evita la carrera de clobber, G9).

Todo local y read-only del working tree (ningún commit/stash/push acá). El git se
corre con el mismo endurecimiento no-interactivo de `pre_run_git._run_git`
(`credential.helper=` vacío, `GIT_TERMINAL_PROMPT=0`, `CREATE_NO_WINDOW` en Windows,
timeout) para que nunca cuelgue en un prompt.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import logging
import os
import subprocess
from pathlib import Path

logger = logging.getLogger("stacky.services.incident_dev_pr")

_MAX_FILE_HASH_BYTES = 8_000_000  # cap defensivo al hashear (archivos enormes)

# Chars válidos del campo XY del porcelain (para distinguir "XY PATH" de un
# path "pelado" que aparece como segundo token en un rename con -z).
_STATUS_CHARS = set(" MADRCU?!T")


# ── Runner git no-interactivo (espejo de pre_run_git._run_git) ────────────────

def _git(cwd: Path, args: list[str], *, timeout: int = 30) -> tuple[bool, str]:
    """Corre `git <args>` en `cwd`. Devuelve (ok, stdout). Nunca lanza ni cuelga."""
    cmd = ["git", "-c", "credential.helper=", "-c", "core.longpaths=true", *args]
    env = os.environ.copy()
    env.update({
        "GIT_TERMINAL_PROMPT": "0",
        "GCM_INTERACTIVE": "Never",
        "GIT_ASKPASS": "",
        "SSH_ASKPASS": "",
    })
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            env=env,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
        )
        return proc.returncode == 0, (proc.stdout or "")
    except (subprocess.TimeoutExpired, OSError) as exc:
        logger.info("incident_dev_pr._git falló (%s): %s", args[:2], exc)
        return False, ""


# ── Resolución de repo + remoto ───────────────────────────────────────────────

def resolve_repo_root(workspace_root: str | None) -> str | None:
    """Devuelve el toplevel del repo git que contiene `workspace_root`
    (que puede ser un SUBDIR del repo), o None si vacío / no es un repo git."""
    if not workspace_root:
        return None
    ws = Path(workspace_root)
    if not ws.exists():
        return None
    ok, out = _git(ws, ["rev-parse", "--show-toplevel"], timeout=15)
    if not ok:
        return None
    top = (out or "").strip()
    return top or None


def remote_origin_url(repo_root: str) -> str | None:
    """URL del remoto 'origin' del repo, o None (sin origin / no repo / vacío).
    [ADICIÓN ARQUITECTO] — insumo de la guardia de mapeo working-tree ↔ repo del
    tracker (F4) y de la anotación del origin en el PR."""
    if not repo_root:
        return None
    ok, out = _git(Path(repo_root), ["remote", "get-url", "origin"], timeout=15)
    if not ok:
        return None
    url = (out or "").strip()
    return url or None


# ── Snapshot + delta del working tree ─────────────────────────────────────────

def _sha1_file(path: Path) -> str:
    h = hashlib.sha1()  # noqa: S324 — sólo para detectar cambios, no criptográfico
    try:
        with path.open("rb") as fh:
            read = 0
            while True:
                chunk = fh.read(65536)
                if not chunk:
                    break
                read += len(chunk)
                if read > _MAX_FILE_HASH_BYTES:
                    h.update(chunk)
                    h.update(b"__truncated__")
                    break
                h.update(chunk)
    except OSError:
        return "__unreadable__"
    return h.hexdigest()


def _parse_porcelain_z(raw: str) -> set[str]:
    """Extrae el conjunto de paths (repo-relativos, POSIX) de la salida de
    `git status --porcelain -z -uall`. Maneja el token 'pelado' del rename."""
    paths: set[str] = set()
    for tok in raw.split("\x00"):
        if not tok:
            continue
        if len(tok) >= 3 and tok[2] == " " and tok[0] in _STATUS_CHARS and tok[1] in _STATUS_CHARS:
            path = tok[3:]
        else:
            path = tok  # path pelado (2do token de un rename con -z)
        if path:
            paths.add(path)
    return paths


def snapshot_worktree(repo_root: str) -> dict:
    """{'head': <sha o ''>, 'entries': {rel_posix: sha1 | '__deleted__'}} de TODOS
    los archivos dirty+untracked del working tree. Read-only."""
    root = Path(repo_root)
    ok_head, head_out = _git(root, ["rev-parse", "HEAD"], timeout=15)
    head_sha = (head_out or "").strip() if ok_head else ""
    ok, out = _git(root, ["status", "--porcelain", "-z", "-uall"], timeout=60)
    entries: dict[str, str] = {}
    if ok and out:
        for rel in _parse_porcelain_z(out):
            full = root / rel
            entries[rel] = _sha1_file(full) if full.is_file() else "__deleted__"
    return {"head": head_sha, "entries": entries}


def compute_changed_files(baseline: dict, current: dict) -> dict:
    """Delta por HASH: qué tocó ESTE run. Excluye lo dirty preexistente intacto.
    → {'added_or_modified': [rel...], 'deleted': [rel...]} (ordenados)."""
    base_entries = (baseline or {}).get("entries", {}) or {}
    cur_entries = (current or {}).get("entries", {}) or {}
    added_or_modified: list[str] = []
    deleted: list[str] = []
    for path, sha in cur_entries.items():
        if sha == "__deleted__":
            if base_entries.get(path) != "__deleted__":
                deleted.append(path)
        elif base_entries.get(path) != sha:
            added_or_modified.append(path)
    return {"added_or_modified": sorted(added_or_modified), "deleted": sorted(deleted)}


# ── Clasificación código vs tests (cierra K2) ─────────────────────────────────

def _is_test_path(p: str) -> bool:
    pl = p.lower()
    base = pl.rsplit("/", 1)[-1]
    if base.startswith("test_") and base.endswith(".py"):
        return True
    if base.endswith("_test.py"):
        return True
    if ".test." in base or ".spec." in base:
        return True
    padded = "/" + pl
    return any(seg in padded for seg in ("/tests/", "/__tests__/", "/test/"))


def classify_changed_files(paths: list[str]) -> dict:
    """{'code': [...], 'tests': [...]} — los tests viajan explícitos en el PR (K2)."""
    code: list[str] = []
    tests: list[str] = []
    for p in paths:
        (tests if _is_test_path(p) else code).append(p)
    return {"code": sorted(code), "tests": sorted(tests)}


# ── Intent store en disco (keyeado por execution_id; espejo de incident_store) ─

def _intent_dir() -> Path:
    from runtime_paths import data_dir  # noqa: PLC0415
    d = data_dir() / "incident_dev_pr"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _intent_path(execution_id: int) -> Path:
    return _intent_dir() / f"{int(execution_id)}.json"


def record_intent(execution_id: int, intent: dict) -> None:
    """Escribe atómico (tmp + replace) el intent del PR keyeado por execution_id."""
    data = dict(intent or {})
    data.setdefault("created_at", datetime.datetime.now(datetime.timezone.utc).isoformat())
    path = _intent_path(execution_id)
    tmp = path.parent / (path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def get_intent(execution_id: int) -> dict | None:
    path = _intent_path(execution_id)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def mark_intent(execution_id: int, **fields) -> None:
    """Merge idempotente de campos de resultado (pr_id, pr_url, branch, status,
    error, files_committed, origin, ...) sobre el intent existente."""
    cur = get_intent(execution_id) or {}
    cur.update(fields)
    record_intent(execution_id, cur)
