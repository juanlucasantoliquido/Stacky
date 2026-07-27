"""Plan 215 F4 — runner de publish por solución (espejo del solution_builder del 201).

Reglas duras:
- argv SIEMPRE lista: el parseo jamas se delega al interprete de comandos del SO
  (la prosa evita nombrar el kwarg prohibido porque el criterio binario del plan
  es un grep sobre este archivo).
- Buffer de log PROPIO (shape LogEvent), NO el streamer de ejecuciones: un publish
  no es un `AgentExecution` y cerrar su stream rompe la FK (misma razon que 201 F5).
- C1: el timeout y el cancel NO dependen de que el proceso emita output. Un
  watchdog `threading.Timer` mata el árbol al vencer el plazo y `cancel()` lo mata
  en el momento; el reader ve EOF y sale.
- El publish escribe SIEMPRE en staging propio, jamás en el workspace del cliente.
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from runtime_paths import data_dir

logger = logging.getLogger(__name__)

_LOCK = threading.Lock()
_RUNS: dict = {}
_PUBLISH_TIMEOUT_SEC = 1800
_MAX_RETAINED_RUNS = 10
_ASSIST_LOG_TAIL = 120

# ADICIÓN ARQUITECTO 2 — clasificador determinista de fallos (sin LLM, 3/3 runtimes).
_FAILURE_PATTERNS = (
    (re.compile(r"error NU1\d{3}", re.I), "nuget_restore",
     "Fallo de restore NuGet (feed o paquete). Revisar NuGet.config / conectividad."),
    (re.compile(r"error MSB3644", re.I), "targeting_pack_missing",
     "Falta el targeting pack / SDK del framework objetivo."),
    (re.compile(r"error CS\d{4}", re.I), "compile_error",
     "Error de compilación C# (ver líneas 'error CS' del log)."),
    (re.compile(r"error MSB4126", re.I), "invalid_configuration",
     "Configuration/Platform inválida para esta solución — revisar 'configuration' en la config."),
    (re.compile(r"MSB4019|MSB4236", re.I), "missing_targets",
     "Faltan .targets/SDK de MSBuild (p. ej. WebApplication.targets) — suele requerir workload de VS."),
)


# ── Helpers de tiempo/paths (espejo 201 F5) ─────────────────────────────────

def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z"


def _ts() -> str:
    """Staging ÚNICO: dos publishes del mismo slug en el mismo segundo no colisionan."""
    return (datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            + "_" + uuid.uuid4().hex[:6])


def artifacts_root() -> Path:
    return data_dir() / "solution_publish_artifacts"


def _ledger_path() -> Path:
    return data_dir() / "solution_publish_runs.jsonl"


def _set(run_id: str, **fields) -> None:
    with _LOCK:
        entry = _RUNS.get(run_id)
        if entry is not None:
            entry.update(fields)


def _push(run_id: str, level: str, message: str) -> None:
    with _LOCK:
        entry = _RUNS.get(run_id)
        if entry is not None:
            entry["log"].append({"ts": _utcnow_iso(), "level": level, "message": message})


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


def classify_publish_failure(log_tail) -> dict | None:
    """Causa probable DETERMINISTA de un publish fallido, o None."""
    text = "\n".join(log_tail or [])
    for rx, code, hint in _FAILURE_PATTERNS:
        if rx.search(text):
            return {"code": code, "hint": hint}
    return None


def _ledger_append(payload: dict) -> None:
    try:
        path = _ledger_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:  # noqa: BLE001
        logger.warning("no se pudo escribir el ledger de publishes", exc_info=True)


def prune_old_publish_runs(scope_dir) -> None:
    """Conserva los `_MAX_RETAINED_RUNS` más nuevos del scope (dirs Y zips). Best-effort."""
    try:
        scope_dir = Path(scope_dir)
        subdirs = sorted((p for p in scope_dir.iterdir() if p.is_dir()),
                         key=lambda p: p.stat().st_mtime, reverse=True)
        for old in subdirs[_MAX_RETAINED_RUNS:]:
            shutil.rmtree(old, ignore_errors=True)
            zp = old.with_suffix(".zip")
            if zp.exists():
                zp.unlink(missing_ok=True)
    except OSError:
        pass


def _dir_stats(path) -> tuple:
    files = 0
    total = 0
    try:
        for dirpath, _dirnames, filenames in os.walk(str(path)):
            for fn in filenames:
                files += 1
                try:
                    total += os.path.getsize(os.path.join(dirpath, fn))
                except OSError:
                    pass
    except OSError:
        pass
    return files, total


def _build_argv(plan: dict, cfg: dict, toolchain: dict, staging_out: str) -> list:
    """argv COMPLETO. SIEMPRE lista — cero riesgo de quoting/inyeccion."""
    extra = list(cfg.get("extra_args") or [])
    mode = plan["mode_effective"]
    if mode == "dotnet_publish":
        return [toolchain["dotnet_path"]] + list(plan["argv_tail"]) + ["-o", staging_out] + extra
    if mode == "msbuild_pubxml":
        return ([toolchain["msbuild_path"]] + list(plan["argv_tail"])
                + ["/p:publishUrl=" + staging_out + os.sep] + extra)
    # build_only — espejo EXACTO de los comandos del 201 F5.
    if toolchain.get("builder") == "dotnet":
        return [toolchain["dotnet_path"], "build", plan["target"], "-c",
                cfg.get("configuration") or "Release", "-o", staging_out, "--nologo"] + extra
    return [toolchain["msbuild_path"], plan["target"], "/t:Build",
            "/p:Configuration=" + (cfg.get("configuration") or "Release"),
            "/p:OutDir=" + staging_out + os.sep, "/nologo"] + extra


def _write_summary(run_id: str) -> None:
    with _LOCK:
        run = dict(_RUNS.get(run_id) or {})
    base_dir = run.get("base_dir")
    if not base_dir:
        return
    try:
        out_dir = os.path.join(base_dir, "out")
        files, total = _dir_stats(out_dir)
        summary = {
            "run_id": run_id,
            "slug": run.get("slug"),
            "mode_effective": run.get("mode_effective"),
            "argv": run.get("argv") or [],
            "status": run.get("status"),
            "returncode": run.get("returncode"),
            "started_at": run.get("started_at"),
            "finished_at": run.get("finished_at"),
            "duration_sec": run.get("duration_sec"),
            "staging_dir": out_dir,
            "zip_path": run.get("zip_path"),
            "toolchain": run.get("toolchain") or {},
            "failure_class": run.get("failure_class"),
            "files": files,
            "bytes": total,
        }
        Path(base_dir).mkdir(parents=True, exist_ok=True)
        with open(os.path.join(base_dir, "publish.summary.json"), "w", encoding="utf-8") as fh:
            json.dump(summary, fh, indent=2, ensure_ascii=False)
        with open(os.path.join(base_dir, "publish.log"), "w", encoding="utf-8") as fh:
            for e in run.get("log") or []:
                fh.write(f"[{e.get('ts')}] {e.get('level')}: {e.get('message')}\n")
    except Exception:  # noqa: BLE001
        logger.warning("no se pudo escribir el summary/log del publish", exc_info=True)


def _finish(run_id: str, status: str, returncode=None, error=None) -> None:
    """NUNCA lanza. Summary + log + ledger `finished` + poda (SIEMPRE, C6)."""
    with _LOCK:
        run = _RUNS.get(run_id)
        if run is None:
            return
        run["status"] = status
        run["returncode"] = returncode
        run["error"] = error
        run["finished_at"] = _utcnow_iso()
        tail = [e.get("message", "") for e in (run.get("log") or [])][-_ASSIST_LOG_TAIL:]
        slug = run.get("slug")
        base_dir = run.get("base_dir")
    if status in ("failed", "unsupported"):
        fc = classify_publish_failure(tail)
        if fc:
            _set(run_id, failure_class=fc)
    _write_summary(run_id)
    with _LOCK:
        snap = dict(_RUNS.get(run_id) or {})
    _ledger_append({
        "event": "finished",
        "run_id": run_id,
        "slug": slug,
        "mode_effective": snap.get("mode_effective"),
        "status": status,
        "returncode": returncode,
        "zip_path": snap.get("zip_path"),
        "base_dir": base_dir,
        "workspace_root": snap.get("workspace_root"),
        "finished_at": snap.get("finished_at"),
        "duration_sec": snap.get("duration_sec"),
        "failure_class": snap.get("failure_class"),
    })
    # C6 — la poda corre SIEMPRE, no solo en success.
    if slug:
        prune_old_publish_runs(artifacts_root() / slug)


def _timeout_kill(run_id: str) -> None:
    """Corre en el thread del Timer. NUNCA lanza."""
    try:
        with _LOCK:
            run = _RUNS.get(run_id)
            if not run or run.get("status") != "running":
                return
            run["_timed_out"] = True
            proc = run.get("_proc")
        if proc is not None:
            _terminate_tree(proc)
    except Exception:  # noqa: BLE001
        logger.warning("watchdog de publish falló", exc_info=True)


def cancel(run_id: str) -> bool:
    """C1 — cancel INMEDIATO: bandera + matar el árbol YA (sin esperar output)."""
    with _LOCK:
        run = _RUNS.get(run_id)
        if not run or run.get("status") != "running":
            return False
        run["_cancel"] = True
        proc = run.get("_proc")
    if proc is not None:
        _terminate_tree(proc)
    return True


def _run(run_id: str, slug: str, workspace_root: str) -> None:
    from services import publish_config_store, publish_profile_scanner, solution_store
    from services.build_toolchain import detect_toolchain

    try:
        tc = detect_toolchain()
        _set(run_id, toolchain={k: tc.get(k) for k in ("available", "builder", "version")})
        sol = next((s for s in solution_store.load_catalog(workspace_root).get("solutions", [])
                    if s.get("slug") == slug), None)
        if sol is None or not os.path.exists(sol.get("sln_path", "")):
            _push(run_id, "error", "No se encontró la solución en el catálogo.")
            _finish(run_id, "failed", error="solucion_no_encontrada")
            return
        cfg = publish_config_store.load_config(workspace_root, slug)
        plan = publish_profile_scanner.resolve_publish_plan(sol, cfg, tc)
        _set(run_id, mode_effective=plan["mode_effective"])
        if not tc.get("available"):
            _push(run_id, "error", (tc.get("remediation") or {}).get("message")
                  or "Falta el toolchain .NET/MSBuild.")
            _finish(run_id, "toolchain_missing")
            return
        if not plan["supported"]:
            _push(run_id, "error", "Plan de publish no soportado: " + plan["reason"])
            _finish(run_id, "unsupported", error=plan["reason"])
            return

        base_dir = artifacts_root() / slug / _ts()
        staging_out = str(base_dir / "out")
        os.makedirs(staging_out, exist_ok=True)
        argv = _build_argv(plan, cfg, tc, staging_out)
        _set(run_id, argv=argv, base_dir=str(base_dir))
        _push(run_id, "info", "Publicando " + slug + " (" + plan["mode_effective"] + ")…")

        proc = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, encoding="utf-8", errors="replace",
                                cwd=os.path.dirname(plan["target"]) or None)
        _set(run_id, _proc=proc)
        watchdog = threading.Timer(_PUBLISH_TIMEOUT_SEC, _timeout_kill, args=(run_id,))
        watchdog.daemon = True
        watchdog.start()
        try:
            for line in proc.stdout:
                _push(run_id, "info", line.rstrip())
            proc.wait()
        finally:
            watchdog.cancel()

        with _LOCK:
            cancelled = bool(_RUNS.get(run_id, {}).get("_cancel"))
            timed_out = bool(_RUNS.get(run_id, {}).get("_timed_out"))
        if cancelled:
            _finish(run_id, "cancelled", returncode=proc.returncode)
            return
        if timed_out:
            _push(run_id, "error", f"timeout ({_PUBLISH_TIMEOUT_SEC}s) — proceso terminado por watchdog")
            _finish(run_id, "failed", returncode=proc.returncode, error="timeout")
            return
        status = "success" if proc.returncode == 0 else "failed"
        if status == "success":
            try:
                zip_path = shutil.make_archive(str(base_dir), "zip", root_dir=staging_out)
                _set(run_id, zip_path=zip_path)
            except OSError:
                logger.warning("no se pudo comprimir el artefacto", exc_info=True)
        _finish(run_id, status, returncode=proc.returncode)
    except Exception as exc:  # noqa: BLE001 — el thread NUNCA debe morir sin cerrar el run
        logger.warning("publish falló con excepción", exc_info=True)
        _push(run_id, "error", str(exc))
        _finish(run_id, "failed", error=str(exc))


def start_publish(slug: str, workspace_root: str) -> str:
    run_id = uuid.uuid4().hex
    with _LOCK:
        _RUNS[run_id] = {
            "status": "running", "slug": slug, "workspace_root": workspace_root,
            "log": [], "_cancel": False, "_timed_out": False, "_proc": None,
            "argv": [], "base_dir": None, "zip_path": None, "mode_effective": None,
            "started_at": _utcnow_iso(), "finished_at": None, "returncode": None,
            "error": None, "failure_class": None, "toolchain": {},
        }
    _ledger_append({"event": "started", "run_id": run_id, "slug": slug,
                    "workspace_root": workspace_root, "started_at": _utcnow_iso()})
    threading.Thread(target=_run, args=(run_id, slug, workspace_root), daemon=True).start()
    return run_id


def _ledger_entries() -> list:
    """Todas las líneas del ledger. Las corruptas se SALTAN con warning (C11)."""
    entries: list = []
    path = _ledger_path()
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for raw in fh:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    obj = json.loads(raw)
                except ValueError:
                    logger.warning("línea corrupta en el ledger de publishes; se salta")
                    continue
                if isinstance(obj, dict):
                    entries.append(obj)
    except OSError:
        return []
    return entries


def get_status(run_id: str):
    """Memoria primero; si no está, reconstruye del ledger. None = desconocido (404)."""
    with _LOCK:
        run = _RUNS.get(run_id)
        if run is not None:
            return {
                "run_id": run_id,
                "status": run.get("status"),
                "slug": run.get("slug"),
                "mode_effective": run.get("mode_effective"),
                "argv": list(run.get("argv") or []),
                "log": list(run.get("log") or []),
                "artifact_ready": bool(run.get("zip_path")),
                "error": run.get("error"),
                "failure_class": run.get("failure_class"),
                "returncode": run.get("returncode"),
            }
    for e in reversed(_ledger_entries()):
        if e.get("run_id") == run_id and e.get("event") == "finished":
            return {
                "run_id": run_id,
                "status": e.get("status"),
                "slug": e.get("slug"),
                "mode_effective": e.get("mode_effective"),
                "argv": [],
                "log": [],
                "artifact_ready": bool(e.get("zip_path")),
                "error": None,
                "failure_class": e.get("failure_class"),
                "returncode": e.get("returncode"),
            }
    return None


def artifact_zip_path(run_id: str):
    with _LOCK:
        run = _RUNS.get(run_id)
        if run is not None and run.get("zip_path"):
            return Path(run["zip_path"])
    for e in reversed(_ledger_entries()):
        if e.get("run_id") == run_id and e.get("event") == "finished" and e.get("zip_path"):
            return Path(e["zip_path"])
    return None


def list_runs(workspace_root: str, slug: str | None = None, limit: int = 20) -> list:
    """Historial del ledger, más nuevos primero. ADICIÓN 1: reconcilia `interrupted`."""
    started: dict = {}
    finished: dict = {}
    order: list = []
    for e in _ledger_entries():
        rid = e.get("run_id")
        if not rid:
            continue
        if e.get("event") == "started":
            started[rid] = e
            if rid not in order:
                order.append(rid)
        elif e.get("event") == "finished":
            finished[rid] = e
            if rid not in order:
                order.append(rid)

    out: list = []
    for rid in reversed(order):
        s = started.get(rid) or {}
        f = finished.get(rid) or {}
        ws = f.get("workspace_root") or s.get("workspace_root")
        if workspace_root and ws and ws != workspace_root:
            continue
        run_slug = f.get("slug") or s.get("slug")
        if slug and run_slug != slug:
            continue
        if f:
            status = f.get("status")
        else:
            # started sin finished: si no vive en memoria, el backend se reinició.
            with _LOCK:
                alive = rid in _RUNS
            status = "running" if alive else "interrupted"
        out.append({
            "run_id": rid,
            "slug": run_slug,
            "status": status,
            "mode_effective": f.get("mode_effective"),
            "started_at": s.get("started_at"),
            "finished_at": f.get("finished_at"),
            "duration_sec": f.get("duration_sec"),
            "artifact_ready": bool(f.get("zip_path")),
            "failure_class": f.get("failure_class"),
        })
        if len(out) >= max(1, int(limit or 20)):
            break
    return out


def build_assist_message(run: dict, cfg: dict, solution: dict, toolchain: dict) -> str:
    """Plan 215 F6 — contexto del asistente DevOps. C3: se enmascara el mensaje COMPLETO."""
    from services.secret_masking import mask_token_values

    run = run or {}
    cfg = cfg or {}
    solution = solution or {}
    toolchain = toolchain or {}
    lines = [
        "Necesito ayuda con la publicación de una solución (Publicador de Soluciones, Plan 215).",
        f"Solución: {solution.get('friendly_name')} ({solution.get('sln_path')})",
        f"Modo efectivo: {run.get('mode_effective')} | Estado: {run.get('status')} "
        f"| Returncode: {run.get('returncode')}",
        "Comando ejecutado (argv): " + json.dumps(run.get("argv") or [], ensure_ascii=False),
        "Config actual (data/publish_configs.json): " + json.dumps(cfg, ensure_ascii=False),
        "Toolchain: " + json.dumps(
            {k: toolchain.get(k) for k in ("available", "builder", "version")},
            ensure_ascii=False),
    ]
    if toolchain.get("remediation"):
        lines.append("Doctor: " + str((toolchain.get("remediation") or {}).get("message")))
    if run.get("failure_class"):
        fc = run["failure_class"]
        lines.append("Clasificación determinista del fallo: " + fc["code"] + " — " + fc["hint"])
    tail = [e.get("message", "") for e in (run.get("log") or [])][-_ASSIST_LOG_TAIL:]
    lines.append("Últimas líneas del log del publish:")
    lines.append("\n".join(tail))
    lines.append(
        "Diagnosticá la causa raíz y proponé la corrección EXACTA (por ejemplo el JSON de config "
        "corregido para esta solución, o el comando de instalación del toolchain). NO ejecutes nada: "
        "yo aplico los cambios desde la UI y confirmo con CONFIRMO si hace falta ejecutar algo."
    )
    # C3 — el masking cubre el mensaje COMPLETO (argv, config, doctor y tail incluidos).
    return mask_token_values("\n".join(lines))
