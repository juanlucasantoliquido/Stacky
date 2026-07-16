"""services/deploy_planner.py — Plan 120 F1. Motor PURO del Centro de Despliegues.

Toda la lógica de DECISIÓN (qué pasos correr, qué comando exacto emitir, qué
versiones podar, cómo calcular drift/DORA) vive acá como funciones puras:
sin I/O, sin red, sin Flask, sin subprocess. Los efectos (ejecutar comandos,
transferir archivos, persistir) viven en deploy_executor.py / deploy_store.py.

Convención de layout en el destino (§5.2 del plan):
    <install_path>\\releases\\<version_id>\\    ← contenido, inmutable
    <install_path>\\incoming\\<version_id>.zip  ← staging del artefacto
    <install_path>\\current                     ← junction -> releases\\<version_id>
    <install_path>\\release.json                ← marker {version_id, app_id, deployed_at, source_sha256}
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta

MAX_ARTIFACT_MB = 500

_APP_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_ARTIFACT_KINDS = ("folder", "zip")
_SMOKE_KINDS = ("http", "ps", "none")
_FAILED_STATUSES = ("failed", "failed_smoke")


# ── validate_app ────────────────────────────────────────────────────────────

def validate_app(app: dict) -> list[str]:
    """Valida el shape de una app desplegable. Devuelve lista de errores legibles;
    [] significa válida. NUNCA lanza (defensivo ante dict malformado)."""
    errors: list[str] = []
    if not isinstance(app, dict):
        return ["app debe ser un objeto"]

    app_id = app.get("id")
    if not isinstance(app_id, str) or not _APP_ID_RE.match(app_id):
        errors.append("id inválido: solo minúsculas/dígitos/_/- (1-64 chars, empieza alfanumérico)")

    artifact = app.get("artifact")
    if not isinstance(artifact, dict):
        errors.append("artifact es obligatorio (objeto)")
    else:
        kind = artifact.get("kind")
        if kind not in _ARTIFACT_KINDS:
            errors.append(f"artifact.kind debe ser uno de {_ARTIFACT_KINDS}")
        path = artifact.get("path")
        if not isinstance(path, str) or not path.strip() or not _is_absolute_windows_path(path):
            errors.append("artifact.path debe ser una ruta absoluta no vacía")

    targets = app.get("targets")
    if not isinstance(targets, dict) or not targets:
        errors.append("targets es obligatorio (objeto no vacío)")
    else:
        for key, cfg in targets.items():
            if not isinstance(cfg, dict):
                errors.append(f"targets.{key} debe ser un objeto")
                continue
            install_path = cfg.get("install_path")
            if not isinstance(install_path, str) or not install_path.strip() or not _is_absolute_windows_path(install_path):
                errors.append(f"targets.{key}.install_path debe ser una ruta absoluta no vacía")
            smoke = cfg.get("smoke") or {}
            if not isinstance(smoke, dict) or smoke.get("kind") not in _SMOKE_KINDS:
                errors.append(f"targets.{key}.smoke.kind debe ser uno de {_SMOKE_KINDS}")

    return errors


def _is_absolute_windows_path(path: str) -> bool:
    # Acepta 'C:\\...' o UNC '\\\\server\\share\\...'. Rechaza rutas relativas.
    return bool(re.match(r"^[A-Za-z]:\\", path)) or path.startswith("\\\\")


# ── versionado ───────────────────────────────────────────────────────────────

def make_version_id(now_utc: datetime, zip_sha256: str) -> str:
    return now_utc.strftime("%Y%m%d-%H%M%S") + "-" + (zip_sha256 or "")[:8]


# ── comandos exactos (§5.2) ──────────────────────────────────────────────────

def _reject_embedded_quotes(*values: str) -> None:
    for v in values:
        if '"' in (v or ""):
            raise ValueError(f"valor con comillas dobles embebidas no permitido: {v!r}")


def build_switch_commands(install_path: str, version_id: str) -> list[str]:
    """C1 v2: el rmdir SIEMPRE va guardado con `if exist` (no-op si `current`
    todavía no existe, p.ej. el primer deploy), así nunca revienta con exit≠0.
    Borra SOLO el junction; si `current` fuera un directorio real no vacío,
    `rmdir` sin `/S` falla con error legible (protege el contenido)."""
    if not _is_absolute_windows_path(install_path):
        raise ValueError(f"install_path debe ser absoluto: {install_path!r}")
    _reject_embedded_quotes(install_path, version_id)
    current = f"{install_path}\\current"
    release = f"{install_path}\\releases\\{version_id}"
    return [
        f'cmd /c if exist "{current}" rmdir "{current}"',
        f'cmd /c mklink /J "{current}" "{release}"',
    ]


def build_marker_command(install_path: str, marker: dict) -> str:
    """C4 v2 — comando exacto para escribir release.json en el destino."""
    if not _is_absolute_windows_path(install_path):
        raise ValueError(f"install_path debe ser absoluto: {install_path!r}")
    payload = json.dumps(marker, separators=(",", ":"), ensure_ascii=False)
    if "'" in payload:
        raise ValueError("el marker serializado no puede contener comilla simple")
    return f"Set-Content -LiteralPath '{install_path}\\release.json' -Value '{payload}' -Encoding utf8"


def build_smoke_command(smoke: dict, timeout_s: int) -> str | None:
    """C9 v2 — corre en modo write (las llaves {} están permitidas ahí, §5.2)."""
    kind = (smoke or {}).get("kind")
    if kind == "none" or kind is None:
        return None
    if kind == "http":
        url = smoke.get("url") or ""
        return (
            "try { (Invoke-WebRequest -UseBasicParsing -TimeoutSec "
            f"{int(timeout_s)} -Uri '{url}').StatusCode }} "
            "catch { if ($_.Exception.Response) { [int]$_.Exception.Response.StatusCode } "
            "else { 'ERR: ' + $_.Exception.Message } }"
        )
    if kind == "ps":
        return smoke.get("command") or None
    return None


_LAST_NUMERIC_RE = re.compile(r"(\d+)")


def parse_smoke_http_stdout(stdout: str) -> int | None:
    """C9 v2 — el ÚLTIMO token numérico del stdout, o None si no hay ninguno."""
    matches = _LAST_NUMERIC_RE.findall(stdout or "")
    if not matches:
        return None
    try:
        return int(matches[-1])
    except ValueError:
        return None


def smoke_http_ok(status_code: int | None) -> bool:
    return status_code is not None and 200 <= status_code <= 399


# ── planes de deploy / rollback ─────────────────────────────────────────────

def _ensure_dirs_command(install_path: str) -> str:
    return (
        "New-Item -ItemType Directory -Force -Path "
        f"'{install_path}\\releases','{install_path}\\incoming' | Out-Null"
    )


def _unpack_command(install_path: str, version_id: str) -> str:
    return (
        f"Expand-Archive -LiteralPath '{install_path}\\incoming\\{version_id}.zip' "
        f"-DestinationPath '{install_path}\\releases\\{version_id}' -Force"
    )


def _cleanup_command(install_path: str, version_id: str) -> str:
    return f"Remove-Item -LiteralPath '{install_path}\\incoming\\{version_id}.zip' -Force"


def _step(name: str, command: str | None, *, read_only: bool = False, housekeeping: bool = False) -> dict:
    return {"name": name, "command": command, "read_only": read_only, "housekeeping": housekeeping}


def build_deploy_plan(
    app: dict,
    target_key: str,
    target_cfg: dict,
    version_id: str,
    retain: int,
    smoke_timeout_s: int,
) -> list[dict]:
    install_path = target_cfg["install_path"]
    steps: list[dict] = [
        _step("preflight", None, read_only=True),
        _step("ensure_dirs", _ensure_dirs_command(install_path)),
        _step("transfer", None),  # despachado por nombre en el executor (F4)
        _step("unpack", _unpack_command(install_path, version_id)),
    ]
    if target_cfg.get("pre_switch"):
        steps.append(_step("pre_switch", target_cfg["pre_switch"]))
    steps.append(_step("switch", "; ".join(build_switch_commands(install_path, version_id))))
    marker = {
        "version_id": version_id,
        "app_id": app.get("id"),
        "deployed_at": None,  # el executor completa el timestamp real al escribir
        "source_sha256": None,
    }
    steps.append(_step("write_marker", build_marker_command(install_path, marker)))
    if target_cfg.get("post_switch"):
        steps.append(_step("post_switch", target_cfg["post_switch"]))
    smoke_cmd = build_smoke_command(target_cfg.get("smoke") or {}, smoke_timeout_s)
    if smoke_cmd is not None:
        steps.append(_step("smoke", smoke_cmd))
    steps.append(_step("prune", None, housekeeping=True))  # despachado por nombre (F4)
    steps.append(_step("cleanup", _cleanup_command(install_path, version_id), housekeeping=True))
    return steps


def build_rollback_plan(
    app: dict,
    target_key: str,
    target_cfg: dict,
    to_version_id: str,
    smoke_timeout_s: int,
) -> list[dict]:
    """SIN `transfer` NI `unpack`: re-apunta el junction a una release retenida."""
    install_path = target_cfg["install_path"]
    steps: list[dict] = []
    if target_cfg.get("pre_switch"):
        steps.append(_step("pre_switch", target_cfg["pre_switch"]))
    steps.append(_step("switch", "; ".join(build_switch_commands(install_path, to_version_id))))
    marker = {
        "version_id": to_version_id,
        "app_id": app.get("id"),
        "deployed_at": None,
        "source_sha256": None,
    }
    steps.append(_step("write_marker", build_marker_command(install_path, marker)))
    if target_cfg.get("post_switch"):
        steps.append(_step("post_switch", target_cfg["post_switch"]))
    smoke_cmd = build_smoke_command(target_cfg.get("smoke") or {}, smoke_timeout_s)
    if smoke_cmd is not None:
        steps.append(_step("smoke", smoke_cmd))
    return steps


# ── retención ────────────────────────────────────────────────────────────────

def prune_versions(existing: list[str], retain: int, current: str | None) -> list[str]:
    """Devuelve las versiones a BORRAR: todo lo que exceda las `retain` más
    nuevas, EXCLUYENDO SIEMPRE `current` (aunque quedara fuera de la ventana)."""
    uniq = sorted({v for v in (existing or []) if v})  # ids ordenables lexicográficamente
    keep_newest = set(uniq[-retain:]) if retain > 0 else set()
    keep = keep_newest | ({current} if current else set())
    return [v for v in uniq if v not in keep]


# ── marker / drift ───────────────────────────────────────────────────────────

def parse_release_marker(stdout: str) -> dict | None:
    try:
        data = json.loads((stdout or "").strip())
    except Exception:  # noqa: BLE001 — JSON corrupto/ausente: degradar a None
        return None
    return data if isinstance(data, dict) else None


def compute_drift(desired_version: str | None, marker: dict | None) -> str:
    if not desired_version:
        return "never"
    if not marker or not isinstance(marker.get("version_id"), str):
        return "unknown"
    return "ok" if marker["version_id"] == desired_version else "drift"


# ── estado efectivo (A1) ─────────────────────────────────────────────────────

def _parse_iso(ts) -> datetime | None:
    if not isinstance(ts, str) or not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def derive_effective_status(entry: dict, now_utc: datetime, stale_after_s: int = 3600) -> str:
    """[A1] Un `running` cuyo backend murió a mitad de deploy se DERIVA `stale`
    en lectura; nunca muta el ledger."""
    status = (entry or {}).get("status")
    if status != "running":
        return status
    started = _parse_iso((entry or {}).get("started_at"))
    if started is None:
        return status
    if (now_utc - started).total_seconds() > stale_after_s:
        return "stale"
    return status


# ── preflight de disco (A2) ───────────────────────────────────────────────────

def check_disk_headroom(free_bytes: int | None, artifact_bytes: int) -> str | None:
    """Warning informativo (JAMÁS bloquea) si el libre < 2x el artefacto."""
    if free_bytes is None:
        return None
    needed = max(artifact_bytes, 0) * 2
    if free_bytes >= needed:
        return None
    free_mb = free_bytes / (1024 * 1024)
    needed_mb = needed / (1024 * 1024)
    return (
        f"Espacio libre bajo: {free_mb:.0f} MB disponibles, se recomiendan al menos "
        f"{needed_mb:.0f} MB (2x el artefacto) antes de desplegar."
    )


# ── DORA local ────────────────────────────────────────────────────────────────

def dora_metrics(entries: list[dict], now_utc: datetime) -> dict:
    deploys = [e for e in (entries or []) if e.get("action") == "deploy" and e.get("finished_at")]
    deploys_sorted = sorted(deploys, key=lambda e: e["finished_at"])

    def _within(entry, days):
        dt = _parse_iso(entry.get("finished_at"))
        return dt is not None and (now_utc - dt) <= timedelta(days=days)

    deploys_7d = sum(1 for e in deploys_sorted if _within(e, 7))
    window_30 = [e for e in deploys_sorted if _within(e, 30)]
    deploys_30d = len(window_30)
    fails_30 = [e for e in window_30 if e.get("status") in _FAILED_STATUSES]
    successes_30 = [e for e in window_30 if e.get("status") == "success"]
    total_30 = len(fails_30) + len(successes_30)
    change_failure_rate_30d = (len(fails_30) / total_30) if total_30 else None

    mttrs: list[float] = []
    for i, entry in enumerate(deploys_sorted):
        if entry not in fails_30:
            continue
        fail_dt = _parse_iso(entry.get("finished_at"))
        if fail_dt is None:
            continue
        for later in deploys_sorted[i + 1:]:
            if later.get("status") == "success":
                succ_dt = _parse_iso(later.get("finished_at"))
                if succ_dt is not None:
                    mttrs.append((succ_dt - fail_dt).total_seconds() / 60.0)
                break
    mttr_minutes_30d = (sum(mttrs) / len(mttrs)) if mttrs else None
    last_deploy_at = deploys_sorted[-1]["finished_at"] if deploys_sorted else None

    return {
        "deploys_7d": deploys_7d,
        "deploys_30d": deploys_30d,
        "change_failure_rate_30d": change_failure_rate_30d,
        "mttr_minutes_30d": mttr_minutes_30d,
        "last_deploy_at": last_deploy_at,
    }
