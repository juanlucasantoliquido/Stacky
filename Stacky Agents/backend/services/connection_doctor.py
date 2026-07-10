"""services/connection_doctor.py — Plan 116 · Doctor de conexiones DETERMINISTA.

Catálogo tipificado de códigos de falla con remediación paso a paso (escrita acá,
NO la inventa ningún modelo), clasificadores de excepciones/HTTP y sondas paralelas
con timeout corto. Cero LLM, cero costo por uso. HITL: solo corre por click.

F0 = núcleo puro (catálogo + clasificadores + build_result), sin red, sin Flask.
F1 = sondas (probe_*) + agregador run_connection_check.
"""
from __future__ import annotations

import socket
import ssl
import time
import urllib.error
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

_PROBE_TIMEOUT_SECONDS: float = 5.0
_DETAIL_MAX = 300

CODES: tuple[str, ...] = (
    "CONFIG_MISSING", "DNS_FAIL", "TCP_REFUSED", "TIMEOUT", "TLS_ERROR",
    "AUTH_401", "FORBIDDEN_403", "NOT_FOUND_404", "HTTP_5XX", "CLI_NOT_FOUND",
    "KEYRING_UNAVAILABLE", "CRED_MISSING", "UNKNOWN",
)

# Catálogo LITERAL de remediación (§F0). Los {placeholders} se resuelven en build_result.
REMEDIATIONS: dict[str, dict] = {
    "CONFIG_MISSING": {
        "title": "Falta configuración",
        "cause": "No hay datos suficientes para intentar la conexión ({what}).",
        "steps": [
            "Abrí Configuración → Config global (o el proyecto activo) y completá {what}.",
            "Guardá y volvé a este panel.",
            "Click en \"Reintentar\".",
        ],
        "action": {"kind": "retry"},
    },
    "DNS_FAIL": {
        "title": "El nombre no resuelve",
        "cause": "El host {host} no existe en DNS o no hay red.",
        "steps": [
            "Verificá que el nombre esté bien escrito (sin http:// ni espacios).",
            "Probá `ping {host}` en una terminal: si falla, es red/VPN, no Stacky.",
            "Si usás VPN corporativa, conectala y reintentá.",
        ],
        "action": {"kind": "copy_command", "command": "ping {host}"},
    },
    "TCP_REFUSED": {
        "title": "El servidor rechaza la conexión",
        "cause": "El host {host} responde pero el puerto {port} está cerrado o el servicio caído.",
        "steps": [
            "Confirmá que el servicio esté levantado en {host}.",
            "Revisá firewall/puerto {port}.",
            "Reintentá cuando el servicio esté arriba.",
        ],
        "action": {"kind": "retry"},
    },
    "TIMEOUT": {
        "title": "La conexión expiró",
        "cause": "{host} no respondió en {timeout}s (red lenta, VPN caída o host apagado).",
        "steps": [
            "Verificá tu conexión/VPN.",
            "Confirmá que el host esté encendido.",
            "Reintentá; si persiste, revisá con el doctor IA de la sección (plan 104).",
        ],
        "action": {"kind": "retry"},
    },
    "TLS_ERROR": {
        "title": "Error de certificado TLS",
        "cause": "El certificado de {host} no es válido para este cliente (autofirmado, vencido o proxy corporativo).",
        "steps": [
            "Si es un servidor interno con certificado autofirmado, revisá la config `verify_ssl` del tracker del proyecto.",
            "Si hay proxy corporativo, consultá qué CA raíz instalar.",
            "Reintentá tras el cambio.",
        ],
        "action": {"kind": "retry"},
    },
    "AUTH_401": {
        "title": "Credenciales inválidas o vencidas",
        "cause": "{service} rechazó la autenticación (401): token/PAT inválido, vencido o revocado.",
        "steps": [
            "Regenerá el token en {service}.",
            "Pegalo en Configuración → Config global (campo correspondiente) y guardá.",
            "Click en \"Reintentar\" para validar.",
        ],
        "action": {"kind": "open_url", "url": "{token_url}"},
    },
    "FORBIDDEN_403": {
        "title": "Sin permisos suficientes",
        "cause": "{service} autenticó pero denegó el acceso (403): el token no tiene los scopes/permisos necesarios.",
        "steps": [
            "Regenerá el token con los scopes de lectura/escritura de work items o `api` (GitLab).",
            "Verificá que tu usuario tenga acceso al proyecto/organización.",
            "Reintentá.",
        ],
        "action": {"kind": "open_url", "url": "{token_url}"},
    },
    "NOT_FOUND_404": {
        "title": "Recurso inexistente",
        "cause": "{service} respondió 404: la organización/proyecto/URL configurada no existe o está mal escrita.",
        "steps": [
            "Revisá organización y proyecto en Configuración → Config global.",
            "Confirmá el nombre exacto en el navegador.",
            "Corregí y reintentá.",
        ],
        "action": {"kind": "retry"},
    },
    "HTTP_5XX": {
        "title": "El servicio remoto falló",
        "cause": "{service} devolvió un error {status} de SU lado; no es un problema de tu configuración.",
        "steps": [
            "Esperá unos minutos: suele ser transitorio.",
            "Revisá el status page del servicio si persiste.",
            "Reintentá.",
        ],
        "action": {"kind": "retry"},
    },
    "CLI_NOT_FOUND": {
        "title": "CLI no instalada",
        "cause": "No se encontró `{cli}` en el PATH: el runtime {runtime} no puede ejecutarse desde Stacky.",
        "steps": [
            "Instalala con el comando de abajo (botón \"Copiar\").",
            "Cerrá y reabrí la terminal/backend para refrescar el PATH.",
            "Reintentá el diagnóstico.",
        ],
        "action": {"kind": "copy_command", "command": "{install_cmd}"},
    },
    "KEYRING_UNAVAILABLE": {
        "title": "Almacén de credenciales no disponible",
        "cause": "El backend no pudo usar el keyring de Windows: los passwords de servidores no pueden guardarse ni leerse.",
        "steps": [
            "Instalá la dependencia en el venv del backend con el comando de abajo.",
            "Reiniciá el backend.",
            "Reintentá el diagnóstico.",
        ],
        "action": {"kind": "copy_command", "command": "pip install keyring==25.6.0"},
    },
    "CRED_MISSING": {
        "title": "Servidor sin credencial guardada",
        "cause": "El servidor {alias} está registrado pero no tiene password en el keyring: RDP 1-click y consola remota no van a autenticar.",
        "steps": [
            "Andá a la sección Servidores.",
            "Editá {alias} y cargá el password (se guarda write-only en keyring).",
            "Reintentá el diagnóstico.",
        ],
        "action": {"kind": "goto_section", "section_id": "servidores"},
    },
    "UNKNOWN": {
        "title": "Falla no clasificada",
        "cause": "Ocurrió un error que el doctor no pudo tipificar.",
        "steps": [
            "Leé el detalle técnico de abajo.",
            "Reintentá una vez.",
            "Si persiste, usá el doctor IA de la sección (plan 104) o revisá los logs del backend en Diagnóstico.",
        ],
        "action": {"kind": "retry"},
    },
}


