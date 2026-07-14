"""services/deploy_executor.py — Plan 120 F4. Ejecuta planes de deploy/rollback.

Local y WinRM comparten la MISMA interfaz de transporte (paridad de pasos):
`run(command, *, timeout_s, read_only, run_id=None) -> dict` y
`push_file(local_path, remote_path, *, timeout_s, run_id=None) -> dict`.

El gating de flags (STACKY_DEPLOYMENTS_ENABLED / _EXECUTE_ENABLED) se aplica
UNA sola vez, acá en el executor — NO dentro de LocalTransport — para que
ambos transportes respeten las mismas reglas (WinRMTransport además las
vuelve a chequear dentro de remote_exec.run_deploy_step, redundante pero
inofensivo).
"""
from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
import threading
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from runtime_paths import data_dir
from services import deploy_planner as planner
from services import deploy_store as store

MAX_ARTIFACT_MB = planner.MAX_ARTIFACT_MB
_STEP_TIMEOUT_S = 120
_REMOTE_PATH_RE = re.compile(r"^[A-Za-z]:\\")


# ── artefacto ────────────────────────────────────────────────────────────────

def build_artifact_zip(app: dict) -> dict:
    artifact = app.get("artifact") or {}
    kind = artifact.get("kind")
    src = Path(artifact.get("path") or "")
    staging_dir = data_dir() / "deploy_staging"
    staging_dir.mkdir(parents=True, exist_ok=True)
    zip_path = staging_dir / f"{app.get('id')}.zip"

    if kind == "zip":
        if not src.is_file():
            raise ValueError(f"artefacto zip no encontrado: {src}")
        shutil.copy2(src, zip_path)
    elif kind == "folder":
        if not src.is_dir():
            raise ValueError(f"carpeta de artefacto no encontrada: {src}")
        if zip_path.exists():
            zip_path.unlink()
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for file_path in src.rglob("*"):
                if file_path.is_file():
                    zf.write(file_path, file_path.relative_to(src))
    else:
        raise ValueError(f"artifact.kind desconocido: {kind!r}")

    size_mb = zip_path.stat().st_size / (1024 * 1024)
    if size_mb > MAX_ARTIFACT_MB:
        raise ValueError(f"artefacto de {size_mb:.1f} MB supera el tope de {MAX_ARTIFACT_MB} MB")

    hasher = hashlib.sha256()
    with open(zip_path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            hasher.update(chunk)
    return {"zip_path": str(zip_path), "sha256": hasher.hexdigest(), "size_mb": round(size_mb, 2)}


# ── gating (Plan 120, único punto de verdad para ambos transportes) ────────

def _deployments_gate_error(read_only: bool) -> str | None:
    import config as _config
    cfg = _config.config
    if not getattr(cfg, "STACKY_DEPLOYMENTS_ENABLED", False):
        return "deployments_disabled"
    if not read_only and not getattr(cfg, "STACKY_DEPLOYMENTS_EXECUTE_ENABLED", False):
        return "deployments_execute_disabled"
    return None


# ── transportes ──────────────────────────────────────────────────────────────

class LocalTransport:
    """Ejecuta EN la máquina del backend (destino `__local__`)."""

    def run(self, command: str, *, timeout_s: int = _STEP_TIMEOUT_S, read_only: bool = False,
            run_id: str | None = None) -> dict:
        start = time.time()
        try:
            result = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
                capture_output=True, text=True, timeout=timeout_s,
            )
            ok = result.returncode == 0
            return {
                "ok": ok, "error": None if ok else "local_exec_error",
                "stdout": result.stdout or "", "stderr": result.stderr or "",
                "exit_code": result.returncode, "duration_ms": int((time.time() - start) * 1000),
            }
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": "timeout", "stdout": "", "stderr": "",
                    "exit_code": None, "duration_ms": int((time.time() - start) * 1000)}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": "local_exec_error", "stdout": "", "stderr": str(e),
                    "exit_code": None, "duration_ms": int((time.time() - start) * 1000)}

    def push_file(self, local_path: str, remote_path: str, *, timeout_s: int = _STEP_TIMEOUT_S,
                  run_id: str | None = None) -> dict:
        if '"' in (remote_path or "") or not _REMOTE_PATH_RE.match(remote_path or ""):
            return {"ok": False, "error": "invalid_remote_path"}
        p = Path(local_path)
        if not p.is_file():
            return {"ok": False, "error": "local_file_not_found"}
        dest = Path(remote_path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, dest)
        return {"ok": True, "error": None}


