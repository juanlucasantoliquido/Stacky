"""
Bridge al engine LLM real (copilot / mock).

- mock: outputs canned para validar la UI sin gastar tokens.
- copilot: GitHub Copilot Chat API real (OpenAI-compatible).
  Token OAuth obtenido vía `gh auth token`.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from typing import Callable

import requests

from config import config


logger = logging.getLogger(__name__)


def _models_endpoint() -> str:
    """Endpoint para listar modelos (siempre api.githubcopilot.com, acepta gho_ token)."""
    return config.COPILOT_MODELS_ENDPOINT


def _editor_headers() -> dict[str, str]:
    return {
        "Editor-Version": "vscode/1.95.0",
        "Editor-Plugin-Version": "copilot-chat/0.20.0",
        "User-Agent": "GitHubCopilotChat/0.20.0",
    }


def _get_copilot_token() -> str:
    """Devuelve el token de GitHub para usar como Bearer directo en api.githubcopilot.com.

    Los tokens gho_/ghp_/ghu_ con scope 'copilot' funcionan directamente como Bearer
    contra api.githubcopilot.com sin necesidad de exchange interno.
    """
    return _gh_auth_token()



# Cache de model limits: model_id → max_output_tokens
_model_limits: dict[str, int] = {}

# Modelos de razonamiento que no soportan `max_tokens` y requieren `max_completion_tokens`.
_REASONING_PREFIXES = ("o1", "o3", "o4", "gpt-5", "gpt5")


def _is_reasoning_model(model_id: str) -> bool:
    lm = model_id.lower()
    return any(lm.startswith(p) or f"/{p}" in lm for p in _REASONING_PREFIXES)


def list_copilot_models(timeout_sec: int = 15) -> list[dict]:
    """Lista los modelos disponibles via GitHub Models catalog.

    Usa https://models.github.ai/catalog/models que acepta el gho_ token directamente.
    Los IDs retornados son el short name (p.ej. `gpt-4o`) que acepta el endpoint de inference.
    """
    token = _get_copilot_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }
    url = _models_endpoint()
    response = requests.get(url, headers=headers, timeout=timeout_sec)
    if response.status_code != 200:
        body = response.text[:500]
        raise RuntimeError(f"GitHub Models catalog HTTP {response.status_code}: {body}")
    try:
        raw = response.json()
    except ValueError as exc:
        raise RuntimeError(f"GitHub Models catalog non-JSON: {response.text[:500]}") from exc

    if not isinstance(raw, list):
        return []

    out: list[dict] = []
    for m in raw:
        if not isinstance(m, dict):
            continue
        # ID en formato publisher/model-name. El inference endpoint acepta solo el short name.
        full_id = m.get("id") or ""
        short_id = full_id.split("/", 1)[1] if "/" in full_id else full_id
        if not short_id:
            continue
        # Excluir modelos de embedding
        if "embed" in short_id.lower() or "embed" in (m.get("name") or "").lower():
            continue
        limits = m.get("limits") or {}
        max_out = int(limits.get("max_output_tokens") or 4096)
        _model_limits[short_id] = max_out
        out.append({
            "id": short_id,
            "name": str(m.get("name") or short_id),
            "vendor": str(m.get("publisher") or ""),
            "family": "",
            "preview": "preview" in (m.get("name") or "").lower(),
            "capabilities": {"max_output_tokens": max_out},
        })
    return out


@dataclass
class BridgeResponse:
    text: str
    format: str = "markdown"
    metadata: dict = None  # type: ignore[assignment]


LogFn = Callable[[str, str], None]


_CANCELLED: set[int] = set()


def cancel(execution_id: int) -> None:
    _CANCELLED.add(execution_id)


def _is_cancelled(execution_id: int | None) -> bool:
    return execution_id is not None and execution_id in _CANCELLED


def invoke(
    *,
    agent_type: str,
    system: str,
    user: str,
    on_log: LogFn,
    execution_id: int | None = None,
    model: str | None = None,
    project_name: str | None = None,
    workspace_root: str | None = None,
    bridge_port: int | None = None,
) -> BridgeResponse:
    backend = config.LLM_BACKEND.lower()
    if backend == "mock":
        return _invoke_mock(agent_type=agent_type, on_log=on_log, execution_id=execution_id, model=model)
    if backend == "vscode_bridge":
        return _invoke_vscode_bridge(
            agent_type=agent_type,
            system=system,
            user=user,
            on_log=on_log,
            execution_id=execution_id,
            model=model,
            project_name=project_name,
            workspace_root=workspace_root,
            bridge_port=bridge_port,
        )
    if backend == "copilot":
        return _invoke_copilot(
            agent_type=agent_type, system=system, user=user, on_log=on_log, execution_id=execution_id, model=model
        )
    if backend == "claude_cli":
        return _invoke_claude_cli(
            agent_type=agent_type, system=system, user=user, on_log=on_log, execution_id=execution_id, model=model
        )
    raise NotImplementedError(f"LLM_BACKEND='{backend}' no soportado todavía")


# ── VS Code Bridge ────────────────────────────────────────────────────────────

def _fallback_bridge_url() -> str:
    return f"http://127.0.0.1:{config.VSCODE_BRIDGE_PORT}"


VSCODE_BRIDGE_URL = _fallback_bridge_url()


def _bridge_target(
    *,
    project_name: str | None = None,
    workspace_root: str | None = None,
    bridge_port: int | None = None,
    ensure_ready: bool = False,
) -> tuple[str, dict]:
    metadata = {
        "project_name": project_name,
        "workspace_root": workspace_root,
        "bridge_port": bridge_port,
    }

    if bridge_port:
        return f"http://127.0.0.1:{bridge_port}", metadata

    try:
        from services.project_context import ensure_project_vscode, resolve_project_context
        from services.vscode_instance_manager import get_or_assign_port

        ctx = None
        if ensure_ready and project_name:
            ctx = ensure_project_vscode(project_name)
        else:
            ctx = resolve_project_context(project_name=project_name) if project_name else resolve_project_context()
        if ctx is not None:
            port = ctx.vscode_port
            if port is None and ctx.workspace_root:
                port = get_or_assign_port(ctx.stacky_project_name, ctx.workspace_root)
            if ensure_ready and project_name and port is not None and ctx.vscode_port != port:
                ctx = ctx.with_vscode_port(port)
            if port is not None:
                metadata.update(
                    {
                        "project_name": ctx.stacky_project_name,
                        "workspace_root": ctx.workspace_root,
                        "bridge_port": port,
                    }
                )
                return f"http://127.0.0.1:{port}", metadata
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "No se pudo resolver bridge target project-aware (project=%s, workspace_root=%s): %s",
            project_name,
            workspace_root,
            exc,
        )

    metadata["bridge_port"] = config.VSCODE_BRIDGE_PORT
    return _fallback_bridge_url(), metadata


def _vscode_bridge_health(
    project_name: str | None = None,
    workspace_root: str | None = None,
    bridge_port: int | None = None,
) -> bool:
    """Verifica que la extensión Stacky Agents esté corriendo y tenga Copilot Chat."""
    bridge_url, _ = _bridge_target(
        project_name=project_name,
        workspace_root=workspace_root,
        bridge_port=bridge_port,
    )
    try:
        r = requests.get(f"{bridge_url}/health", timeout=3)
        return r.status_code == 200 and r.json().get("ok") is True
    except Exception:
        return False


def list_vscode_bridge_models(
    timeout_sec: int = 5,
    *,
    project_name: str | None = None,
    workspace_root: str | None = None,
    bridge_port: int | None = None,
) -> list[dict]:
    """Lista los modelos disponibles en VS Code (vía vscode.lm API)."""
    bridge_url, _ = _bridge_target(
        project_name=project_name,
        workspace_root=workspace_root,
        bridge_port=bridge_port,
    )
    try:
        r = requests.get(f"{bridge_url}/models", timeout=timeout_sec)
        if r.status_code == 200:
            return r.json().get("models", [])
    except Exception:
        pass
    return []


def _invoke_vscode_bridge(
    *,
    agent_type: str,
    system: str,
    user: str,
    on_log: LogFn,
    execution_id: int | None,
    model: str | None = None,
    project_name: str | None = None,
    workspace_root: str | None = None,
    bridge_port: int | None = None,
) -> BridgeResponse:
    """Invoca el modelo de lenguaje de VS Code (Copilot) via el bridge HTTP de la extensión.

    La extensión usa vscode.lm.selectChatModels + model.sendRequest para invocar
    Copilot programáticamente y devuelve la respuesta completa al backend.
    La respuesta real se guarda en el output del agente.
    """
    started = time.time()

    if _is_cancelled(execution_id):
        raise CancelledError("cancelled by user")

    bridge_url, bridge_meta = _bridge_target(
        project_name=project_name,
        workspace_root=workspace_root,
        bridge_port=bridge_port,
        ensure_ready=bool(project_name),
    )
    target_port = bridge_meta.get("bridge_port")
    target_workspace = bridge_meta.get("workspace_root") or workspace_root

    on_log("info", "verificando VS Code bridge")
    if not _vscode_bridge_health(
        project_name=project_name,
        workspace_root=workspace_root,
        bridge_port=bridge_meta.get("bridge_port"),
    ):
        raise RuntimeError(
            f"VS Code bridge no responde en 127.0.0.1:{target_port}. "
            "Asegurate de tener la extensión Stacky Agents instalada y VS Code abierto. "
            "Si acabas de instalar la extensión, recargá VS Code (Ctrl+Shift+P → Developer: Reload Window)."
        )

    chosen_model = model or config.COPILOT_MODEL
    on_log(
        "info",
        "invocando Copilot via VS Code bridge "
        f"(project={bridge_meta.get('project_name') or project_name or 'default'}, "
        f"workspace_root={target_workspace or '(unknown)'}, "
        f"bridge_port={target_port}, model={chosen_model}, "
        f"system={len(system)}c user={len(user)}c)",
    )

    # Timeout de invocación: 4 minutos para requests complejos
    INVOKE_TIMEOUT = 300

    payload = {
        "system": system,
        "user": user,
        "agent": agent_type,
        "model": chosen_model,
        "timeout_sec": INVOKE_TIMEOUT - 30,  # margen para overhead HTTP
    }

    try:
        r = requests.post(
            f"{bridge_url}/invoke",
            json=payload,
            timeout=INVOKE_TIMEOUT,
        )
    except requests.Timeout:
        raise RuntimeError(f"VS Code bridge timeout después de {INVOKE_TIMEOUT}s")
    except requests.RequestException as exc:
        raise RuntimeError(f"VS Code bridge request failed: {exc}") from exc

    try:
        data = r.json()
    except Exception:
        raise RuntimeError(f"VS Code bridge respuesta inválida ({r.status_code}): {r.text[:200]}")

    if not r.ok or not data.get("ok"):
        raise RuntimeError(f"VS Code bridge error: {data.get('error', r.text[:300])}")

    response_text = data.get("text") or ""
    model_used = data.get("model_used", chosen_model)
    chars_out = len(response_text)
    elapsed = int((time.time() - started) * 1000)

    on_log("info", f"respuesta recibida de Copilot ({chars_out} chars, modelo: {model_used}, {elapsed}ms)")

    return BridgeResponse(
        text=response_text,
        format="markdown",
        metadata={
            "model": model_used,
            "tokens_in": (len(system) + len(user)) // 4,
            "tokens_out": chars_out // 4,
            "duration_ms": elapsed,
            "sub_agents": [],
            "vscode_bridge": True,
            "bridge_port": target_port,
            "workspace_root": target_workspace,
            "stacky_project_name": bridge_meta.get("project_name") or project_name,
        },
    )




def _invoke_mock(
    *,
    agent_type: str,
    on_log: LogFn,
    execution_id: int | None,
    model: str | None = None,
) -> BridgeResponse:
    """Simula una ejecución con steps y delays para que la UI muestre logs en vivo."""
    started = time.time()
    steps = [
        ("info", "leyendo metadata del ticket"),
        ("info", "explorando documentación"),
        ("info", "consultando contexto técnico"),
        ("info", "compilando análisis"),
    ]
    for level, msg in steps:
        if _is_cancelled(execution_id):
            raise CancelledError("cancelled by user")
        on_log(level, msg)
        time.sleep(0.4)

    output = MOCK_OUTPUTS.get(agent_type, MOCK_OUTPUTS["default"])

    return BridgeResponse(
        text=output,
        format="markdown",
        metadata={
            "model": model or "mock-1.0",
            "tokens_in": 1200,
            "tokens_out": 600,
            "duration_ms": int((time.time() - started) * 1000),
            "sub_agents": [],
        },
    )


def _gh_auth_token() -> str:
    """Obtiene un OAuth token de GitHub Copilot probando varias fuentes.

    Orden de resolución:
      1. env `GH_TOKEN` o `GITHUB_TOKEN`
      2. archivo `backend/.copilot_token` (texto plano, gitignored)
      3. `gh auth token` (busca en PATH y en `C:/Program Files/GitHub CLI/gh.exe`)
      4. `~/.config/github-copilot/hosts.json` o `apps.json` (formato legacy plugin)

    Raises:
        RuntimeError: si no se encontró ningún token válido.
    """
    import os
    from pathlib import Path

    # 1. env vars
    for var in ("GH_TOKEN", "GITHUB_TOKEN", "COPILOT_TOKEN"):
        token = (os.environ.get(var) or "").strip()
        if token:
            return token

    # 2. archivo local del backend
    backend_root = Path(__file__).resolve().parent
    token_file = backend_root / ".copilot_token"
    if token_file.is_file():
        token = token_file.read_text(encoding="utf-8").strip()
        if token:
            return token

    # 3. gh CLI (PATH y ruta default Windows)
    gh_candidates = ["gh", r"C:\Program Files\GitHub CLI\gh.exe"]
    for gh_bin in gh_candidates:
        try:
            result = subprocess.run(
                [gh_bin, "auth", "token"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except (FileNotFoundError, OSError):
            continue
        except subprocess.TimeoutExpired:
            continue
        if result.returncode == 0:
            token = result.stdout.strip()
            if token:
                return token

    # 4. hosts.json / apps.json del plugin Copilot
    home = Path(os.path.expanduser("~"))
    candidates = [
        home / ".config" / "github-copilot" / "hosts.json",
        home / ".config" / "github-copilot" / "apps.json",
        home / "AppData" / "Local" / "github-copilot" / "hosts.json",
        home / "AppData" / "Roaming" / "github-copilot" / "hosts.json",
    ]
    for path in candidates:
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        token = _extract_copilot_token_from_hosts(data)
        if token:
            return token

    raise RuntimeError(
        "No se encontró token de GitHub Copilot. Setea env GH_TOKEN/GITHUB_TOKEN, "
        "creá backend/.copilot_token con el token, o corré `gh auth login`."
    )


def _extract_copilot_token_from_hosts(data: dict) -> str | None:
    """Extrae oauth_token de la estructura de hosts.json/apps.json del plugin Copilot."""
    if not isinstance(data, dict):
        return None
    for key, value in data.items():
        if not isinstance(value, dict):
            continue
        token = value.get("oauth_token") or value.get("token")
        if isinstance(token, str) and token.strip():
            return token.strip()
        if "github.com" in key.lower():
            for sub in value.values():
                if isinstance(sub, dict):
                    sub_token = sub.get("oauth_token") or sub.get("token")
                    if isinstance(sub_token, str) and sub_token.strip():
                        return sub_token.strip()
    return None


def _invoke_copilot(
    *,
    agent_type: str,
    system: str,
    user: str,
    on_log: LogFn,
    execution_id: int | None,
    model: str | None = None,
) -> BridgeResponse:
    """Llama a la GitHub Copilot Chat API (OpenAI-compatible)."""
    started = time.time()
    chosen_model = model or config.COPILOT_MODEL

    if _is_cancelled(execution_id):
        raise CancelledError("cancelled by user")

    on_log("info", "obteniendo token Copilot")
    try:
        token = _get_copilot_token()
    except RuntimeError as exc:
        on_log("error", f"auth falló: {exc}")
        logger.error("copilot auth failed: %s", exc)
        raise

    on_log("info", f"invocando copilot API model={chosen_model}")
    logger.info("invocando copilot API model=%s agent=%s", chosen_model, agent_type)

    # Calcular max_tokens seguros para este modelo
    model_max_out = _model_limits.get(chosen_model, 4096)
    safe_max_out = min(4096, model_max_out)

    payload: dict = {
        "model": chosen_model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.2,
        "stream": False,
    }
    # Modelos de razonamiento (o1, o3, gpt-5) no aceptan `max_tokens`,
    # usan `max_completion_tokens` y no soportan `temperature`.
    if _is_reasoning_model(chosen_model):
        payload["max_completion_tokens"] = safe_max_out
        del payload["temperature"]
    else:
        payload["max_tokens"] = safe_max_out

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Copilot-Integration-Id": config.COPILOT_INTEGRATION_ID,
        "Accept": "application/json",
        **_editor_headers(),
    }

    try:
        response = requests.post(
            config.COPILOT_ENDPOINT,
            headers=headers,
            data=json.dumps(payload),
            timeout=120,
        )
    except requests.RequestException as exc:
        on_log("error", f"error de red: {exc}")
        logger.exception("copilot request failed")
        raise RuntimeError(f"copilot request failed: {exc}") from exc

    if _is_cancelled(execution_id):
        raise CancelledError("cancelled by user")

    if response.status_code != 200:
        body = response.text[:2000]
        on_log("error", f"HTTP {response.status_code}: {body}")
        logger.error("copilot HTTP %s body=%s", response.status_code, body)
        raise RuntimeError(
            f"copilot API HTTP {response.status_code}: {body}"
        )

    try:
        data = response.json()
    except ValueError as exc:
        on_log("error", "respuesta no es JSON válido")
        raise RuntimeError(f"copilot returned non-JSON: {response.text[:500]}") from exc

    try:
        text = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        on_log("error", f"respuesta inesperada: {data}")
        raise RuntimeError(f"copilot response malformed: {data}") from exc

    usage = data.get("usage") or {}
    tokens_in = usage.get("prompt_tokens", 0)
    tokens_out = usage.get("completion_tokens", 0)
    on_log("info", f"completado tokens_in={tokens_in} tokens_out={tokens_out}")

    return BridgeResponse(
        text=text,
        format="markdown",
        metadata={
            "model": data.get("model") or chosen_model,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "duration_ms": int((time.time() - started) * 1000),
            "sub_agents": [],
            "copilot_id": data.get("id"),
            "finish_reason": (data.get("choices") or [{}])[0].get("finish_reason"),
        },
    )


# ── Claude CLI (cuenta Claude del operador, sin GitHub Copilot) ─────────────────

def _resolve_claude_bin() -> str:
    """Resuelve el binario `claude` (PATH o rutas npm conocidas en Windows).

    Mantiene este resolver liviano y local para no acoplar el gateway LLM al
    runner del agente. Lanza RuntimeError accionable si no lo encuentra.
    """
    configured = (config.CLAUDE_CODE_CLI_BIN or "claude").strip().strip('"')
    found = shutil.which(configured)
    if found:
        return found
    candidates: list[str] = []
    if configured.lower() not in {"claude", "claude.exe", "claude.cmd"}:
        candidates.append(configured)
    if os.name == "nt":
        appdata = os.environ.get("APPDATA")
        if appdata:
            candidates.append(os.path.join(appdata, "npm", "claude.cmd"))
            candidates.append(os.path.join(appdata, "npm", "claude.exe"))
    else:
        candidates.append("/usr/local/bin/claude")
        candidates.append(os.path.expanduser("~/.local/bin/claude"))
    for cand in candidates:
        if cand and os.path.exists(cand):
            return cand
    raise RuntimeError(
        "LLM_BACKEND=claude_cli pero no encontré el CLI 'claude'. "
        "Instalalo (npm i -g @anthropic-ai/claude-code) y logueate con tu cuenta "
        "Claude, o configurá CLAUDE_CODE_CLI_BIN con la ruta al binario."
    )


def _parse_claude_cli_json(stdout: str) -> tuple[str, int, int, str | None]:
    """Parsea la salida `--output-format json` del CLI claude.

    Espera un objeto JSON con `result` (texto) y `usage`
    (input_tokens/output_tokens). Tolera una lista de eventos (busca el de
    type=result). Si no parsea, devuelve ("", 0, 0, None) y el caller cae al
    stdout crudo.
    """
    raw = (stdout or "").strip()
    if not raw:
        return "", 0, 0, None
    try:
        data = json.loads(raw)
    except ValueError:
        try:
            data = json.loads(raw.splitlines()[-1])
        except (ValueError, IndexError):
            return "", 0, 0, None
    if isinstance(data, list):
        data = next(
            (e for e in reversed(data) if isinstance(e, dict) and e.get("type") == "result"),
            None,
        )
    if not isinstance(data, dict):
        return "", 0, 0, None
    text = data.get("result") or data.get("text") or ""
    usage = data.get("usage") or {}
    tin = int(usage.get("input_tokens") or usage.get("prompt_tokens") or 0)
    tout = int(usage.get("output_tokens") or usage.get("completion_tokens") or 0)
    finish = data.get("subtype") or data.get("stop_reason") or data.get("finish_reason")
    return str(text), tin, tout, finish


def _invoke_claude_cli(
    *,
    agent_type: str,
    system: str,
    user: str,
    on_log: LogFn,
    execution_id: int | None,
    model: str | None = None,
) -> BridgeResponse:
    """Completa vía el CLI `claude` (modo print, one-shot) usando la cuenta
    Claude del operador (OAuth de disco / suscripción Pro). NO usa GitHub Copilot.

    Es la contraparte interna de `claude_code_cli` (runtime del agente): permite
    que el cerebro de Stacky (enriquecimiento, criterios, KPIs, chat) corra con la
    misma cuenta Claude en vez de Copilot. El `system` se antepone al `user` en un
    único prompt por stdin (las llamadas internas no requieren rol system separado,
    y así se evita el límite de longitud de línea en Windows).
    """
    from services.agent_env import build_agent_env  # filtra secretos del subproceso

    started = time.time()
    chosen_model = model or config.CLAUDE_CODE_CLI_MODEL or "claude-sonnet-4-6"

    if _is_cancelled(execution_id):
        raise CancelledError("cancelled by user")

    claude_bin = _resolve_claude_bin()
    prompt = (f"{system.strip()}\n\n{user.strip()}".strip() if system else (user or "")).strip()

    cmd = [
        claude_bin, "-p",
        "--output-format", "json",
        "--model", chosen_model,
        "--dangerously-skip-permissions",
    ]
    # Completion interna: tope acotado (no el cap de sesión del agente, que es 30 min).
    timeout_sec = 300

    on_log("info", f"invocando claude CLI (cuenta Claude, sin Copilot) model={chosen_model}")
    logger.info("invocando claude_cli model=%s agent=%s", chosen_model, agent_type)

    creationflags = 0
    if os.name == "nt":
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

    try:
        proc = subprocess.run(
            cmd,
            input=prompt,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_sec,
            cwd=tempfile.gettempdir(),
            env=build_agent_env(),
            creationflags=creationflags,
        )
    except subprocess.TimeoutExpired as exc:
        on_log("error", f"claude CLI timeout tras {timeout_sec}s")
        logger.error("claude_cli timeout tras %ss", timeout_sec)
        raise RuntimeError(f"claude_cli timeout tras {timeout_sec}s") from exc

    if _is_cancelled(execution_id):
        raise CancelledError("cancelled by user")

    if proc.returncode != 0:
        err = (proc.stderr or "").strip()[:1500]
        on_log("error", f"claude CLI exit {proc.returncode}: {err}")
        logger.error("claude_cli exit=%s stderr=%s", proc.returncode, err)
        raise RuntimeError(f"claude_cli exit {proc.returncode}: {err or '(sin stderr)'}")

    text, tokens_in, tokens_out, finish = _parse_claude_cli_json(proc.stdout)
    if not text:
        # Sin result parseable: usar stdout crudo como último recurso (mejor que vacío).
        text = (proc.stdout or "").strip()
    on_log("info", f"completado claude_cli tokens_in={tokens_in} tokens_out={tokens_out}")

    return BridgeResponse(
        text=text,
        format="markdown",
        metadata={
            "model": chosen_model,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "duration_ms": int((time.time() - started) * 1000),
            "sub_agents": [],
            "backend": "claude_cli",
            "finish_reason": finish,
        },
    )


class CancelledError(RuntimeError):
    pass


MOCK_OUTPUTS: dict[str, str] = {
    "business": """\
