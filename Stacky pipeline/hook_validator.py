"""
hook_validator.py — X-01: Validador para hooks Git del pipeline CI/CD.

Provee la logica de validacion que los hooks Git (pre-commit, post-commit)
llaman via HTTP al endpoint del dashboard Stacky.

Flujo:
  post-commit → llama /api/v1/hooks/post-commit
    - Registra el commit en el historial de Stacky
    - Verifica que los archivos modificados correspondan a un ticket QA-aprobado
    - Notifica al equipo del nuevo commit

  pre-commit → llama /api/v1/hooks/pre-commit
    - Puede bloquear commits sobre archivos con blast radius critico sin ticket aprobado
    - Configurable por proyecto (puede estar desactivado)

Los scripts de hook reales estan en svn_hooks/post-commit y svn_hooks/pre-commit.
Se instalan copiandolos al directorio .git/hooks/ del repo.

Uso:
    from hook_validator import HookValidator
    hv = HookValidator(project_name)
    result = hv.validate_post_commit(revision, author, files_changed)
    result = hv.validate_pre_commit(author, files_to_commit)
"""

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger("stacky.hook_validator")

BASE_DIR = Path(__file__).parent


class HookValidator:
    """
    Valida commits Git contra el pipeline Stacky.
    """

    def __init__(self, project_name: str):
        self.project_name = project_name
        self._config      = self._load_config()
        self._pre_commit_blocking = self._config.get(
            "svn_hooks", {}
        ).get("pre_commit_blocking", False)
        self._commit_log_path = (
            BASE_DIR / "projects" / project_name / "commit_history.json"
        )
        self._tickets_base = BASE_DIR / "projects" / project_name / "tickets"

    # ── API publica ──────────────────────────────────────────────────────────

    def validate_post_commit(
        self, revision: str, author: str, files_changed: list, commit_message: str = ""
    ) -> dict:
        """
        Procesa un post-commit:
        1. Busca si los archivos pertenecen a algun ticket QA-aprobado
        2. Registra el commit en el historial
        3. Retorna resultado con tickets relacionados encontrados
        """
        result = {
            "revision":       revision,
            "author":         author,
            "files_changed":  files_changed,
            "commit_message": commit_message,
            "timestamp":      datetime.now().isoformat(),
            "tickets_found":  [],
            "untracked_files": [],
        }

        # Buscar tickets que tocaron los mismos archivos
        qa_tickets = self._get_qa_approved_tickets()
        matched_tickets = set()

        for fpath in files_changed:
            fname = Path(fpath).name
            for ticket_id, ticket_data in qa_tickets.items():
                if fname in [Path(f).name for f in ticket_data.get("files_touched", [])]:
                    matched_tickets.add(ticket_id)

        result["tickets_found"] = list(matched_tickets)

        if not matched_tickets:
            result["untracked_files"] = files_changed[:5]
            result["warning"] = (
                "Los archivos modificados no corresponden a ningun ticket "
                "procesado por Stacky con QA aprobado."
            )
        else:
            result["message"] = (
                f"Commit validado. Tickets relacionados: {', '.join(matched_tickets)}"
            )

        # Registrar en historial
        self._record_commit(result)

        # Notificar al equipo
        self._send_commit_notification(result)

        logger.info(
            "[X-01] post-commit r%s por %s — tickets: %s",
            revision, author, matched_tickets or "ninguno",
        )

        return result

    def validate_pre_commit(self, author: str, files_to_commit: list) -> dict:
        """
        Valida antes del commit. Si pre_commit_blocking=True,
        puede rechazar commits sobre archivos de alto blast radius sin ticket aprobado.
        Retorna: {"allowed": True/False, "reason": str}
        """
        if not self._pre_commit_blocking:
            return {"allowed": True, "reason": "pre-commit validation disabled"}

        # Verificar blast radius critico sin ticket activo
        high_risk = self._get_high_blast_radius_files()
        blocked_files = []

        for fpath in files_to_commit:
            fname = Path(fpath).name
            if fname in high_risk:
                # Verificar si hay un ticket Stacky activo que cubra este archivo
                has_active_ticket = self._has_active_ticket_for_file(fpath)
                if not has_active_ticket:
                    blocked_files.append(fname)

        if blocked_files:
            return {
                "allowed": False,
                "reason": (
                    f"Los siguientes archivos tienen blast radius critico y no tienen "
                    f"ticket Stacky activo: {', '.join(blocked_files)}. "
                    f"Procesar el ticket en Stacky antes de commitear."
                ),
                "blocked_files": blocked_files,
            }

        return {"allowed": True, "reason": "pre-commit validation passed"}

    def get_commit_history(self, limit: int = 50) -> list:
        """Retorna el historial de commits registrados."""
        if not self._commit_log_path.exists():
            return []
        try:
            data = json.loads(self._commit_log_path.read_text(encoding="utf-8"))
            commits = data.get("commits", [])
            return commits[-limit:]
        except Exception:
            return []

    # ── Privados ─────────────────────────────────────────────────────────────

    def _get_qa_approved_tickets(self) -> dict:
        """Retorna tickets con QA aprobado y sus archivos modificados."""
        result = {}
        qa_dir  = self._tickets_base
        if not qa_dir.exists():
            return result

        # Buscar tickets completados con QA aprobado (tienen TESTER_COMPLETADO.md)
        for estado_dir in qa_dir.iterdir():
            if not estado_dir.is_dir():
                continue
            for ticket_folder in estado_dir.iterdir():
                if not ticket_folder.is_dir():
                    continue
                tester_file = ticket_folder / "TESTER_COMPLETADO.md"
                if tester_file.exists():
                    content = tester_file.read_text(encoding="utf-8", errors="ignore")
                    if "APROBADO" in content.upper():
                        files = self._extract_files_from_folder(ticket_folder)
                        result[ticket_folder.name] = {"files_touched": files}
        return result

    def _get_high_blast_radius_files(self) -> set:
        """Retorna set de archivos con blast radius critico del proyecto."""
        files = set()
        # Buscar BLAST_RADIUS.md en tickets activos
        for estado_dir in (self._tickets_base.iterdir() if self._tickets_base.exists() else []):
            for ticket_folder in (estado_dir.iterdir() if estado_dir.is_dir() else []):
                blast_file = ticket_folder / "BLAST_RADIUS.md"
                if blast_file.exists():
                    content = blast_file.read_text(encoding="utf-8", errors="ignore")
                    for line in content.splitlines():
                        if "CRITICO" in line.upper() or "HIGH" in line.upper():
                            match = re.search(r"[\w.\-]+\.(?:cs|aspx|vb)", line)
                            if match:
                                files.add(match.group(0))
        return files

    def _has_active_ticket_for_file(self, file_path: str) -> bool:
        """Verifica si hay un ticket Stacky activo que incluya este archivo."""
        fname = Path(file_path).name
        state_path = BASE_DIR / "pipeline" / "state.json"
        if not state_path.exists():
            return False
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
            for ticket_id, info in state.items():
                if "error" in info.get("stage", "") or "completado" in info.get("stage", ""):
                    continue
                relevant = info.get("relevant_files", [])
                if fname in [Path(f).name for f in relevant]:
                    return True
        except Exception:
            pass
        return False

    def _extract_files_from_folder(self, folder: Path) -> list:
        files = set()
        for fname in ("GIT_CHANGES.md", "DEV_COMPLETADO.md"):
            fpath = folder / fname
            if fpath.exists():
                content = fpath.read_text(encoding="utf-8", errors="ignore")
                for match in re.finditer(r"[\w.\-/\\]+\.(?:cs|aspx|vb|sql)", content):
                    files.add(Path(match.group(0)).name)
        return list(files)

    def _record_commit(self, commit_data: dict) -> None:
        """Registra el commit en el historial JSON."""
        data = {"commits": []}
        if self._commit_log_path.exists():
            try:
                data = json.loads(self._commit_log_path.read_text(encoding="utf-8"))
            except Exception:
                pass

        data["commits"].append(commit_data)
        # Mantener solo los ultimos 1000 commits
        data["commits"] = data["commits"][-1000:]

        self._commit_log_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def _send_commit_notification(self, commit_data: dict) -> None:
        try:
            from notifier import notify
            tickets_str = (
                ", ".join(commit_data["tickets_found"])
                if commit_data["tickets_found"]
                else "sin ticket Stacky"
            )
            notify(
                title=f"[Stacky] Commit Git r{commit_data['revision']}",
                message=(
                    f"Autor: {commit_data['author']} — "
                    f"Tickets: {tickets_str} — "
                    f"{len(commit_data['files_changed'])} archivos"
                ),
                level="info" if commit_data["tickets_found"] else "warning",
            )
        except Exception:
            pass

    def _load_config(self) -> dict:
        cfg = BASE_DIR / "projects" / self.project_name / "config.json"
        if cfg.exists():
            try:
                return json.loads(cfg.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}
