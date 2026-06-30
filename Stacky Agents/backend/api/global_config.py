"""
api/global_config.py -- Configuracion global de trackers (defaults para nuevos proyectos).

GET  /api/global-config  -> devuelve los valores actuales (sin tokens/secrets)
PUT  /api/global-config  -> actualiza el .env del backend con los nuevos valores

IMPORTANTE: estos valores SOLO se usan como defaults al crear nuevos proyectos.
Las APIs de trackers siempre usan la configuracion por proyecto (auth/*.json).

Portado desde WS2 (2026-05-23) -- P1.5.
Adaptaciones WS1:
  - test-connection Mantis usa list_projects() en vez de get_project_statuses()
    (get_project_statuses no esta disponible en WS1 todavia).
"""
import os
import logging
import base64
import json
import urllib.request
import urllib.error
import urllib.parse
from pathlib import Path

from flask import Blueprint, jsonify, request

from runtime_paths import backend_root
from services.gitlab_client import GitLabClient  # importado a nivel módulo para parchear en tests
from services.tracker_provider import TrackerConfigError as _TrackerConfigError  # ídem

logger = logging.getLogger(__name__)

bp = Blueprint("global_config", __name__)

# Ruta al .env del backend. Debe ser EXACTAMENTE el mismo archivo que carga
# config.py al arrancar (backend_root()/.env) y el que escribe harness_flags.py.
# En un deploy frozen, Path(__file__).parent.parent resolvía a _internal/.env
# (que el loader nunca lee) → los cambios no persistían al reiniciar. Mantener
# ambos endpoints sobre el mismo archivo es obligatorio: no deben divergir.
_ENV_PATH = backend_root() / ".env"

# Claves gestionadas por este endpoint
_MANAGED_KEYS = [
    # Azure DevOps
    "ADO_ORG",
    "ADO_PROJECT",
    "ADO_PAT",
    # Jira
    "JIRA_URL",
    "JIRA_USER",
    "JIRA_TOKEN",
    "JIRA_API_VERSION",
    # Mantis REST
    "MANTIS_URL",
    "MANTIS_TOKEN",
    "MANTIS_PROJECT_ID",
    "MANTIS_USER_ID",
    # Mantis SOAP
    "MANTIS_USERNAME",
    "MANTIS_PASSWORD",
    "MANTIS_PROTOCOL",
    # Codex CLI
    "CODEX_CLI_BIN",
    "CODEX_CLI_MODEL",
    "CODEX_CLI_SANDBOX",
    "CODEX_CLI_APPROVAL",
    "CODEX_AGENTS_DIR",
    "CODEX_AUTH_MODE",
    "OPENAI_API_KEY",
    # Claude Code CLI
    "CLAUDE_CODE_CLI_BIN",
    "CLAUDE_CODE_CLI_MODEL",
    "CLAUDE_CODE_CLI_EFFORT",
    "CLAUDE_CODE_CLI_PERMISSION_MODE",
    "CLAUDE_CODE_CLI_SKIP_PERMISSIONS",
    # GitLab (Plan 65) — NUNCA incluir GITLAB_TOKEN aquí (secret)
    "GITLAB_URL",
    "GITLAB_PROJECT",
    "STACKY_GITLAB_GROUP",
    "STACKY_GITLAB_ENABLED",
    "STACKY_GITLAB_EPICS_NATIVE",
    "STACKY_GITLAB_CI_INFERENCE",
]

# Claves que contienen secrets -- no se devuelven en GET
_SECRET_KEYS = {"ADO_PAT", "JIRA_TOKEN", "MANTIS_TOKEN", "MANTIS_PASSWORD", "OPENAI_API_KEY"}
# GITLAB_TOKEN no está en _MANAGED_KEYS (nunca persiste por esta ruta)

# Valores por defecto para campos Codex cuando no estan en el .env
_CODEX_DEFAULTS = {
    "CODEX_CLI_BIN": "",
    "CODEX_CLI_MODEL": "",
    "CODEX_CLI_SANDBOX": "danger-full-access",
    "CODEX_CLI_APPROVAL": "never",
    "CODEX_AGENTS_DIR": "",
    "CODEX_AUTH_MODE": "apikey",
    "OPENAI_API_KEY": "",
    # Claude Code CLI
    "CLAUDE_CODE_CLI_BIN": "",
    "CLAUDE_CODE_CLI_MODEL": "claude-sonnet-4-6",
    "CLAUDE_CODE_CLI_EFFORT": "medium",
    "CLAUDE_CODE_CLI_PERMISSION_MODE": "acceptEdits",
    "CLAUDE_CODE_CLI_SKIP_PERMISSIONS": "false",
}


