"""
ado_attachment_manager.py — Adjuntar artefactos PM/DEV/QA al Work Item en ADO.

Los artefactos generados por Stacky se adjuntan directamente al Work Item
para que todo el historial del ticket quede en un solo lugar.

Uso:
    from ado_attachment_manager import ADOAttachmentManager
    mgr = ADOAttachmentManager()
    mgr.attach_stage_artifacts(27698, "pm_completado", ticket_folder)
"""

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger("stacky.ado_attachment")

# Files to attach per stage
STAGE_ATTACHMENTS = {
    "pm_completado": [
        "INCIDENTE.md",
        "ANALISIS_TECNICO.md",
        "ARQUITECTURA_SOLUCION.md",
        "TAREAS_DESARROLLO.md",
        "QUERIES_ANALISIS.sql",
        "NOTAS_IMPLEMENTACION.md",
    ],
    "dev_completado": [
        "DEV_COMPLETADO.md",
        "GIT_CHANGES.md",
        "TEST_RESULTS.md",
    ],
    "qa_completado": [
        "TESTER_COMPLETADO.md",
        "TEST_EXECUTION_REPORT.md",
    ],
}

# Max file size for attachment (5 MB)
MAX_ATTACHMENT_SIZE = 5 * 1024 * 1024


class ADOAttachmentManager:
    """Attaches pipeline stage artifacts to ADO Work Items."""

    def __init__(self, ado_client=None):
        self._ado_client = ado_client

    @property
    def ado_client(self):
        if self._ado_client is None:
            try:
                from ado_enricher import _get_ado_client
                self._ado_client = _get_ado_client()
            except Exception as e:
                logger.error("Cannot initialize ADO client: %s", e)
                raise
        return self._ado_client

    def attach_stage_artifacts(
        self,
        work_item_id: int,
        stage: str,
        ticket_folder: str,
    ) -> list[str]:
        """
        Attach all relevant artifacts for a pipeline stage to the ADO Work Item.

        Returns list of successfully attached file names.
        """
        files = STAGE_ATTACHMENTS.get(stage, [])
        if not files:
            logger.debug("No attachment config for stage '%s'", stage)
            return []

        attached = []
        folder = Path(ticket_folder)

        for fname in files:
            fpath = folder / fname
            if not fpath.exists():
                logger.debug("Artifact not found, skipping: %s", fpath)
                continue

            if fpath.stat().st_size > MAX_ATTACHMENT_SIZE:
                logger.warning("Artifact too large (%d bytes), skipping: %s",
                               fpath.stat().st_size, fname)
                continue

            if self._attach_file(work_item_id, fpath, stage):
                attached.append(fname)

        logger.info("Attached %d/%d artifacts for WI#%d stage=%s",
                     len(attached), len(files), work_item_id, stage)
        return attached

    def attach_custom_file(
        self,
        work_item_id: int,
        file_path: str,
        display_name: Optional[str] = None,
    ) -> bool:
        """Attach a single custom file to an ADO Work Item."""
        fpath = Path(file_path)
        if not fpath.exists():
            logger.error("File not found: %s", file_path)
            return False
        return self._attach_file(work_item_id, fpath, "custom", display_name)

    def _attach_file(
        self,
        work_item_id: int,
        file_path: Path,
        stage: str,
        display_name: Optional[str] = None,
    ) -> bool:
        """Upload file and link it to the Work Item."""
        fname = display_name or f"stacky_{stage}_{file_path.name}"

        try:
            content = file_path.read_bytes()

            # Upload attachment
            attachment_ref = self.ado_client.upload_attachment(
                content,
                filename=fname,
            )

            if not attachment_ref:
                logger.error("Upload returned no reference for %s", fname)
                return False

            # Link attachment to work item
            attachment_url = (
                attachment_ref.get("url")
                if isinstance(attachment_ref, dict)
                else str(attachment_ref)
            )

            self.ado_client.add_attachment_to_work_item(
                work_item_id, attachment_url, comment=f"Stacky {stage}: {file_path.name}"
            )

            logger.info("Attached '%s' to WI#%d", fname, work_item_id)
            return True

        except AttributeError as e:
            logger.warning("ADO client doesn't support attachment upload: %s", e)
            return self._attach_as_comment_fallback(work_item_id, file_path, stage)
        except Exception as e:
            logger.error("Failed to attach '%s' to WI#%d: %s", fname, work_item_id, e)
            return False

    def _attach_as_comment_fallback(
        self,
        work_item_id: int,
        file_path: Path,
        stage: str,
    ) -> bool:
        """
        Fallback: if the ADO client doesn't support attachments,
        post the file content as a comment instead.
        """
        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
            # Truncate if too long for a comment
            if len(content) > 8000:
                content = content[:8000] + "\n\n... (truncado, ver archivo completo en el filesystem)"

            comment = (
                f"## 📎 Artefacto: {file_path.name} (stage: {stage})\n\n"
                f"```markdown\n{content}\n```"
            )
            self.ado_client.add_comment(work_item_id, comment)
            logger.info("Fallback: posted '%s' as comment on WI#%d",
                         file_path.name, work_item_id)
            return True
        except Exception as e:
            logger.error("Fallback comment also failed for WI#%d: %s",
                         work_item_id, e)
            return False
