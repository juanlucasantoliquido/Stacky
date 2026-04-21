"""semantic_anchor_injector.py — Q-01: Inyecta fragmentos reales de código como anclas semánticas en prompts."""

import logging
from pathlib import Path

logger = logging.getLogger("stacky.semantic_anchor_injector")

_LANG_BY_EXT = {
    ".cs":   "csharp",
    ".sql":  "sql",
    ".py":   "python",
    ".ts":   "typescript",
    ".tsx":  "typescript",
    ".js":   "javascript",
    ".jsx":  "javascript",
}


def _detect_language(rel_path: str) -> str:
    ext = Path(rel_path).suffix.lower()
    return _LANG_BY_EXT.get(ext, "text")


class SemanticAnchorInjector:
    MAX_CHARS_PER_FILE = 3000
    MAX_FILES = 5

    def build_anchors(self, file_list: list[str], workspace_root: str) -> str:
        if not file_list:
            return ""

        blocks = []
        for rel_path in file_list[:self.MAX_FILES]:
            full_path = Path(workspace_root) / rel_path
            try:
                if not full_path.exists():
                    logger.debug("Anchor skip: %s no existe", rel_path)
                    continue
                content = full_path.read_text(encoding="utf-8", errors="ignore")
            except Exception as e:
                logger.warning("Anchor skip: no pude leer %s: %s", rel_path, e)
                continue

            snippet = content[:self.MAX_CHARS_PER_FILE]
            lang    = _detect_language(rel_path)
            blocks.append(
                f"### Código actual: `{rel_path}`\n```{lang}\n{snippet}\n```"
            )

        return "\n\n".join(blocks)