def _read_env() -> dict[str, str]:
    """Lee el .env y retorna un dict clave=valor."""
    result: dict[str, str] = {}
    if not _ENV_PATH.exists():
        return result
    for line in _ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, val = line.partition("=")
            result[key.strip()] = val.strip()
    return result


def _write_env(updates: dict[str, str]) -> None:
    """Actualiza las claves gestionadas en el .env sin tocar las demas."""
    lines: list[str] = []
    if _ENV_PATH.exists():
        lines = _ENV_PATH.read_text(encoding="utf-8").splitlines()

    updated_keys: set[str] = set()
    new_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            new_lines.append(line)
            continue
        key = stripped.partition("=")[0].strip()
        if key in updates:
            new_lines.append(f"{key}={updates[key]}")
            updated_keys.add(key)
        else:
            new_lines.append(line)

    # Agregar claves nuevas que no estaban en el archivo
    for key in _MANAGED_KEYS:
        if key in updates and key not in updated_keys:
            new_lines.append(f"{key}={updates[key]}")

    _ENV_PATH.write_text("\n".join(new_lines) + "\n", encoding="utf-8")

    # Actualizar os.environ en caliente
    for key, val in updates.items():
        if val:
            os.environ[key] = val
        elif key in os.environ:
            del os.environ[key]


@bp.get("/global-config")
def get_global_config():
    """Devuelve la configuracion global de trackers.

    Con ?reveal=1 devuelve los valores reales de los secrets.
    Sin ese parametro los secrets se devuelven como { saved: true/false }.
    """
    reveal = request.args.get("reveal", "0") == "1"
    env = _read_env()
    result: dict = {}
    for key in _MANAGED_KEYS:
        val = env.get(key, _CODEX_DEFAULTS.get(key, ""))
        if key in _SECRET_KEYS:
            result[key] = val if reveal else {"saved": bool(val)}
        else:
            result[key] = val
    return jsonify({"ok": True, "config": result})


@bp.put("/global-config")
def put_global_config():
    """Actualiza la configuracion global de trackers en el .env.

    Los campos secret vacios se ignoran (no se sobreescriben si ya tenian valor).
    """
    data = request.get_json(force=True, silent=True) or {}
    env = _read_env()

    updates: dict[str, str] = {}
    for key in _MANAGED_KEYS:
        if key not in data:
            continue
        val = str(data[key] or "").strip()
        # Si es un secret y llega vacio, conservar el valor existente
        if key in _SECRET_KEYS and not val:
            continue
        updates[key] = val

    _write_env(updates)
    logger.info("global-config actualizado: %s", list(updates.keys()))
    return jsonify({"ok": True})