_TRACKER_LABELS = {
    "azure_devops": "Azure DevOps", "gitlab": "GitLab", "jira": "Jira", "mantis": "Mantis",
}
_INSTALL_CMD = {
    "codex": "npm install -g @openai/codex",
    "claude": "npm install -g @anthropic-ai/claude-code",
    "git": "winget install --id Git.Git -e",
}
_CLI_RUNTIME = {"git": "git", "codex": "Codex CLI", "claude": "Claude Code CLI"}


class _SafeDict(dict):
    def __missing__(self, key):  # placeholder faltante → "?" (nunca KeyError)
        return "?"


def classify_http_error(status_code: int | None, exc: Exception | None) -> str:
    if status_code is None:
        return classify_socket_error(exc) if exc is not None else "UNKNOWN"
    if status_code == 401:
        return "AUTH_401"
    if status_code == 403:
        return "FORBIDDEN_403"
    if status_code == 404:
        return "NOT_FOUND_404"
    if status_code >= 500:
        return "HTTP_5XX"
    return "UNKNOWN"


def classify_socket_error(exc: Exception) -> str:
    if isinstance(exc, socket.gaierror):
        return "DNS_FAIL"
    if isinstance(exc, (socket.timeout, TimeoutError)):
        return "TIMEOUT"
    if isinstance(exc, ConnectionRefusedError):
        return "TCP_REFUSED"
    if isinstance(exc, ssl.SSLError):
        return "TLS_ERROR"
    if isinstance(exc, urllib.error.HTTPError):
        return classify_http_error(exc.code, None)
    if isinstance(exc, urllib.error.URLError):
        reason = getattr(exc, "reason", None)
        return classify_socket_error(reason) if isinstance(reason, Exception) else "UNKNOWN"
    return "UNKNOWN"