class WinRMTransport:
    """Delega en `services.remote_exec` (Plan 120 F2). `alias` = target_key."""

    def __init__(self, alias: str):
        self.alias = alias

    def run(self, command: str, *, timeout_s: int = _STEP_TIMEOUT_S, read_only: bool = False,
            run_id: str | None = None) -> dict:
        from services.remote_exec import run_deploy_step
        return run_deploy_step(self.alias, command, timeout_s=timeout_s, read_only=read_only, run_id=run_id)

    def push_file(self, local_path: str, remote_path: str, *, timeout_s: int = _STEP_TIMEOUT_S,
                  run_id: str | None = None) -> dict:
        from services.remote_exec import push_file_winrm
        return push_file_winrm(self.alias, local_path, remote_path, timeout_s=timeout_s, run_id=run_id)


def make_transport(target_key: str):
    return LocalTransport() if target_key == "__local__" else WinRMTransport(target_key)


# ── ejecución de un plan ─────────────────────────────────────────────────────

def _dispatch_prune(transport, install_path: str, retain: int, current_version: str | None, run_id: str):
    listing = transport.run(
        f"Get-ChildItem -LiteralPath '{install_path}\\releases' -Name",
        timeout_s=_STEP_TIMEOUT_S, read_only=True, run_id=run_id,
    )
    if not listing.get("ok"):
        return False, listing.get("error") or "prune_list_failed"
    existing = [ln.strip() for ln in (listing.get("stdout") or "").splitlines() if ln.strip()]
    to_delete = planner.prune_versions(existing, retain, current_version)
    for v in to_delete:
        res = transport.run(
            f'cmd /c rmdir /S /Q "{install_path}\\releases\\{v}"',
            timeout_s=_STEP_TIMEOUT_S, read_only=False, run_id=run_id,
        )
        if not res.get("ok"):
            return False, f"no se pudo borrar {v}: {res.get('error')}"
    return True, f"borradas: {len(to_delete)}"


def execute_plan(
    run_id: str,
    app: dict,
    target_key: str,
    plan: list[dict],
    transport,
    *,
    version_id: str,
    action: str = "deploy",
    zip_local: str | None = None,
    retain: int = 3,
    prev_version_id: str | None = None,
    source: dict | None = None,
) -> dict:
    """SÍNCRONO: recorre `plan` paso a paso, persistiendo progreso en el
    ledger tras cada paso. Cero falsos verdes: solo `success` si TODOS los
    pasos de ACTIVACIÓN (hasta `smoke` inclusive) ok=true. `housekeeping`
    (prune/cleanup) fallido se registra `ok:false` SIN degradar el status."""
    target_cfg = (app.get("targets") or {}).get(target_key) or {}
    install_path = target_cfg.get("install_path", "")
    started_at = datetime.now(timezone.utc).isoformat()

    entry = {
        "run_id": run_id, "app_id": app.get("id"), "target": target_key, "action": action,
        "version_id": version_id, "prev_version_id": prev_version_id,
        "status": "running", "steps": [], "source": source, "smoke": None,
        "operator_confirmed": True, "started_at": started_at, "finished_at": None,
        "duration_ms": None, "error": None, "insight": None,
    }
    store.append_ledger(entry)

    steps_log: list[dict] = []
    final_status = "success"
    error_detail = None

    for step in plan:
        name = step["name"]
        command = step.get("command")
        t0 = time.time()

        gate_err = _deployments_gate_error(step["read_only"])
        if gate_err is not None:
            ok, detail = False, gate_err
        elif name == "transfer":
            result = transport.push_file(
                zip_local, f"{install_path}\\incoming\\{version_id}.zip",
                timeout_s=_STEP_TIMEOUT_S, run_id=run_id,
            )
            ok, detail = bool(result.get("ok")), (result.get("error") or "")
        elif name == "prune":
            ok, detail = _dispatch_prune(transport, install_path, retain, version_id, run_id)
        elif command is None:
            # p.ej. "preflight": paso informativo, ya validado en /plan (F5). Sin efectos.
            ok, detail = True, "informativo (sin acción)"
        else:
            result = transport.run(command, timeout_s=_STEP_TIMEOUT_S, read_only=step["read_only"], run_id=run_id)
            ok = bool(result.get("ok"))
            detail = result.get("stderr") or result.get("error") or ""
            if name == "smoke":
                smoke_kind = (target_cfg.get("smoke") or {}).get("kind")
                if smoke_kind == "http":
                    code = planner.parse_smoke_http_stdout(result.get("stdout") or "")
                    ok = planner.smoke_http_ok(code)
                    detail = f"status={code}"
                entry["smoke"] = {"kind": smoke_kind, "ok": ok, "detail": str(detail)[:300]}

        steps_log.append({
            "name": name, "ok": ok, "ms": int((time.time() - t0) * 1000),
            "detail": str(detail)[:500],
        })
        store.update_ledger_entry(run_id, {"steps": steps_log, "smoke": entry.get("smoke")})

        if not ok:
            if step.get("housekeeping"):
                continue  # C2 v2 — housekeeping fallido NO degrada el status
            final_status = "failed_smoke" if name == "smoke" else "failed"
            error_detail = f"{name}: {detail}"
            break

    finished_at = datetime.now(timezone.utc).isoformat()
    started_dt = datetime.fromisoformat(started_at)
    finished_dt = datetime.fromisoformat(finished_at)
    patch = {
        "status": final_status,
        "steps": steps_log,
        "smoke": entry.get("smoke"),
        "finished_at": finished_at,
        "duration_ms": int((finished_dt - started_dt).total_seconds() * 1000),
        "error": error_detail,
    }
    store.update_ledger_entry(run_id, patch)
    entry.update(patch)
    return entry