@bp.post("/global-config/test-connection")
def test_global_tracker_connection():
    """Prueba la conexion con el tracker usando las credenciales globales guardadas.

    Body: { tracker_type, organization?, ado_project?, pat?,
            jira_url?, jira_user?, jira_token?, api_version?,
            mantis_url?, mantis_protocol?, mantis_token?,
            mantis_username?, mantis_password? }
    """
    data = request.get_json(force=True, silent=True) or {}
    t_type = (data.get("tracker_type") or "azure_devops").strip()
    env = _read_env()

    def _merge(body_key: str, env_key: str) -> str:
        return (data.get(body_key) or env.get(env_key) or "").strip()

    _TIMEOUT = 12

    try:
        if t_type == "azure_devops":
            org = _merge("organization", "ADO_ORG")
            pat = _merge("pat", "ADO_PAT")
            if not org:
                return jsonify({"ok": False, "error": "Organizacion ADO no configurada."})
            if not pat:
                return jsonify({"ok": False, "error": "PAT de Azure DevOps no configurado."})
            token_b64 = base64.b64encode(f":{pat}".encode()).decode("ascii")
            url = (
                f"https://dev.azure.com/{urllib.parse.quote(org)}"
                "/_apis/projects?api-version=7.1&$top=1"
            )
            req = urllib.request.Request(
                url,
                headers={"Authorization": f"Basic {token_b64}", "Accept": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
                result = json.loads(resp.read().decode())
            count = result.get("count", 0)
            msg = f"Azure DevOps -- conexion OK. {count} proyecto(s) visible(s)."

        elif t_type == "jira":
            jira_url = _merge("jira_url", "JIRA_URL").rstrip("/")
            user = _merge("jira_user", "JIRA_USER")
            token = _merge("jira_token", "JIRA_TOKEN")
            api_ver = _merge("api_version", "JIRA_API_VERSION") or "3"
            if not jira_url:
                return jsonify({"ok": False, "error": "URL de Jira no configurada."})
            if not user or not token:
                return jsonify({"ok": False, "error": "Usuario y token Jira son obligatorios."})
            creds_b64 = base64.b64encode(f"{user}:{token}".encode()).decode("ascii")
            url = f"{jira_url}/rest/api/{api_ver}/myself"
            req = urllib.request.Request(
                url,
                headers={"Authorization": f"Basic {creds_b64}", "Accept": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
                result = json.loads(resp.read().decode())
            display = result.get("displayName") or result.get("name") or user
            msg = f"Jira -- conexion OK. Autenticado como: {display}"

        elif t_type == "mantis":
            from services.mantis_client import get_mantis_client, MantisConfigError
            mantis_url = _merge("mantis_url", "MANTIS_URL")
            protocol = _merge("mantis_protocol", "MANTIS_PROTOCOL") or "rest"
            token = _merge("mantis_token", "MANTIS_TOKEN")
            username = _merge("mantis_username", "MANTIS_USERNAME")
            password = _merge("mantis_password", "MANTIS_PASSWORD")
            if not mantis_url:
                return jsonify({"ok": False, "error": "URL de Mantis no configurada."})
            client = get_mantis_client(
                url=mantis_url, protocol=protocol,
                token=token, username=username, password=password,
                auth_file="non_existent_so_direct_creds_are_used",
            )
            # WS1: usa list_projects() para probar la conexion
            # (get_project_statuses no disponible todavia en WS1)
            projects = client.list_projects()
            msg = f"Mantis -- conexion OK. {len(projects)} proyecto(s) visible(s)."

        elif t_type == "gitlab":
            base = _merge("gitlab_url", "GITLAB_URL").rstrip("/")
            proj = _merge("gitlab_project", "GITLAB_PROJECT")
            if not base or not proj:
                return jsonify({"ok": False, "error": "Falta GITLAB_URL o GITLAB_PROJECT"})

            try:
                c = GitLabClient(base_url=base, project=proj)
            except _TrackerConfigError as e:
                return jsonify({"ok": False, "error": str(e)})

            checks: dict[str, object] = {"auth": False, "read": False, "write_permission": None}
            user: dict = {}

            try:
                user, _ = c._request("GET", "/user")
                checks["auth"] = bool(user.get("id"))
            except Exception as exc_gl:
                return jsonify({"ok": False, "error": f"Auth GitLab falló: {exc_gl}"})

            try:
                c._request("GET", f"/projects/{c._project_path()}/issues", params={"per_page": 1})
                checks["read"] = True
            except Exception:
                pass

            try:
                uid = user.get("id")
                if uid:
                    member, _ = c._request(
                        "GET", f"/projects/{c._project_path()}/members/all/{uid}"
                    )
                    checks["write_permission"] = (member.get("access_level", 0) >= 30)
            except Exception:
                checks["write_permission"] = None  # desconocido

            ok = bool(checks["auth"] and checks["read"])
            msg = f"GitLab -- conexion {'OK' if ok else 'PARCIAL'}. Checks: {checks}"

        else:
            return jsonify({"ok": False, "error": f"Tipo de tracker desconocido: {t_type}"}), 400

        logger.info("test-global-connection [%s]: %s", t_type, msg)
        return jsonify({"ok": True, "message": msg, "tracker_type": t_type})

    except (urllib.error.HTTPError, urllib.error.URLError) as exc:
        err = str(exc)
        logger.error("test-global-connection [%s] HTTP error: %s", t_type, err)
        return jsonify({"ok": False, "error": err, "tracker_type": t_type})
    except Exception as exc:
        err = str(exc)
        logger.error("test-global-connection [%s] fallo: %s", t_type, err)
        return jsonify({"ok": False, "error": err, "tracker_type": t_type})


# -- Modelos OpenAI conocidos compatibles con Codex CLI --
_CODEX_KNOWN_MODELS = [
    {"id": "o3",           "name": "o3"},
    {"id": "o4-mini",      "name": "o4-mini"},
    {"id": "o3-mini",      "name": "o3-mini"},
    {"id": "o1",           "name": "o1"},
    {"id": "o1-mini",      "name": "o1-mini"},
    {"id": "gpt-4.1",      "name": "gpt-4.1"},
    {"id": "gpt-4.1-mini", "name": "gpt-4.1-mini"},
    {"id": "gpt-4o",       "name": "gpt-4o"},
    {"id": "gpt-4o-mini",  "name": "gpt-4o-mini"},
]


@bp.post("/global-config/test-codex")
def test_codex_connection():
    """Verifica el binario de Codex CLI y devuelve los modelos disponibles.

    Body (opcional): { codex_bin: str, api_key: str }
    Respuesta: { ok, version, models, models_source, account_type, debug_log?, error? }
    """
    import subprocess
    import sys
    import shutil

    data = request.get_json(force=True, silent=True) or {}
    debug_log: list[str] = []

    def _dlog(msg: str) -> None:
        debug_log.append(msg)
        logger.info("test-codex | %s", msg)

    # Resolver bin: body > .env > autodetect
    codex_bin = (data.get("codex_bin") or "").strip()
    if not codex_bin:
        env = _read_env()
        codex_bin = env.get("CODEX_CLI_BIN", "").strip()

    if not codex_bin:
        local_app = os.environ.get("LOCALAPPDATA", "")
        if local_app:
            candidate = Path(local_app) / "OpenAI" / "Codex" / "bin" / "codex.exe"
            if candidate.exists():
                codex_bin = str(candidate)

    if not codex_bin:
        app_data = os.environ.get("APPDATA", "")
        if app_data and sys.platform == "win32":
            for name in ("codex.cmd", "codex.ps1", "codex"):
                candidate = Path(app_data) / "npm" / name
                if candidate.exists():
                    codex_bin = str(candidate)
                    break

    if not codex_bin:
        found = shutil.which("codex")
        if found:
            codex_bin = found

    if not codex_bin:
        codex_bin = "codex"

    _dlog(f"CODEX_BIN={codex_bin!r}")

    create_no_window = 0x08000000 if sys.platform == "win32" else 0
    bin_lower = codex_bin.lower()
    if sys.platform == "win32" and (bin_lower.endswith(".cmd") or bin_lower.endswith(".bat")):
        version_cmd = ["cmd", "/c", codex_bin, "--version"]
    else:
        version_cmd = [codex_bin, "--version"]

    try:
        proc = subprocess.run(
            version_cmd,
            capture_output=True, text=True, timeout=15,
            creationflags=create_no_window,
        )
        version_raw = (proc.stdout or proc.stderr or "").strip()
        version = version_raw.splitlines()[0] if version_raw else "OK"
        _dlog(f"VERSION={version!r}  rc={proc.returncode}")
        if proc.returncode != 0 and not version_raw:
            return jsonify({"ok": False, "error": f"El binario respondio con codigo {proc.returncode}."})
    except FileNotFoundError:
        return jsonify({
            "ok": False,
            "error": (
                f"Binario no encontrado: '{codex_bin}'. "
                "Instala Codex CLI con:  npm install -g @openai/codex  "
                "o configura la ruta completa al ejecutable."
            ),
        })
    except subprocess.TimeoutExpired:
        return jsonify({"ok": False, "error": "Timeout al ejecutar codex --version."})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)})

    models = _CODEX_KNOWN_MODELS
    source = "curated"

    logger.info("test-codex: bin=%s version=%s models=%d", codex_bin, version, len(models))
    return jsonify({
        "ok": True,
        "version": version,
        "models": models,
        "models_source": source,
        "account_type": "unknown",
        "debug_log": debug_log,
    })


@bp.post("/global-config/codex-login")
def codex_oauth_login():
    """Ejecuta codex login para autenticar con cuenta ChatGPT via OAuth.

    Body (opcional): { codex_bin: str }
    Respuesta: { ok, output?, error? }
    """
    import subprocess
    import sys
    import shutil

    data = request.get_json(force=True, silent=True) or {}

    codex_bin = (data.get("codex_bin") or "").strip()
    if not codex_bin:
        env = _read_env()
        codex_bin = env.get("CODEX_CLI_BIN", "").strip()

    if not codex_bin:
        local_app = os.environ.get("LOCALAPPDATA", "")
        if local_app:
            candidate = Path(local_app) / "OpenAI" / "Codex" / "bin" / "codex.exe"
            if candidate.exists():
                codex_bin = str(candidate)
    if not codex_bin and sys.platform == "win32":
        app_data = os.environ.get("APPDATA", "")
        if app_data:
            for name in ("codex.cmd", "codex.ps1", "codex"):
                candidate = Path(app_data) / "npm" / name
                if candidate.exists():
                    codex_bin = str(candidate)
                    break
    if not codex_bin:
        found = shutil.which("codex")
        if found:
            codex_bin = found
    if not codex_bin:
        codex_bin = "codex"

    if sys.platform == "win32" and codex_bin.lower().endswith((".cmd", ".bat")):
        cmd = ["cmd", "/c", codex_bin, "login"]
    else:
        cmd = [codex_bin, "login"]

    logger.info("codex-login: launching %s", cmd)

    try:
        proc = subprocess.run(
            cmd,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=300,
        )
        output = (proc.stdout or proc.stderr or "").strip()
        if proc.returncode == 0:
            logger.info("codex-login: exito")
            return jsonify({"ok": True, "output": output})
        else:
            logger.warning("codex-login: fallo con codigo %d: %s", proc.returncode, output[:200])
            return jsonify({"ok": False, "error": output or f"El proceso termino con codigo {proc.returncode}."})
    except FileNotFoundError:
        return jsonify({"ok": False, "error": f"Binario no encontrado: '{codex_bin}'."})
    except subprocess.TimeoutExpired:
        return jsonify({"ok": False, "error": "Timeout: el login no se completo en 5 minutos."})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)})