def build_result(*, target: str, target_label: str, group: str, status: str,
                 code: str = "", detail: str = "", latency_ms: int | None = None,
                 fmt: dict | None = None) -> dict:
    detail = (detail or "")[:_DETAIL_MAX]
    remediation = None
    if status in ("fail", "warn"):
        entry = REMEDIATIONS.get(code) or REMEDIATIONS["UNKNOWN"]
        safe = _SafeDict(fmt or {})
        action = dict(entry["action"])
        for key in ("command", "url", "section_id"):
            if key in action:
                action[key] = str(action[key]).format_map(safe)
        remediation = {
            "title": entry["title"],
            "cause": entry["cause"].format_map(safe),
            "steps": [s.format_map(safe) for s in entry["steps"]],
            "action": action,
        }
    return {
        "target": target,
        "target_label": target_label,
        "group": group,
        "status": status,
        "code": code if status in ("fail", "warn") else "",
        "detail": detail,
        "latency_ms": latency_ms,
        "remediation": remediation,
    }


# ── F1 — Sondas (reusan el sustrato existente) + agregador paralelo ────────────

def _token_url(tracker_type: str, tracker: dict) -> str:
    """(C1) URL pública de gestión de tokens; '' si falta org/base → degrada a retry."""
    if tracker_type == "azure_devops":
        org = str(tracker.get("organization") or tracker.get("org") or "").strip()
        return f"https://dev.azure.com/{org}/_usersSettings/tokens" if org else ""
    if tracker_type == "gitlab":
        base = str(tracker.get("base_url") or tracker.get("url") or "").rstrip("/")
        return f"{base}/-/user_settings/personal_access_tokens" if base else ""
    return ""


def _probe_gitlab(tracker: dict) -> None:
    """Sonda GitLab propia (el bug de local_diagnostics._check_tracker:80 manda gitlab
    a _probe_ado; acá NO se replica). Mismo cliente/constructor que api/global_config.py."""
    from services.gitlab_client import GitLabClient
    base = str(tracker.get("base_url") or tracker.get("url") or "")
    proj = str(tracker.get("project") or tracker.get("project_path") or "")
    client = GitLabClient(base_url=base, project=proj)
    client._request("GET", "/user")


def probe_tracker() -> dict:
    from project_manager import get_active_project, get_project_config
    active = get_active_project()
    if not active:
        return build_result(target="tracker", target_label="Tracker", group="tracker",
                            status="warn", code="CONFIG_MISSING",
                            detail="No hay proyecto activo.", fmt={"what": "el proyecto activo"})
    cfg = get_project_config(active) or {}
    tracker = cfg.get("issue_tracker") or {}
    tracker_type = str(tracker.get("type") or "azure_devops").strip().lower()
    label = _TRACKER_LABELS.get(tracker_type, tracker_type or "Tracker")  # (C1) incluye gitlab
    started = time.monotonic()
    try:
        if tracker_type == "jira":
            from services.local_diagnostics import _probe_jira
            _probe_jira(active, tracker)
        elif tracker_type == "mantis":
            from services.local_diagnostics import _probe_mantis
            _probe_mantis(active, tracker)
        elif tracker_type == "gitlab":
            _probe_gitlab(tracker)
        else:
            from services.local_diagnostics import _probe_ado
            _probe_ado(active)
        latency = int((time.monotonic() - started) * 1000)
        return build_result(target="tracker", target_label=f"{label} ({active})", group="tracker",
                            status="ok", detail=f"{label}: credenciales válidas para {active}.",
                            latency_ms=latency)
    except Exception as exc:  # noqa: BLE001
        code = classify_socket_error(exc)
        if isinstance(exc, urllib.error.HTTPError):
            code = classify_http_error(exc.code, None)
        token_url = _token_url(tracker_type, tracker)
        fmt = {"service": label, "host": "", "token_url": token_url,
               "status": getattr(exc, "code", ""), "what": label}
        result = build_result(target="tracker", target_label=f"{label} ({active})", group="tracker",
                              status="fail", code=code, detail=str(exc)[:_DETAIL_MAX], fmt=fmt)
        # Degradación: sin token_url conocido, la acción open_url baja a retry.
        rem = result.get("remediation")
        if rem and rem["action"].get("kind") == "open_url" and not token_url:
            rem["action"] = {"kind": "retry"}
        return result


