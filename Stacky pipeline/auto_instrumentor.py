"""
auto_instrumentor.py — Auto-Instrumentation of Production Code.

Detecta métodos nuevos/modificados en archivos .cs y genera sugerencias de
logging estructurado para inyectar en esos puntos.

Uso:
    from auto_instrumentor import AutoInstrumentor
    instrumentor = AutoInstrumentor()
    suggestions = instrumentor.analyze_dev_changes(dev_content, workspace_root)
"""

import re
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger("stacky.auto_instrumentor")


@dataclass
class InstrumentationSuggestion:
    file: str
    method: str
    suggested_log: str
    priority: str  # "high" (public) or "low" (private)
    line_hint: int = 0


class AutoInstrumentor:
    # Patterns to detect C# method declarations
    METHOD_PATTERN = re.compile(
        r"^\s*(public|private|protected|internal)?\s*"
        r"(static\s+)?(async\s+)?"
        r"(\w[\w<>,\s]*?)\s+"
        r"(\w+)\s*\(",
        re.MULTILINE
    )

    LOGGING_PATTERNS = [
        r"log\.", r"logger\.", r"Log\.", r"Logger\.",
        r"_log\.", r"_logger\.",
        r"Console\.Write", r"Debug\.Write",
        r"Trace\.", r"EventLog\.",
    ]

    def analyze_dev_changes(
        self,
        dev_completado_content: str,
        workspace_root: str,
    ) -> list[InstrumentationSuggestion]:
        modified_files = self._extract_modified_cs_files(dev_completado_content)
        suggestions = []

        for rel_path in modified_files:
            full_path = Path(workspace_root) / rel_path
            if not full_path.exists():
                continue
            try:
                content = full_path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue

            methods = self._detect_methods(content)
            for method in methods:
                if not self._has_logging(method["body"]):
                    suggestions.append(InstrumentationSuggestion(
                        file=rel_path,
                        method=method["name"],
                        suggested_log=self._generate_log_statement(method),
                        priority="high" if method["is_public"] else "low",
                        line_hint=method.get("line", 0),
                    ))

        logger.info("[Instrumentor] Found %d instrumentation suggestions across %d files",
                     len(suggestions), len(modified_files))
        return suggestions

    def build_suggestion_block(self, suggestions: list[InstrumentationSuggestion]) -> str:
        if not suggestions:
            return ""
        high = [s for s in suggestions if s.priority == "high"]
        if not high:
            return ""

        lines = [
            "### 📊 Sugerencias de logging (Auto-Instrumentor)",
            "",
            "Los siguientes métodos públicos no tienen logging. "
            "Considerar agregar para mejorar observabilidad:",
            "",
        ]
        for s in high[:5]:
            lines.append(f"- `{s.file}` → `{s.method}()`: `{s.suggested_log}`")
        return "\n".join(lines)

    def _extract_modified_cs_files(self, content: str) -> list[str]:
        pattern = re.compile(r"\b([\w/\\]+\.cs)\b", re.IGNORECASE)
        return list(set(pattern.findall(content)))

    def _detect_methods(self, cs_content: str) -> list[dict]:
        methods = []
        for i, match in enumerate(self.METHOD_PATTERN.finditer(cs_content)):
            access = match.group(1) or "private"
            return_type = match.group(4).strip()
            name = match.group(5).strip()
            start = match.start()
            line = cs_content[:start].count("\n") + 1

            # Extract approximate method body (next 50 lines)
            body_start = cs_content.find("{", match.end())
            if body_start == -1:
                continue
            body_end = min(body_start + 2000, len(cs_content))
            body = cs_content[body_start:body_end]

            methods.append({
                "name": name,
                "return_type": return_type,
                "is_public": access in ("public", "internal"),
                "body": body,
                "line": line,
            })
        return methods

    def _has_logging(self, body: str) -> bool:
        return any(re.search(p, body, re.IGNORECASE) for p in self.LOGGING_PATTERNS)

    def _generate_log_statement(self, method: dict) -> str:
        name = method["name"]
        return f'_logger.LogInformation("Ejecutando {name}");'
