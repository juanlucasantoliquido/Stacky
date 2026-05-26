"""Write QA UAT artifacts using the Stacky centralized ADO publish contract.

The QA UAT tool must not publish to ADO directly. It leaves:

    Agentes/outputs/<ADO_ID>/comment.html
    Agentes/outputs/<ADO_ID>/attachments.json
    Agentes/outputs/<ADO_ID>/attachments/<screenshots>

Stacky Agents backend owns upload/link/comment publication.
"""
from __future__ import annotations

import json
import logging
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger("stacky.qa_uat.stacky_handoff")

_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}


def export_stacky_handoff(
    *,
    ticket_id: int,
    dossier_path: Path,
    html_path: Path | None = None,
    source: str = "qa_uat_pipeline",
) -> dict[str, Any]:
    """Copy the generated ADO comment and screenshot artifacts to Stacky outputs."""
    started = datetime.utcnow()
    dossier_path = Path(dossier_path)
    html_path = Path(html_path) if html_path else dossier_path.parent / "ado_comment.html"

    if not dossier_path.is_file():
        return _err("missing_dossier", f"dossier.json not found: {dossier_path}")
    if not html_path.is_file():
        return _err("missing_html", f"ado_comment.html not found: {html_path}")

    try:
        dossier = json.loads(dossier_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return _err("invalid_dossier", f"Cannot read dossier.json: {exc}")

    repo = _repo_root()
    out_dir = repo / "Agentes" / "outputs" / str(ticket_id)
    attachments_dir = out_dir / "attachments"
    out_dir.mkdir(parents=True, exist_ok=True)
    attachments_dir.mkdir(parents=True, exist_ok=True)

    html_content = html_path.read_text(encoding="utf-8", errors="replace")
    (out_dir / "comment.html").write_text(html_content, encoding="utf-8")

    attachments = _copy_declared_screenshots(
        ticket_id=ticket_id,
        dossier=dossier,
        dossier_dir=dossier_path.parent,
        out_dir=out_dir,
        attachments_dir=attachments_dir,
        repo_root=repo,
    )

    manifest_path = out_dir / "attachments.json"
    if attachments:
        manifest_path.write_text(
            json.dumps(
                {
                    "schema_version": "stacky.agent_attachments.v1",
                    "source": source,
                    "ticket_id": ticket_id,
                    "dossier_path": str(dossier_path),
                    "attachments": attachments,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    else:
        manifest_path.unlink(missing_ok=True)

    (out_dir / "comment.meta.json").write_text(
        json.dumps(
            {
                "schema_version": "stacky.comment.meta.v1",
                "source": source,
                "agent_type": "qa-uat",
                "ado_id": ticket_id,
                "dossier_path": str(dossier_path),
                "generated_at": started.isoformat() + "Z",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    html_output_path = str((out_dir / "comment.html").relative_to(repo)).replace("\\", "/")
    return {
        "ok": True,
        "publish_state": "stacky_handoff_ready",
        "ticket_id": ticket_id,
        "html_output_path": html_output_path,
        "output_dir": str(out_dir),
        "attachments_count": len(attachments),
        "message": "QA UAT artifacts written for Stacky centralized ADO publish.",
    }


def _copy_declared_screenshots(
    *,
    ticket_id: int,
    dossier: dict[str, Any],
    dossier_dir: Path,
    out_dir: Path,
    attachments_dir: Path,
    repo_root: Path,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen_tokens: set[str] = set()

    for scenario in dossier.get("scenarios") or []:
        sid = str(scenario.get("scenario_id") or "scenario")
        for index, step in enumerate(scenario.get("steps") or [], start=1):
            token = str(step.get("attachment_token") or "").strip()
            if not token or token in seen_tokens:
                continue
            source_path = _resolve_image_path(
                step.get("screenshot_path") or step.get("screenshot"),
                dossier_dir=dossier_dir,
                repo_root=repo_root,
            )
            if source_path is None:
                logger.warning("stacky_handoff: screenshot missing for token %s", token)
                continue

            seen_tokens.add(token)
            suffix = source_path.suffix.lower() or ".png"
            safe_sid = _safe_file_part(sid)
            safe_name = _safe_file_part(step.get("screenshot_name") or source_path.stem)
            dest_name = f"qa-uat-{ticket_id}-{safe_sid}-{index:02d}-{safe_name}{suffix}"
            dest_path = attachments_dir / dest_name
            if source_path.resolve() != dest_path.resolve():
                shutil.copy2(source_path, dest_path)

            rows.append(
                {
                    "token": _normalize_token(token),
                    "path": str(dest_path.relative_to(out_dir)).replace("\\", "/"),
                    "upload_name": f"ADO-{ticket_id}_{dest_name}",
                    "comment": f"QA UAT {sid}: {step.get('description') or step.get('screenshot_name') or dest_name}",
                }
            )

    return rows


def _resolve_image_path(raw: Any, *, dossier_dir: Path, repo_root: Path) -> Path | None:
    if not raw:
        return None
    candidate = Path(str(raw))
    candidates = [candidate]
    if not candidate.is_absolute():
        candidates.extend([dossier_dir / candidate, Path.cwd() / candidate, repo_root / candidate])

    root = repo_root.resolve()
    for path in candidates:
        try:
            resolved = path.resolve()
        except OSError:
            continue
        if resolved.suffix.lower() not in _IMAGE_EXTS or not resolved.is_file():
            continue
        try:
            resolved.relative_to(root)
        except ValueError:
            logger.warning("stacky_handoff: screenshot outside repo ignored: %s", resolved)
            return None
        return resolved
    return None


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    for ancestor in here.parents:
        if (ancestor / "Agentes").is_dir() and (ancestor / "Tools").is_dir():
            return ancestor
    return here.parents[4]


def _normalize_token(token: str) -> str:
    token = token.strip()
    if token.startswith("{{ATTACH:") and token.endswith("}}"):
        return token
    if token.startswith("ATTACH:"):
        return "{{" + token + "}}"
    return token


def _safe_file_part(value: Any) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value or "")).strip("._-")
    return cleaned[:80] or "item"


def _err(code: str, message: str) -> dict[str, Any]:
    return {"ok": False, "error": code, "message": message}