def probe_servers() -> list[dict]:
    from services import server_registry
    out: list[dict] = []
    keyring_ok = server_registry.keyring_available()
    for server in server_registry.list_servers():
        alias = server.get("alias", "")
        host = server.get("host", "")
        ok, detail = server_registry.test_connectivity(host)
        if ok:
            code = ""
            status = "ok"
        elif detail.startswith("DNS:"):
            code, status = "DNS_FAIL", "fail"
        elif "timed out" in detail.lower():
            code, status = "TIMEOUT", "fail"
        else:
            code, status = "TCP_REFUSED", "fail"
        out.append(build_result(
            target=f"server:{alias}", target_label=f"Servidor {alias}", group="servers",
            status=status, code=code, detail=detail[:_DETAIL_MAX],
            fmt={"host": host, "port": "3389", "timeout": "3"}))
        if ok and keyring_ok and not server.get("has_password", False):
            out.append(build_result(
                target=f"server:{alias}", target_label=f"Servidor {alias}", group="servers",
                status="warn", code="CRED_MISSING", fmt={"alias": alias}))
    return out


def probe_clis() -> list[dict]:
    from services.local_diagnostics import _find_executable, _npm_global_fallbacks
    out: list[dict] = []
    for name in ("git", "codex", "claude"):
        fallbacks = [] if name == "git" else _npm_global_fallbacks(name)
        path = _find_executable(name, fallbacks)
        if path:
            out.append(build_result(target=f"cli:{name}", target_label=f"{_CLI_RUNTIME[name]}",
                                    group="clis", status="ok", detail=str(path)))
        else:
            out.append(build_result(
                target=f"cli:{name}", target_label=f"{_CLI_RUNTIME[name]}", group="clis",
                status="fail", code="CLI_NOT_FOUND",
                fmt={"cli": name, "runtime": _CLI_RUNTIME[name], "install_cmd": _INSTALL_CMD[name]}))
    out.append(build_result(
        target="runtime:copilot", target_label="GitHub Copilot", group="clis", status="skip",
        detail="GitHub Copilot no requiere CLI local (corre vía VS Code/bridge)."))
    return out


def probe_keyring() -> dict:
    from services import server_registry
    if server_registry.keyring_available():
        return build_result(target="keyring", target_label="Keyring", group="credentials",
                            status="ok", detail="Almacén de credenciales disponible.")
    return build_result(target="keyring", target_label="Keyring", group="credentials",
                        status="warn", code="KEYRING_UNAVAILABLE")


def run_connection_check() -> dict:
    started = time.monotonic()
    tasks = {"tracker": probe_tracker, "servers": probe_servers,
             "clis": probe_clis, "keyring": probe_keyring}
    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {name: pool.submit(fn) for name, fn in tasks.items()}
        for name, fut in futures.items():
            try:
                out = fut.result(timeout=_PROBE_TIMEOUT_SECONDS * 3)
                results.extend(out if isinstance(out, list) else [out])
            except Exception as exc:  # noqa: BLE001 — un probe roto NUNCA rompe el chequeo
                results.append(build_result(
                    target=name, target_label=name,
                    group=name if name != "keyring" else "credentials",
                    status="fail", code="UNKNOWN", detail=str(exc)[:_DETAIL_MAX]))
    summary = {s: sum(1 for r in results if r["status"] == s) for s in ("ok", "warn", "fail", "skip")}
    return {"generated_at": datetime.utcnow().isoformat() + "Z",
            "duration_ms": int((time.monotonic() - started) * 1000),
            "results": results, "summary": summary}