@bp.get("/global-config/codex-session")
def get_codex_session_status():
    """Verifica si el Codex CLI tiene sesion OAuth activa.

    Respuesta: { exists: bool, path?: str, method?: str, modified?: str, expires_at?: str }
    """
    import datetime
    import subprocess
    import sys
    import shutil

    # 1. File-based check (instantaneo)
    candidates: list[Path] = []
    home = Path.home()
    candidates += [
        home / ".codex" / "auth.json",
        home / ".openai" / "auth.json",
        home / ".config" / "openai" / "auth.json",
        home / ".config" / "openai" / "credentials.json",
    ]
    if os.name == "nt":
        local_app = os.environ.get("LOCALAPPDATA", "")
        app_data = os.environ.get("APPDATA", "")
        for base in (local_app, app_data):
            if not base:
                continue
            bp_ = Path(base)
            candidates += [
                bp_ / "openai" / "auth.json",
                bp_ / "OpenAI" / "auth.json",
                bp_ / "openai-nodejs" / "auth.json",
                bp_ / "openai-codex-nodejs" / "auth.json",
                bp_ / "openai-codex-nodejs" / "config.json",
            ]
    openai_cfg_dir = os.environ.get("OPENAI_CONFIG_DIR", "")
    if openai_cfg_dir:
        candidates.append(Path(openai_cfg_dir) / "auth.json")

    for path in candidates:
        if path.exists():
            mtime = path.stat().st_mtime
            modified_iso = datetime.datetime.fromtimestamp(mtime).isoformat(timespec="seconds")
            expires_at: str | None = None
            try:
                auth_data = json.loads(path.read_text(encoding="utf-8"))
                ts = auth_data.get("expiresAt") or auth_data.get("expires_at")
                if ts:
                    ts_sec = int(ts) / 1000 if int(ts) > 1e10 else int(ts)
                    expires_at = datetime.datetime.fromtimestamp(ts_sec).isoformat(timespec="seconds")
            except Exception:
                pass
            return jsonify({"exists": True, "path": str(path), "modified": modified_iso, "expires_at": expires_at})

    # 2. CLI probe
    codex_bin = ""
    try:
        env_cfg = _read_env()
        codex_bin = env_cfg.get("CODEX_CLI_BIN", "").strip()
    except Exception:
        pass
    if not codex_bin:
        codex_bin = shutil.which("codex") or ""
    if not codex_bin:
        local_app2 = os.environ.get("LOCALAPPDATA", "")
        if local_app2:
            candidate2 = Path(local_app2) / "OpenAI" / "Codex" / "bin" / "codex.exe"
            if candidate2.exists():
                codex_bin = str(candidate2)
    if not codex_bin:
        app_data2 = os.environ.get("APPDATA", "")
        if app_data2 and sys.platform == "win32":
            for nm in ("codex.cmd", "codex"):
                c2 = Path(app_data2) / "npm" / nm
                if c2.exists():
                    codex_bin = str(c2)
                    break

    if codex_bin:
        create_no_window = 0x08000000 if sys.platform == "win32" else 0
        bin_lower = codex_bin.lower()
        if sys.platform == "win32" and (bin_lower.endswith(".cmd") or bin_lower.endswith(".bat")):
            probe_cmd = ["cmd", "/c", codex_bin, "exec", "--json", "--skip-git-repo-check", "-m", "o4-mini", "-"]
        else:
            probe_cmd = [codex_bin, "exec", "--json", "--skip-git-repo-check", "-m", "o4-mini", "-"]
        probe_env = {k: v for k, v in os.environ.items() if k != "OPENAI_API_KEY"}
        try:
            proc = subprocess.Popen(
                probe_cmd,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, encoding="utf-8", errors="replace",
                creationflags=create_no_window, env=probe_env,
            )
            try:
                out, err = proc.communicate(input=".\n", timeout=4)
                combined = (out + err).lower()
                _no_auth = ("codex login", "not logged in", "please log in",
                            "not authenticated", "login required", "sign in")
                if any(kw in combined for kw in _no_auth):
                    return jsonify({"exists": False, "method": "cli_probe"})
                return jsonify({"exists": True, "method": "cli_probe",
                                "note": "Sesion activa (credenciales en keychain del SO)"})
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.communicate()
                return jsonify({"exists": True, "method": "cli_probe_timeout",
                                "note": "Sesion activa"})
        except Exception as _pe:
            logger.debug("codex-session probe failed: %s", _pe)

    return jsonify({"exists": False})


