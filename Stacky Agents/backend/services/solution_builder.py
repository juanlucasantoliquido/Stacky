"""Plan 201 F5 — Builder de soluciones en Release.

Compila una `.sln` a una carpeta de staging, con log vivo, timeout y cancelación.
El comando SIEMPRE se arma como lista de argumentos (nunca un string de shell):
así las rutas con espacios, acentos y backslashes finales son seguras.

El log vive en un buffer propio en memoria, NO en el servicio de logs de
ejecuciones: ese persiste filas `ExecutionLog(execution_id=...)` contra la tabla
de ejecuciones, y un build NO es un `AgentExecution` — sería una FK inválida. Se
reusa su *shape* de evento (`{ts, level, message}`), no su acople a la base.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from runtime_paths import data_dir
from services import solution_store
from services.build_toolchain import detect_toolchain

logger = logging.getLogger(__name__)

_BUILD_TIMEOUT_SEC = 1800    # 30 min; la cancelación manual es la garantía primaria
_MAX_RETAINED_BUILDS = 10    # builds retenidos por <slug> (y por 'unified')

_LOCK = threading.Lock()
_BUILDS: dict = {}


# ── Helpers de tiempo/paths ──────────────────────────────────────────────────

def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z"


def _ts() -> str:
    """Timestamp de staging ÚNICO: dos builds del mismo slug en el mismo segundo
    (doble click) no pueden colisionar."""
    return (datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            + "_" + uuid.uuid4().hex[:6])


def artifacts_root() -> Path:
    return data_dir() / "build_artifacts"


def _ledger_path() -> Path:
    return data_dir() / "build_runs.jsonl"


# ── Registro en memoria ──────────────────────────────────────────────────────

def _set(build_id: str, **fields) -> None:
    with _LOCK:
        entry = _BUILDS.get(build_id)
        if entry is not None:
            entry.update(fields)


def _push(build_id: str, level: str, message: str) -> None:
    with _LOCK:
        entry = _BUILDS.get(build_id)
        if entry is not None:
            entry["log"].append({"ts": _utcnow_iso(), "level": level, "message": message})


def _is_cancelled(build_id: str) -> bool:
    with _LOCK:
        entry = _BUILDS.get(build_id)
        return bool(entry and entry.get("_cancel"))


# ── Build ────────────────────────────────────────────────────────────────────

def _sln_path_for_slug(slug: str, workspace_root: str):
    for s in solution_store.load_catalog(workspace_root).get("solutions", []):
        if s.get("slug") == slug:
            return s.get("sln_path")
    return None


def _build_args(toolchain: dict, sln_path: str, staging_dir: str) -> list:
    """Argumentos del build en Release. SIEMPRE lista: cero riesgo de quoting."""
    if toolchain.get("builder") == "dotnet":
        return [toolchain["dotnet_path"], "build", sln_path, "-c", "Release",
                "-o", staging_dir, "--nologo"]
    return [toolchain["msbuild_path"], sln_path, "/t:Build",
            "/p:Configuration=Release", "/p:OutDir=" + staging_dir + os.sep, "/nologo"]


def _terminate_tree(proc) -> None:
    """Mata el proceso y sus hijos (MSBuild deja nodos). Nunca lanza."""
    try:
        proc.terminate()
    except Exception:  # noqa: BLE001
        logger.debug("terminate falló", exc_info=True)
    if os.name == "nt":
        try:
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                           capture_output=True, timeout=15)
        except Exception:  # noqa: BLE001
            logger.debug("taskkill best-effort falló", exc_info=True)


def _run_one(build_id: str, slug: str, workspace_root: str, base_dir: Path):
    """Compila un slug. Devuelve 'success' | 'failed' | None (abortado)."""
    toolchain = detect_toolchain()
    if not toolchain.get("available"):
        _set(build_id, status="toolchain_missing")
        _push(build_id, "error", (toolchain.get("remediation") or {}).get(
            "message", "Toolchain de build no disponible."))
        return None

    sln = _sln_path_for_slug(slug, workspace_root)
    if not sln or not os.path.exists(sln):
        _push(build_id, "error", f"Solución no encontrada: {slug}")
        return "failed"

    staging = base_dir / slug
    staging.mkdir(parents=True, exist_ok=True)
    args = _build_args(toolchain, sln, str(staging))
    _push(build_id, "info", f"Compilando {slug} en Release…")

    try:
        proc = subprocess.Popen(
            args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            encoding="utf-8", errors="replace", cwd=os.path.dirname(sln),
        )
    except OSError as exc:
        _push(build_id, "error", f"No se pudo lanzar el build: {exc}")
        return "failed"

    _set(build_id, _proc=proc)
    try:
        if proc.stdout is not None:
            for line in proc.stdout:
                if _is_cancelled(build_id):
                    _terminate_tree(proc)
                    _set(build_id, status="cancelled")
                    return None
                _push(build_id, "info", line.rstrip())
        proc.wait(timeout=_BUILD_TIMEOUT_SEC)
    except subprocess.TimeoutExpired:
        _terminate_tree(proc)
        _push(build_id, "error", f"timeout: el build superó {_BUILD_TIMEOUT_SEC}s")
        return "failed"
    except Exception as exc:  # noqa: BLE001
        _terminate_tree(proc)
        _push(build_id, "error", f"Error inesperado durante el build: {exc}")
        return "failed"

    if proc.returncode != 0:
        _push(build_id, "error", f"{slug}: returncode {proc.returncode}")
        return "failed"
    return "success"


def _dir_stats(path: Path) -> tuple:
    files = 0
    total = 0
    try:
        for root, _dirs, names in os.walk(path):
            for name in names:
                files += 1
                try:
                    total += os.path.getsize(os.path.join(root, name))
                except OSError:
                    pass
    except OSError:
        pass
    return files, total


def _write_summary(build_id: str, base_dir: Path, returncodes: dict, toolchain: dict) -> None:
    """Evidencia determinista del build. Se escribe SIEMPRE (aun en failed)."""
    try:
        with _LOCK:
            entry = dict(_BUILDS.get(build_id) or {})
        started = entry.get("started_at")
        finished = entry.get("finished_at") or _utcnow_iso()
        duration = None
        try:
            t0 = datetime.fromisoformat((started or "").rstrip("Z"))
            t1 = datetime.fromisoformat(finished.rstrip("Z"))
            duration = round((t1 - t0).total_seconds(), 3)
        except (TypeError, ValueError):
            duration = None

        artifacts = []
        for slug in entry.get("slugs") or []:
            slug_dir = base_dir / slug
            files, total = _dir_stats(slug_dir)
            artifacts.append({"slug": slug, "dir": str(slug_dir),
                              "files": files, "bytes": total})

        summary = {
            "build_id": build_id,
            "mode": entry.get("mode"),
            "status": entry.get("status"),
            "slugs": list(entry.get("slugs") or []),
            "toolchain": {"builder": toolchain.get("builder"),
                          "version": toolchain.get("version")},
            "started_at": started,
            "finished_at": finished,
            "duration_sec": duration,
            "artifacts": artifacts,
            "returncodes": dict(returncodes),
            "base_dir": str(base_dir),
            "zip_path": entry.get("zip_path"),
        }
        base_dir.mkdir(parents=True, exist_ok=True)
        (base_dir / "build.summary.json").write_text(
            json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8", errors="replace"
        )
    except Exception:  # noqa: BLE001 — la evidencia nunca tumba el build
        logger.warning("no se pudo escribir build.summary.json", exc_info=True)


def _append_ledger(build_id: str) -> None:
    try:
        with _LOCK:
            entry = dict(_BUILDS.get(build_id) or {})
        path = _ledger_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps({
            "build_id": build_id,
            "mode": entry.get("mode"),
            "slugs": list(entry.get("slugs") or []),
            "status": entry.get("status"),
            "base_dir": entry.get("base_dir"),
            "zip_path": entry.get("zip_path"),
            "finished_at": entry.get("finished_at"),
        }, ensure_ascii=False)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except Exception:  # noqa: BLE001
        logger.warning("no se pudo escribir el ledger de builds", exc_info=True)


def prune_old_builds(scope_dir) -> None:
    """Conserva los `_MAX_RETAINED_BUILDS` builds más nuevos del scope. Best-effort."""
    try:
        scope_dir = Path(scope_dir)
        subdirs = sorted((p for p in scope_dir.iterdir() if p.is_dir()),
                         key=lambda p: p.stat().st_mtime, reverse=True)
        for old in subdirs[_MAX_RETAINED_BUILDS:]:
            shutil.rmtree(old, ignore_errors=True)
            zp = old.with_suffix(".zip")
            if zp.exists():
                zp.unlink(missing_ok=True)
    except OSError:
        pass


def _run_all(build_id: str, slugs: list, unified: bool, workspace_root: str,
             base_dir: Path) -> None:
    returncodes: dict = {}
    toolchain = detect_toolchain()
    peor = "success"
    for slug in slugs:
        if _is_cancelled(build_id):
            break
        result = _run_one(build_id, slug, workspace_root, base_dir)
        returncodes[slug] = 0 if result == "success" else 1
        if result is None:
            peor = None  # toolchain_missing o cancelled: el status ya quedó seteado
            break
        if result == "failed":
            peor = "failed"

    with _LOCK:
        entry = _BUILDS.get(build_id) or {}
        estado_actual = entry.get("status")
    if peor is not None and estado_actual == "running":
        _set(build_id, status=peor)

    _set(build_id, finished_at=_utcnow_iso())

    with _LOCK:
        estado_final = (_BUILDS.get(build_id) or {}).get("status")

    if estado_final == "success":
        try:
            zip_path = shutil.make_archive(str(base_dir), "zip", root_dir=str(base_dir))
            _set(build_id, zip_path=zip_path)
        except Exception:  # noqa: BLE001
            logger.warning("no se pudo generar el zip del build", exc_info=True)
            _push(build_id, "error", "No se pudo empaquetar el artefacto (.zip)")

    try:
        with _LOCK:
            log_lines = [f"[{e['ts']}] {e['level']}: {e['message']}"
                         for e in (_BUILDS.get(build_id) or {}).get("log", [])]
        base_dir.mkdir(parents=True, exist_ok=True)
        (base_dir / "build.log").write_text("\n".join(log_lines), encoding="utf-8",
                                            errors="replace")
    except Exception:  # noqa: BLE001
        logger.debug("no se pudo volcar build.log", exc_info=True)

    _write_summary(build_id, base_dir, returncodes, toolchain)
    _append_ledger(build_id)
    prune_old_builds(base_dir.parent)


# ── API pública ──────────────────────────────────────────────────────────────

def start_build(slugs: list, unified: bool, workspace_root: str) -> str:
    """Arranca el build en un hilo daemon y devuelve el build_id de inmediato."""
    build_id = uuid.uuid4().hex
    stamp = _ts()
    scope = "unified" if unified else (slugs[0] if slugs else "unknown")
    base_dir = artifacts_root() / scope / stamp
    base_dir.mkdir(parents=True, exist_ok=True)

    with _LOCK:
        _BUILDS[build_id] = {
            "status": "running",
            "mode": "unified" if unified else "single",
            "slugs": list(slugs),
            "base_dir": str(base_dir),
            "zip_path": None,
            "log": [],
            "started_at": _utcnow_iso(),
            "finished_at": None,
            "error": None,
            "_proc": None,
            "_cancel": False,
        }

    thread = threading.Thread(
        target=_run_all, args=(build_id, list(slugs), bool(unified), workspace_root, base_dir),
        name=f"build-{build_id[:8]}", daemon=True,
    )
    thread.start()
    return build_id


def _summary_from_disk(base_dir):
    try:
        path = Path(base_dir) / "build.summary.json"
        if path.is_file():
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else None
    except Exception:  # noqa: BLE001
        logger.debug("build.summary.json ilegible", exc_info=True)
    return None


def get_status(build_id: str):
    """Sobre de estado del build, o None si el build_id es desconocido."""
    with _LOCK:
        entry = _BUILDS.get(build_id)
        if entry is None:
            return None
        snapshot = {
            "status": entry.get("status"),
            "mode": entry.get("mode"),
            "slugs": list(entry.get("slugs") or []),
            "log": list(entry.get("log") or []),
            "error": entry.get("error"),
            "base_dir": entry.get("base_dir"),
            "zip_path": entry.get("zip_path"),
        }
    terminal = snapshot["status"] != "running"
    snapshot["artifact_ready"] = bool(snapshot["zip_path"]) and terminal
    # `summary` es null mientras corre: el JSON se escribe recién al terminar.
    snapshot["summary"] = _summary_from_disk(snapshot["base_dir"]) if terminal else None
    return snapshot


def cancel(build_id: str) -> bool:
    with _LOCK:
        entry = _BUILDS.get(build_id)
        if entry is None or entry.get("status") != "running":
            return False
        entry["_cancel"] = True
        proc = entry.get("_proc")
    if proc is not None:
        _terminate_tree(proc)
    _push(build_id, "info", "Cancelación solicitada por el operador.")
    return True


def _ledger_entry(build_id: str):
    try:
        path = _ledger_path()
        if not path.is_file():
            return None
        for line in reversed(path.read_text(encoding="utf-8").splitlines()):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict) and row.get("build_id") == build_id:
                return row
    except Exception:  # noqa: BLE001
        logger.debug("ledger de builds ilegible", exc_info=True)
    return None


def artifact_zip_path(build_id: str):
    """Ruta del zip del build. `build_id` es una CLAVE, jamás parte de una ruta."""
    with _LOCK:
        entry = _BUILDS.get(build_id)
        zip_path = entry.get("zip_path") if entry else None
    if not zip_path:
        row = _ledger_entry(build_id)
        zip_path = (row or {}).get("zip_path")
    return Path(zip_path) if zip_path else None


def artifact_dir_for(build_id: str, slug: str):
    """Carpeta con los BITS REALES del slug (no el zip ni el padre)."""
    with _LOCK:
        entry = _BUILDS.get(build_id)
        base_dir = entry.get("base_dir") if entry else None
    if not base_dir:
        row = _ledger_entry(build_id)
        base_dir = (row or {}).get("base_dir")
    if not base_dir:
        return None
    candidate = Path(base_dir) / slug
    return candidate if candidate.exists() else None
