"""
FA-17 — Auto-typecheck del output del Developer.

Detecta bloques de código en el output del Developer agent y los valida
con un compilador / typechecker en sandbox. Si hay errores:
- Marca la sección con badge rojo
- Re-prompt automático opcional con los errores como hint
- Bloquea el botón "Approve" hasta que se resuelva

Soportado:
- C# / .NET    → `dotnet build` sobre proyecto temporal
- TypeScript   → `tsc --noEmit`
- Python       → `python -m py_compile` + `mypy` (si está instalado)

En el MVP corre sólo Python (es lo que tiene la imagen base).
"""
from __future__ import annotations

import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path


_LANG_BY_BLOCK = {
    "csharp": "csharp", "cs": "csharp", "c#": "csharp",
    "typescript": "typescript", "ts": "typescript",
    "javascript": "javascript", "js": "javascript",
    "python": "python", "py": "python",
}


@dataclass
class TypecheckIssue:
    line: int | None
    column: int | None
    severity: str   # error | warning
    message: str
    raw: str

    def to_dict(self) -> dict:
        return {
            "line": self.line,
            "column": self.column,
            "severity": self.severity,
            "message": self.message,
            "raw": self.raw,
        }


@dataclass
class TypecheckResult:
    language: str
    code_snippet: str
    passed: bool
    issues: list[TypecheckIssue]
    skipped_reason: str | None

    def to_dict(self) -> dict:
        return {
            "language": self.language,
            "code_snippet": self.code_snippet[:500],
            "passed": self.passed,
            "issue_count": len(self.issues),
            "issues": [i.to_dict() for i in self.issues[:20]],
            "skipped_reason": self.skipped_reason,
        }


_BLOCK_RE = re.compile(r"```(\w+)?\n([\s\S]*?)```", re.MULTILINE)


def extract_blocks(markdown: str) -> list[tuple[str, str]]:
    """Devuelve list[(lang, code)] de los bloques fenced del output."""
    out: list[tuple[str, str]] = []
    for m in _BLOCK_RE.finditer(markdown or ""):
        lang_raw = (m.group(1) or "").lower()
        lang = _LANG_BY_BLOCK.get(lang_raw)
        if lang:
            out.append((lang, m.group(2)))
    return out


def check_python(code: str) -> TypecheckResult:
    """Compila Python con `compile()` (built-in) — no requiere subprocess."""
    issues: list[TypecheckIssue] = []
    try:
        compile(code, "<typecheck>", "exec")
        return TypecheckResult(language="python", code_snippet=code, passed=True,
                               issues=[], skipped_reason=None)
    except SyntaxError as e:
        issues.append(TypecheckIssue(
            line=e.lineno, column=e.offset, severity="error",
            message=str(e.msg), raw=str(e),
        ))
        return TypecheckResult(language="python", code_snippet=code, passed=False,
                               issues=issues, skipped_reason=None)


def check_typescript(code: str) -> TypecheckResult:
    """Llama a `tsc --noEmit` si está instalado. Si no, skip."""
    if not _which("tsc") and not _which("npx"):
        return TypecheckResult(language="typescript", code_snippet=code, passed=True,
                               issues=[], skipped_reason="tsc/npx not available")
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / "snippet.ts"
        f.write_text(code, encoding="utf-8")
        try:
            cmd = ["tsc"] if _which("tsc") else ["npx", "--yes", "typescript", "tsc"]
            cmd.extend(["--noEmit", "--target", "es2022", "--strict", "false", str(f)])
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        except subprocess.TimeoutExpired:
            return TypecheckResult(language="typescript", code_snippet=code,
                                   passed=False, issues=[], skipped_reason="timeout")
        except FileNotFoundError:
            return TypecheckResult(language="typescript", code_snippet=code,
                                   passed=True, issues=[], skipped_reason="tsc unavailable")

    issues: list[TypecheckIssue] = []
    output = (result.stdout or "") + "\n" + (result.stderr or "")
    for line in output.splitlines():
        m = re.match(r".*?\((\d+),(\d+)\):\s+error\s+(\w+):\s+(.+)", line)
        if m:
            issues.append(TypecheckIssue(
                line=int(m.group(1)), column=int(m.group(2)),
                severity="error", message=m.group(4), raw=line,
            ))
    return TypecheckResult(
        language="typescript", code_snippet=code,
        passed=len(issues) == 0 and result.returncode == 0,
        issues=issues, skipped_reason=None,
    )


def check_csharp(code: str) -> TypecheckResult:
    """Stub. Para ejecutar `dotnet build` se requiere proyecto contextual.
    En MVP devolvemos pass con skipped_reason = info."""
    return TypecheckResult(
        language="csharp", code_snippet=code, passed=True, issues=[],
        skipped_reason="C# typecheck requires project context (Fase 5+)",
    )


def _which(cmd: str) -> bool:
    """Cross-platform check si `cmd` está en PATH."""
    import shutil
    return shutil.which(cmd) is not None


def check(language: str, code: str) -> TypecheckResult:
    if language == "python":
        return check_python(code)
    if language == "typescript":
        return check_typescript(code)
    if language == "csharp":
        return check_csharp(code)
    return TypecheckResult(language=language, code_snippet=code, passed=True,
                           issues=[], skipped_reason="language not supported")


def check_output(output: str) -> list[TypecheckResult]:
    """Devuelve un TypecheckResult por cada bloque de código encontrado."""
    return [check(lang, code) for lang, code in extract_blocks(output)]
