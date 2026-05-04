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
) -> dict:
    """
    Call LLM and return {"text": str, "model": str, "duration_ms": int}.

    Backend selection (env STACKY_LLM_BACKEND):
        "vscode_bridge"   — VS Code bridge (default; best when running in agent context)
        "copilot_direct"  — GitHub Models API directly via gh token
        "mock"            — deterministic stub for unit tests

    Raises LLMError if all backends fail.
    """
    backend = os.environ.get("STACKY_LLM_BACKEND", "vscode_bridge").lower()

    if backend == "mock":
        return _invoke_mock(system, user, model, max_tokens)

    if backend == "vscode_bridge":
        if _vscode_bridge_healthy():
            try:
                return _invoke_vscode_bridge(system, user, model, max_tokens, timeout)
            except LLMError as exc:
                logger.warning("VS Code bridge failed, falling back to copilot_direct: %s", exc)
        else:
            logger.info("VS Code bridge not available, using copilot_direct")
        try:
            return _invoke_copilot_direct(system, user, model, max_tokens, timeout)
        except LLMError:
            raise

    if backend == "copilot_direct":
        return _invoke_copilot_direct(system, user, model, max_tokens, timeout)

    raise LLMError(f"Unknown STACKY_LLM_BACKEND: {backend!r}. Use: vscode_bridge | copilot_direct | mock")