# ── orquestación async (C5 v2) ───────────────────────────────────────────────

def _smoke_timeout_s() -> int:
    import config as _config
    return int(getattr(_config.config, "STACKY_DEPLOYMENTS_SMOKE_TIMEOUT_SEC", 30))


def start_deploy_async(app: dict, target_keys: list[str], plans: dict[str, dict]) -> list[dict]:
    """C5 v2: (1) adquiere UPFRONT el lock de CADA destino pedido — los
    ocupados NO se ejecutan; (2) con los libres, UN thread por ORDEN itera
    los destinos EN el orden recibido (olas), liberando cada lock en
    `finally`; (3) devuelve la lista por destino (run_id o error).
    `plans[target_key]` = {"plan", "version_id", "zip_local"?, "retain"?,
    "prev_version_id"?, "source"?}."""
    app_id = app.get("id")
    acquired: list[tuple[str, str]] = []
    results: list[dict] = []
    for tk in target_keys:
        run_id = store.acquire_run_lock(app_id, tk)
        if run_id is None:
            results.append({"target": tk, "error": "deploy_in_progress"})
        else:
            acquired.append((tk, run_id))
            results.append({"target": tk, "run_id": run_id})

    if acquired:
        def _worker():
            for tk, run_id in acquired:
                ctx = plans[tk]
                transport = make_transport(tk)
                try:
                    execute_plan(
                        run_id, app, tk, ctx["plan"], transport,
                        version_id=ctx["version_id"], zip_local=ctx.get("zip_local"),
                        retain=ctx.get("retain", 3), prev_version_id=ctx.get("prev_version_id"),
                        source=ctx.get("source"),
                    )
                finally:
                    store.release_run_lock(app_id, tk)

        threading.Thread(target=_worker, daemon=True).start()

    return results


def start_rollback_async(app: dict, target_key: str, to_version: str) -> dict:
    app_id = app.get("id")
    run_id = store.acquire_run_lock(app_id, target_key)
    if run_id is None:
        return {"target": target_key, "error": "deploy_in_progress"}

    target_cfg = (app.get("targets") or {}).get(target_key) or {}
    plan = planner.build_rollback_plan(app, target_key, target_cfg, to_version, _smoke_timeout_s())
    prev_version_id = store.last_success_version(app_id, target_key)

    def _worker():
        transport = make_transport(target_key)
        try:
            execute_plan(
                run_id, app, target_key, plan, transport,
                version_id=to_version, action="rollback", prev_version_id=prev_version_id,
            )
        finally:
            store.release_run_lock(app_id, target_key)

    threading.Thread(target=_worker, daemon=True).start()
    return {"target": target_key, "run_id": run_id}