@bp.delete("/global-config/codex-session")
def delete_codex_session():
    """Elimina las credenciales OAuth almacenadas por el Codex CLI.

    Respuesta: { ok: bool, path?: str, note?: str, error?: str }
    """
    import subprocess
    import sys
    import shutil

    codex_bin = ""
    try:
        env_cfg = _read_env()
        codex_bin = env_cfg.get("CODEX_CLI_BIN", "").strip()
    except Exception:
        pass
    if not codex_bin:
        codex_bin = shutil.which("codex") or ""
    if not codex_bin:
        app_data2 = os.environ.get("APPDATA", "")
        if app_data2:
            for nm in ("codex.cmd", "codex"):
                c2 = Path(app_data2) / "npm" / nm
                if c2.exists():
                    codex_bin = str(c2)
                    break

    if codex_bin:
        create_no_window = 0x08000000 if sys.platform == "win32" else 0
        bin_lower = codex_bin.lower()
        if sys.platform == "win32" and (bin_lower.endswith(".cmd") or bin_lower.endswith(".bat")):
            cmd = ["cmd", "/c", codex_bin, "logout"]
        else:
            cmd = [codex_bin, "logout"]
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=10,
                creationflags=create_no_window,
            )
            combined = (result.stdout + result.stderr).strip()
            logger.info("codex logout: %s", combined)
            return jsonify({"ok": True, "note": combined or "Sesion cerrada"})
        except Exception as exc:
            logger.warning("codex logout failed, falling back to file delete: %s", exc)

    # Fallback: borrar auth.json directamente
    home = Path.home()
    candidates: list[Path] = [
        home / ".codex" / "auth.json",
        home / ".openai" / "auth.json",
    ]
    if os.name == "nt":
        for base in (os.environ.get("LOCALAPPDATA", ""), os.environ.get("APPDATA", "")):
            if base:
                candidates += [
                    Path(base) / "openai" / "auth.json",
                    Path(base) / "OpenAI" / "auth.json",
                ]
    for path in candidates:
        if path.exists():
            try:
                path.unlink()
                logger.info("codex-session: deleted auth.json at %s", path)
                return jsonify({"ok": True, "path": str(path)})
            except Exception as exc:
                return jsonify({"ok": False, "error": str(exc), "path": str(path)})

    return jsonify({"ok": False, "error": "No se encontro archivo de sesion para eliminar."})


