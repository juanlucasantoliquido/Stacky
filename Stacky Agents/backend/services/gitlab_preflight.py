"""gitlab_preflight.py — Plan 93 F2. Adapter GitLabPreflightProvider.

Implementa CIPreflightProvider (services/ci_preflight.py) delegando al cliente
REST de GitLabTrackerProvider (mismo patrón que gitlab_ci_provider.py:28-30).
"""
from __future__ import annotations

import re

_MAX_RUNNER_DETAILS = 20  # [C12] cap explícito — el click no cuelga
_DETAIL_SANITIZE_LEN = 500  # [C13] truncar detail de excepciones

# [C13] defensa en profundidad: por contrato los tokens SIEMPRE van en headers
# HTTP, nunca en el cuerpo del mensaje de excepción — pero si algo externo
# (proxy, log de librería) los concatena al texto, esto los redacta igual.
_SENSITIVE_RE = re.compile(
    r"(PRIVATE-TOKEN['\"]?\s*[:=]\s*['\"]?)([\w-]+)"
    r"|(Authorization['\"]?\s*[:=]\s*['\"]?)([\w. -]+)",
    re.IGNORECASE,
)


def _sanitized_detail(exc: Exception) -> str:
    """[C13] nunca incluye headers/PAT; trunca a 500 chars."""
    text = _SENSITIVE_RE.sub(lambda m: (m.group(1) or m.group(3) or "") + "***REDACTED***", str(exc))
    return text[:_DETAIL_SANITIZE_LEN]


class GitLabPreflightProvider:
    """CIPreflightProvider para GitLab CI. Delega a GitLabTrackerProvider."""

    name = "gitlab"

    def __init__(self, project: str | None = None) -> None:
        from services.gitlab_provider import GitLabTrackerProvider  # noqa: PLC0415

        self._project = project
        delegate = GitLabTrackerProvider(project=project)
        self._client = delegate._client

    def lint_yaml(self, yaml_str: str) -> dict:
        """POST /projects/:id/ci/lint con {"content": yaml_str}."""
        try:
            proj_path = self._client._project_path()
            body, _headers = self._client._request(
                "POST", f"/projects/{proj_path}/ci/lint", json_body={"content": yaml_str}
            )
            if body.get("valid"):
                return {
                    "status": "ok",
                    "errors": [],
                    "detail": "YAML válido para GitLab CI",
                }
            return {
                "status": "fail",
                "errors": list(body.get("errors") or []),
                "detail": "; ".join(str(e) for e in (body.get("errors") or [])),
            }
        except Exception as exc:  # nunca 500 — degrada a unavailable
            return {"status": "unavailable", "errors": [], "detail": _sanitized_detail(exc)}

    def list_runners(self) -> dict:
        """GET /projects/:id/runners — [C2] la LISTA no trae tag_list; hidratar
        por GET /runners/:id (máximo 20, solo runners online)."""
        try:
            proj_path = self._client._project_path()
            list_body, _headers = self._client._request(
                "GET", f"/projects/{proj_path}/runners"
            )
        except Exception as exc:
            detail = _sanitized_detail(exc)
            if "403" in detail:
                detail = "PAT sin scope para listar runners"
            return {"status": "unavailable", "runners": [], "detail": detail}

        runners: list[dict] = []
        detail_calls = 0
        for raw in list_body or []:
            runner_id = raw.get("id")
            is_online = bool(raw.get("online")) or raw.get("status") == "online"

            tags: list | None = None
            if is_online and detail_calls < _MAX_RUNNER_DETAILS:
                detail_calls += 1
                try:
                    detail_body, _h = self._client._request("GET", f"/runners/{runner_id}")
                    tags = list(detail_body.get("tag_list") or [])
                except Exception:
                    tags = None  # [C2] detalle caído -> tags desconocidas, nunca falso rojo

            runners.append({"id": runner_id, "online": is_online, "tags": tags})

        return {"status": "ok", "runners": runners, "detail": ""}
