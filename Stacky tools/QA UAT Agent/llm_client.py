"""
llm_client.py — Standalone LLM client for QA UAT Agent tools.

Standalone (no Flask dependency). Tries VS Code bridge first (always available
when running inside a Stacky agent context), then falls back to GitHub Models
API directly via gh auth token.

Usage:
    from llm_client import call_llm, LLMError

    result = call_llm(
        model="gpt-5-mini",   # gpt-5-mini for fast/parsing, gpt-5 for analysis
        system="You are a QA analyst.",
        user="Classify this comment: ...",
        max_tokens=256,
    )
    # result -> {"text": "...", "model": "gpt-4.1-mini", "duration_ms": 843}

Environment variables (optional overrides):
    STACKY_LLM_BACKEND   — "vscode_bridge" (default) | "copilot_direct" | "mock"
    GH_TOKEN / GITHUB_TOKEN / COPILOT_TOKEN  — GitHub token for copilot_direct
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import time
import urllib.error
import urllib.request
from typing import Any

logger = logging.getLogger("stacky.qa_uat.llm_client")

# VS Code bridge endpoint (Stacky Agents extension)
_VSCODE_BRIDGE_URL = "http://127.0.0.1:5052"
# GitHub Models inference endpoint
_GITHUB_MODELS_ENDPOINT = "https://models.github.ai/inference/chat/completions"
# Reasoning model prefixes — use max_completion_tokens instead of max_tokens
_REASONING_PREFIXES = ("o1", "o3", "o4", "gpt-5", "gpt5")


class LLMError(RuntimeError):
    """Raised when all LLM backends fail."""


def _is_reasoning_model(model_id: str) -> bool:
    lm = model_id.lower()
    return any(lm.startswith(p) or "/" + p in lm for p in _REASONING_PREFIXES)


def _gh_auth_token() -> str:
    """Get GitHub token from env vars or gh CLI."""
    for var in ("GH_TOKEN", "GITHUB_TOKEN", "COPILOT_TOKEN"):
        token = (os.environ.get(var) or "").strip()
        if token:
            return token

    gh_candidates = ["gh", r"C:\Program Files\GitHub CLI\gh.exe"]
    for gh_bin in gh_candidates:
        try:
            result = subprocess.run(
                [gh_bin, "auth", "token"],
                capture_output=True, text=True, timeout=10, check=False,
            )
            if result.returncode == 0:
                token = result.stdout.strip()
                if token:
                    return token
        except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
            continue

    raise LLMError(
        "No GitHub token found. Set GH_TOKEN/GITHUB_TOKEN env var or run `gh auth login`."
    )


def _http_post_json(url: str, payload: dict, headers: dict, timeout: int = 60) -> dict:
    """Simple HTTP POST using stdlib urllib (no requests dependency)."""
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body_text = e.read().decode("utf-8", errors="replace")[:400]
        raise LLMError(f"HTTP {e.code} from {url}: {body_text}") from e
    except urllib.error.URLError as e:
        raise LLMError(f"URL error calling {url}: {e.reason}") from e


def _invoke_vscode_bridge(
    system: str, user: str, model: str, max_tokens: int, timeout: int
) -> dict:
    """Call VS Code bridge at 127.0.0.1:5052 (Stacky Agents extension)."""
    payload = {
        "system": system,
        "user": user,
        "agent": "qa",
        "model": model,
        "timeout_sec": timeout - 10,
    }
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    started = time.time()
    data = _http_post_json(
        f"{_VSCODE_BRIDGE_URL}/invoke",
        payload,
        headers,
        timeout=timeout,
    )
    if not data.get("ok"):
        raise LLMError(f"VS Code bridge returned error: {data.get('error', 'unknown')}")
    elapsed = int((time.time() - started) * 1000)
    return {
        "text": data.get("text", ""),
        "model": data.get("model_used", model),
        "duration_ms": elapsed,
    }


def _invoke_copilot_direct(
    system: str, user: str, model: str, max_tokens: int, timeout: int
) -> dict:
    """Call GitHub Models inference endpoint directly."""
    token = _gh_auth_token()
    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "stream": False,
    }
    if _is_reasoning_model(model):
        payload["max_completion_tokens"] = max_tokens
    else:
        payload["max_tokens"] = max_tokens
        payload["temperature"] = 0.2

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    started = time.time()
    data = _http_post_json(_GITHUB_MODELS_ENDPOINT, payload, headers, timeout=timeout)
    elapsed = int((time.time() - started) * 1000)

    choices = data.get("choices") or []
    if not choices:
        raise LLMError(f"No choices in GitHub Models response: {str(data)[:300]}")
    text = (choices[0].get("message") or {}).get("content") or ""
    model_used = data.get("model", model)
    return {"text": text, "model": model_used, "duration_ms": elapsed}


def _invoke_mock(system: str, user: str, model: str, max_tokens: int) -> dict:
    """Mock backend — returns a minimal valid JSON stub for unit tests."""
    return {
        "text": '{"role": "otros"}',
        "model": "mock-1.0",
        "duration_ms": 5,
    }


def _vscode_bridge_healthy() -> bool:
    """Check if VS Code bridge is running."""
    try:
        req = urllib.request.Request(
            f"{_VSCODE_BRIDGE_URL}/health",
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read())
            return bool(data.get("ok"))
    except Exception:
        return False


def call_llm(
    *,
    model: str,
    system: str,
    user: str,
    max_tokens: int = 1024,
    timeout: int = 120,
    _call_site: str = "",  # módulo llamador para trazabilidad en logs
) -> dict:
    """
    Call LLM and return {"text": str, "model": str, "duration_ms": int}.

    Backend selection (env STACKY_LLM_BACKEND):
        "vscode_bridge"   — VS Code bridge (default; best when running in agent context)
        "copilot_direct"  — GitHub Models API directly via gh token
        "mock"            — deterministic stub for unit tests

    Raises LLMError if all backends fail.
    """
    # Obtener el execution_logger activo para registrar la llamada LLM
    _exec_log = None
    try:
        from execution_logger import get_active_logger as _get_active_logger
        _exec_log = _get_active_logger()
    except ImportError:
        pass

    backend = os.environ.get("STACKY_LLM_BACKEND", "vscode_bridge").lower()

    if _exec_log is not None:
        try:
            _exec_log.llm_call(
                model=model,
                backend=backend,
                system_preview=system,
                user_preview=user,
                max_tokens=max_tokens,
                call_site=_call_site,
            )
        except Exception:  # noqa: BLE001
            pass

    if backend == "mock":
        result = _invoke_mock(system, user, model, max_tokens)
        if _exec_log is not None:
            try:
                _exec_log.llm_response(model=model, backend=backend,
                                       duration_ms=result.get("duration_ms", 0),
                                       text_preview=result.get("text", ""))
            except Exception:  # noqa: BLE001
                pass
        return result

    if backend == "vscode_bridge":
        if _vscode_bridge_healthy():
            try:
                result = _invoke_vscode_bridge(system, user, model, max_tokens, timeout)
                if _exec_log is not None:
                    try:
                        _exec_log.llm_response(model=result.get("model", model),
                                               backend="vscode_bridge",
                                               duration_ms=result.get("duration_ms", 0),
                                               text_preview=result.get("text", ""))
                    except Exception:  # noqa: BLE001
                        pass
                return result
            except LLMError as exc:
                logger.warning("VS Code bridge failed, falling back to copilot_direct: %s", exc)
                if _exec_log is not None:
                    try:
                        _exec_log.llm_error(model=model, backend="vscode_bridge", error=str(exc))
                    except Exception:  # noqa: BLE001
                        pass
        else:
            logger.info("VS Code bridge not available, using copilot_direct")
        try:
            result = _invoke_copilot_direct(system, user, model, max_tokens, timeout)
            if _exec_log is not None:
                try:
                    _exec_log.llm_response(model=result.get("model", model),
                                           backend="copilot_direct",
                                           duration_ms=result.get("duration_ms", 0),
                                           text_preview=result.get("text", ""))
                except Exception:  # noqa: BLE001
                    pass
            return result
        except LLMError as exc:
            if _exec_log is not None:
                try:
                    _exec_log.llm_error(model=model, backend="copilot_direct", error=str(exc))
                except Exception:  # noqa: BLE001
                    pass
            raise

    if backend == "copilot_direct":
        try:
            result = _invoke_copilot_direct(system, user, model, max_tokens, timeout)
            if _exec_log is not None:
                try:
                    _exec_log.llm_response(model=result.get("model", model),
                                           backend="copilot_direct",
                                           duration_ms=result.get("duration_ms", 0),
                                           text_preview=result.get("text", ""))
                except Exception:  # noqa: BLE001
                    pass
            return result
        except LLMError as exc:
            if _exec_log is not None:
                try:
                    _exec_log.llm_error(model=model, backend="copilot_direct", error=str(exc))
                except Exception:  # noqa: BLE001
                    pass
            raise

    raise LLMError(f"Unknown STACKY_LLM_BACKEND: {backend!r}. Use: vscode_bridge | copilot_direct | mock")


# ── Vision (multimodal) ──────────────────────────────────────────────────────
#
# call_llm_vision() es un superset multimodal de call_llm. La extensión es
# opt-in: ningún caller existente la usa, y el path de degradación es
# explícito — si el backend no soporta visión, se levanta LLMError y el
# caller puede caer a una alternativa (DOM-based detection en nuestro caso).
#
# Modelos esperados: gpt-4o, gpt-4o-mini (ambos disponibles en el endpoint
# GitHub Models que ya autenticamos con `gh auth token`). Cualquier otro
# modelo recibirá las imágenes en formato OpenAI-compatible content blocks
# y fallará gracefully si el modelo no soporta visión.


def _invoke_copilot_direct_vision(
    system: str,
    user: str,
    model: str,
    images: list[str],
    max_tokens: int,
    timeout: int,
) -> dict:
    """GitHub Models inference con content blocks multimodales.

    `images` es una lista de URLs (`https://...`) o data URLs
    (`data:image/png;base64,...`). El endpoint acepta el shape OpenAI:

        {"role": "user", "content": [
            {"type": "text", "text": "..."},
            {"type": "image_url", "image_url": {"url": "..."}}
        ]}
    """
    token = _gh_auth_token()
    user_content: list[dict[str, Any]] = [{"type": "text", "text": user}]
    for url in images:
        if not url:
            continue
        user_content.append({
            "type": "image_url",
            "image_url": {"url": url},
        })

    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user_content},
        ],
        "stream": False,
    }
    if _is_reasoning_model(model):
        payload["max_completion_tokens"] = max_tokens
    else:
        payload["max_tokens"] = max_tokens
        payload["temperature"] = 0.0

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    started = time.time()
    data = _http_post_json(_GITHUB_MODELS_ENDPOINT, payload, headers, timeout=timeout)
    elapsed = int((time.time() - started) * 1000)

    choices = data.get("choices") or []
    if not choices:
        raise LLMError(f"No choices in vision response: {str(data)[:300]}")
    text = (choices[0].get("message") or {}).get("content") or ""
    return {"text": text, "model": data.get("model", model), "duration_ms": elapsed}


def call_llm_vision(
    *,
    model: str,
    system: str,
    user: str,
    images: list[str],
    max_tokens: int = 512,
    timeout: int = 60,
) -> dict:
    """Multimodal sibling of call_llm. Returns same shape: text/model/duration_ms.

    Backend resolution:
      - mock   → returns a deterministic stub (`{"has_error": false, ...}`)
                 so tests don't make network calls.
      - everything else → forces copilot_direct path (the VS Code bridge
                 currently does not expose vision; routing directly to
                 GitHub Models is the documented opt-in fallback).

    Raises LLMError if the call fails. Callers MUST be prepared to swallow
    the error and degrade gracefully (e.g. fall back to DOM-only detection).
    """
    backend = os.environ.get("STACKY_LLM_BACKEND", "vscode_bridge").lower()

    if backend == "mock":
        return {
            "text": '{"has_error": false, "error_text": "", "category": "none", "confidence": "low"}',
            "model": "mock-vision-1.0",
            "duration_ms": 5,
        }

    # vscode_bridge does not pipe images today — we always go direct for vision.
    return _invoke_copilot_direct_vision(
        system=system,
        user=user,
        model=model,
        images=list(images or []),
        max_tokens=max_tokens,
        timeout=timeout,
    )