# Epic estructurado — Mock

**RF-001** | Login con SSO
- Actor: usuario interno
- Reglas: validar dominio @ubimia.com
- Datos: email, password
- Prioridad: alta

**RF-002** | Listado de tickets propios
- Actor: usuario interno
- Reglas: paginación 50 por defecto
- Datos: ticket_id, título, estado
- Prioridad: media
""",
    "functional": """\
# Análisis funcional — Mock — RF-008

## Cobertura: GAP MENOR

El módulo de cobranzas cubre el 70% del requerimiento.
Falta integrar el flujo nuevo de notificación SMS.

## Plan de pruebas
1. Cobranza con cliente sin SMS configurado
2. Cobranza con SMS exitoso
3. Cobranza con SMS fallido y reintento
""",
    "technical": """\
# Análisis técnico — Mock

## 1. Traducción funcional → técnica
Flujo actual: `CobranzaService.Procesar()` → guarda en BD.
Flujo propuesto: `CobranzaService.Procesar()` → guarda + invoca `SmsNotifier.Send()`.

## 2. Alcance de cambios
| Archivo | Clase | Método | Líneas |
|---|---|---|---|
| CobranzaService.cs | CobranzaService | Procesar | ~85 |
| SmsNotifier.cs | SmsNotifier | Send | nuevo |