# ===========================================================================
# Claude Code CLI -- deteccion de binario, version y sesion de autenticacion
# ===========================================================================

def _resolve_claude_bin(explicit: str | None = None) -> str:
    """Resuelve la ruta del binario `claude`.

    Orden: argumento explicito > .env (CLAUDE_CODE_CLI_BIN) > PATH > rutas
    conocidas de instalacion en Windows (winget, npm global). Devuelve "claude"
    como ultimo recurso para que el caller reporte FileNotFoundError con un
    mensaje util.
    """
    import shutil
    import sys

    candidate = (explicit or "").strip().strip('"')
    if not candidate:
        candidate = _read_env().get("CLAUDE_CODE_CLI_BIN", "").strip()

    if candidate:
        found = shutil.which(candidate)
        if found:
            return found
        if Path(candidate).exists():
            return candidate

    found = shutil.which("claude")
    if found:
        return found

    if sys.platform == "win32":
        local_app = os.environ.get("LOCALAPPDATA", "")
        app_data = os.environ.get("APPDATA", "")
        winget_root = (
            Path(local_app) / "Microsoft" / "WinGet" / "Packages" if local_app else None
        )
        known: list[Path] = []
        if winget_root and winget_root.exists():
            # winget instala en una carpeta con sufijo aleatorio; buscamos claude.exe
            try:
                for pkg in winget_root.glob("Anthropic.ClaudeCode_*"):
                    exe = pkg / "claude.exe"
                    if exe.exists():
                        known.append(exe)
            except Exception:
                pass
        if local_app:
            known.append(Path(local_app) / "AnthropicClaude" / "claude.exe")
        if app_data:
            known.append(Path(app_data) / "npm" / "claude.cmd")
            known.append(Path(app_data) / "npm" / "claude.exe")
        for path in known:
            if path.exists():
                return str(path)
    else:
        for path in (
            Path("/usr/local/bin/claude"),
            Path.home() / ".local" / "bin" / "claude",
            Path.home() / ".claude" / "local" / "claude",
        ):
            if path.exists():
                return str(path)

    return "claude"


