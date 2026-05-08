"""
ado_commit_linker.py — Link commits/PRs to ADO Work Items automatically.

Generates commit messages with AB#XXXXX format that ADO auto-links.

Uso:
    from ado_commit_linker import ADOCommitLinker
    linker = ADOCommitLinker()
    msg = linker.build_linked_commit_message(ticket_id, wi_id, files, summary)
"""

import logging
import re
import subprocess
from pathlib import Path
from typing import Optional

logger = logging.getLogger("stacky.commit_linker")


class ADOCommitLinker:
    def __init__(self, workspace_root: str = "", config: Optional[dict] = None):
        self.workspace_root = workspace_root
        self.config = config or {}

    def build_linked_commit_message(
        self,
        ticket_id: str,
        work_item_id: int,
        files_modified: list[str],
        summary: str,
    ) -> str:
        """
        Build a commit message that ADO automatically links to the work item.
        ADO recognizes 'AB#XXXXX' pattern.
        """
        files_section = "\n".join(f"- {f}" for f in files_modified[:20])
        return (
            f"{summary}\n\n"
            f"Changes:\n{files_section}\n\n"
            f"Resolves AB#{work_item_id}"
        )

    def auto_commit_and_link(
        self,
        ticket_folder: str,
        work_item_id: int,
        files_modified: list[str],
        summary: str = "",
    ) -> Optional[str]:
        """
        Create a git commit with ADO-linked message.
        Returns commit hash if successful.
        """
        if not summary:
            summary = f"fix: ticket #{work_item_id}"

        message = self.build_linked_commit_message(
            ticket_id=str(work_item_id),
            work_item_id=work_item_id,
            files_modified=files_modified,
            summary=summary,
        )

        cwd = self.workspace_root or str(Path(ticket_folder).parent.parent.parent)

        try:
            # Stage files
            for f in files_modified:
                subprocess.run(
                    ["git", "add", f],
                    cwd=cwd, capture_output=True, timeout=10
                )

            # Commit
            result = subprocess.run(
                ["git", "commit", "-m", message],
                cwd=cwd, capture_output=True, text=True, timeout=30
            )

            if result.returncode == 0:
                # Get commit hash
                hash_result = subprocess.run(
                    ["git", "rev-parse", "HEAD"],
                    cwd=cwd, capture_output=True, text=True, timeout=10
                )
                commit_hash = hash_result.stdout.strip()
                logger.info("[CommitLinker] Committed %s → AB#%d",
                             commit_hash[:8], work_item_id)
                return commit_hash
            else:
                logger.warning("[CommitLinker] Commit failed: %s", result.stderr[:200])
                return None

        except Exception as e:
            logger.error("[CommitLinker] Error: %s", e)
            return None

    def extract_modified_files_from_dev(self, ticket_folder: str) -> list[str]:
        """Extract file list from DEV_COMPLETADO.md."""
        dev_file = Path(ticket_folder) / "DEV_COMPLETADO.md"
        if not dev_file.exists():
            return []

        content = dev_file.read_text(encoding="utf-8", errors="replace")
        files = []
        for m in re.finditer(r"[-*]\s*([\w/\\]+\.\w{1,5})\b", content):
            files.append(m.group(1))
        return files