## 3. Plan de pruebas técnico
- TU-001: SMS exitoso → notif registrada en BD
- TU-002: SMS fallido → reintento programado

## 4. Tests unitarios obligatorios
- TU-001 ProcesarCobranzaConSmsTest
- TU-002 ProcesarCobranzaSinSmsTest

## 5. Notas para el desarrollador
- Reusar `IRetryPolicy` de `lib/Pacifico.Common/`
- RIDIOMA: agregar entrada `SMS_FAIL_RETRY`
""",
    "developer": """\
# Implementación completada — Mock

## 1. Resumen
| Archivo | Cambio | Líneas |
|---|---|---|
| CobranzaService.cs | +llamada a SmsNotifier | +12 / -2 |
| SmsNotifier.cs | nuevo | +85 |

## 2. Trazabilidad
Comentarios `// ADO-1234 | 2026-04-23 | SMS notif` en cada cambio.

## 3. Tests unitarios
| TU | Resultado | Cobertura |
|---|---|---|
| TU-001 | PASS | 100% |
| TU-002 | PASS | 100% |

## 4. Verificaciones de BD
- RIDIOMA `SMS_FAIL_RETRY` cargado: ok
- 0 registros huérfanos detectados

## 5. Compilación
MSBuild OK — 0 warnings, 0 errors.

## 6. Notas para QA
Datos de prueba sugeridos: cliente CUIT 30-12345678-9.
""",
    "qa": """\
# QA — Mock

## Verdict: PASS

### Casos verificados
- SMS notif exitoso
- SMS notif fallido con reintento
- Cobranza sin cambios funcionales (regresión)

### Tiempo de ejecución
14 minutos.

### Recomendación
Aprobar para merge.
""",
    "default": """\
# Mock output

(Reemplazá `LLM_BACKEND=mock` por `copilot` para invocar al engine real)
""",
}