def _claude_cmd_prefix(claude_bin: str) -> list[str]:
    """Prefijo de comando que respeta .cmd/.bat en Windows."""
    import sys

    bin_lower = claude_bin.lower()
    if sys.platform == "win32" and (bin_lower.endswith(".cmd") or bin_lower.endswith(".bat")):
        return ["cmd", "/c", claude_bin]
    return [claude_bin]


@bp.post("/global-config/test-claude")
def test_claude_connection():
    """Verifica el binario de Claude Code CLI y devuelve la version.

    Body (opcional): { claude_bin: str }
    Respuesta: { ok, bin, version, debug_log?, error? }
    """
    import subprocess
    import sys

    data = request.get_json(force=True, silent=True) or {}
    claude_bin = _resolve_claude_bin(data.get("claude_bin"))
    create_no_window = 0x08000000 if sys.platform == "win32" else 0
    cmd = _claude_cmd_prefix(claude_bin) + ["--version"]

    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=20,
            creationflags=create_no_window,
        )
        version_raw = (proc.stdout or proc.stderr or "").strip()
        version = version_raw.splitlines()[0] if version_raw else "OK"
        if proc.returncode != 0 and not version_raw:
            return jsonify({"ok": False, "bin": claude_bin,
                            "error": f"El binario respondio con codigo {proc.returncode}."})
        logger.info("test-claude: bin=%s version=%s", claude_bin, version)
        return jsonify({"ok": True, "bin": claude_bin, "version": version})
    except FileNotFoundError:
        return jsonify({
            "ok": False,
            "bin": claude_bin,
            "error": (
                f"Binario no encontrado: '{claude_bin}'. "
                "Instala Claude Code con:  npm install -g @anthropic-ai/claude-code  "
                "(o winget install Anthropic.ClaudeCode) o configura la ruta completa."
            ),
        })
    except subprocess.TimeoutExpired:
        return jsonify({"ok": False, "bin": claude_bin, "error": "Timeout al ejecutar claude --version."})
    except Exception as exc:
        return jsonify({"ok": False, "bin": claude_bin, "error": str(exc)})


@bp.get("/global-config/claude-session")
def get_claude_session_status():
    """Estado de autenticacion de Claude Code CLI via `claude auth status --json`.

    Respuesta: {
      exists, bin, logged_in, auth_method?, email?, org_name?,
      subscription_type?, error?
    }
    """
    import subprocess
    import sys

    claude_bin = _resolve_claude_bin()
    create_no_window = 0x08000000 if sys.platform == "win32" else 0
    cmd = _claude_cmd_prefix(claude_bin) + ["auth", "status", "--json"]

    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=20,
            creationflags=create_no_window,
        )
    except FileNotFoundError:
        return jsonify({"exists": False, "bin": claude_bin,
                        "error": f"Binario no encontrado: '{claude_bin}'."})
    except subprocess.TimeoutExpired:
        return jsonify({"exists": False, "bin": claude_bin, "error": "Timeout en claude auth status."})
    except Exception as exc:
        return jsonify({"exists": False, "bin": claude_bin, "error": str(exc)})

    raw = (proc.stdout or "").strip()
    # `claude auth status --json` imprime JSON; tomamos el primer objeto valido.
    info: dict = {}
    if raw:
        try:
            info = json.loads(raw)
        except json.JSONDecodeError:
            start = raw.find("{")
            end = raw.rfind("}")
            if start != -1 and end != -1 and end > start:
                try:
                    info = json.loads(raw[start:end + 1])
                except json.JSONDecodeError:
                    info = {}

    logged_in = bool(info.get("loggedIn"))
    return jsonify({
        "exists": logged_in,
        "bin": claude_bin,
        "logged_in": logged_in,
        "auth_method": info.get("authMethod"),
        "email": info.get("email"),
        "org_name": info.get("orgName"),
        "subscription_type": info.get("subscriptionType"),
    })


@bp.post("/global-config/claude-login")
def claude_login():
    """Ejecuta `claude auth login` para autenticar via OAuth (subscripcion/cuenta).

    Abre el navegador y completa via callback local, igual que codex login.
    Body (opcional): { claude_bin: str }
    Respuesta: { ok, output?, error? }
    """
    import subprocess

    data = request.get_json(force=True, silent=True) or {}
    claude_bin = _resolve_claude_bin(data.get("claude_bin"))
    cmd = _claude_cmd_prefix(claude_bin) + ["auth", "login"]
    logger.info("claude-login: launching %s", cmd)

    try:
        proc = subprocess.run(
            cmd,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=300,
        )
        output = (proc.stdout or proc.stderr or "").strip()
        if proc.returncode == 0:
            logger.info("claude-login: exito")
            return jsonify({"ok": True, "output": output})
        logger.warning("claude-login fallo (rc=%d): %s", proc.returncode, output[:200])
        return jsonify({"ok": False, "error": output or f"El proceso termino con codigo {proc.returncode}."})
    except FileNotFoundError:
        return jsonify({"ok": False, "error": f"Binario no encontrado: '{claude_bin}'."})
    except subprocess.TimeoutExpired:
        return jsonify({"ok": False, "error": "Timeout: el login no se completo en 5 minutos."})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)})


@bp.delete("/global-config/claude-session")
def delete_claude_session():
    """Cierra la sesion de Claude Code CLI via `claude auth logout`.

    Respuesta: { ok, note?, error? }
    """
    import subprocess
    import sys

    claude_bin = _resolve_claude_bin()
    create_no_window = 0x08000000 if sys.platform == "win32" else 0
    cmd = _claude_cmd_prefix(claude_bin) + ["auth", "logout"]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=20,
            creationflags=create_no_window,
        )
        combined = (result.stdout + result.stderr).strip()
        logger.info("claude logout: %s", combined)
        return jsonify({"ok": True, "note": combined or "Sesion cerrada"})
    except FileNotFoundError:
        return jsonify({"ok": False, "error": f"Binario no encontrado: '{claude_bin}'."})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)})
