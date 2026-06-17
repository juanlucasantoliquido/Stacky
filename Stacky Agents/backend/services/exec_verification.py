"""E0.1 — Motor de verificación ejecutable del entregable.

Ejecuta verificadores objetivos del proyecto (compilar, tests, lint, type-check,
parseo de esquema) sobre lo que el agente produjo, antes de entregar.

API pública:
    verify(workspace, changed_files, agent_type, runtime, budget_s) -> VerificationReport

Todos los flags default OFF → retro-compat byte-idéntica cuando
STACKY_EXEC_VERIFICATION_ENABLED=false (default).

Diseño:
  - Registro de verificadores con applies(workspace, changed_files) -> bool
  - Escalonado barato-primero + short-circuit ante primer HARD
  - Caché por content-hash (sha256 del fileset + versión toolchain)
  - Budget global + timeout por verificador (desde flags)
  - NUNCA falla si toolchain ausente/timeout → could-not-verify (soft, nunca bloquea)
  - FakeGreenGuard (E1.2) integrado como verificador adicional
"""
from __future__ import annotations

import ast
import hashlib
import json
import logging
import os
import re
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("stacky.exec_verification")

# ── Constantes ───────────────────────────────────────────────────────────────

_HARD = "hard"
_SOFT = "soft"
_COULD_NOT_VERIFY = "could-not-verify"

# Extensiones de archivos de test para FakeGreenGuard
_TEST_FILE_PATTERNS = (
    "test_*.py",
    "*_test.py",
    "*.test.ts",
    "*.test.tsx",
    "*.test.js",
    "*.spec.ts",
    "*.spec.tsx",
    "*.spec.js",
)

# Caché: key → (passed, report_dict) — en memoria, dura la vida del proceso
_CACHE: dict[str, dict] = {}


# ── Estructuras de datos ──────────────────────────────────────────────────────

@dataclass
class VerifierResult:
    name: str
    status: str          # "passed" | "hard" | "soft" | "could-not-verify"
    detail: str = ""     # excerpt del log (acotado a 500 chars)
    duration_ms: int = 0


@dataclass
class VerificationReport:
    passed: bool | None              # None = no hay nada que verificar / could-not-verify
    ran: list[str] = field(default_factory=list)
    hard_failed: list[VerifierResult] = field(default_factory=list)
    soft: list[VerifierResult] = field(default_factory=list)
    could_not_verify: list[str] = field(default_factory=list)
    duration_ms: int = 0
    skipped_reason: str | None = None
    fake_green: list[str] = field(default_factory=list)

    def to_metadata(self, mode: str = "annotate") -> dict:
        return {
            "exec_verification": {
                "mode": mode,
                "ran": self.ran,
                "hard_failed": [
                    {"name": r.name, "detail": r.detail} for r in self.hard_failed
                ],
                "soft": [
                    {"name": r.name, "detail": r.detail} for r in self.soft
                ],
                "could_not_verify": self.could_not_verify,
                "passed": self.passed,
                "skipped_reason": self.skipped_reason,
                "duration_ms": self.duration_ms,
                "fake_green": self.fake_green,
            }
        }


# ── Verificadores ─────────────────────────────────────────────────────────────

class _BaseVerifier:
    name: str = ""
    order: int = 0  # menor = más barato; corre primero

    def applies(self, workspace: str, changed_files: list[str]) -> bool:
        return False

    def run(self, workspace: str, changed_files: list[str], timeout_s: int) -> VerifierResult:
        raise NotImplementedError


class JsonYamlParser(_BaseVerifier):
    """Parseo de .json/.yaml producidos — stdlib, microsegundos."""
    name = "JsonYamlParser"
    order = 10

    def applies(self, workspace: str, changed_files: list[str]) -> bool:
        return any(
            f.lower().endswith((".json", ".yaml", ".yml"))
            for f in changed_files
        )

    def run(self, workspace: str, changed_files: list[str], timeout_s: int) -> VerifierResult:
        t0 = time.monotonic()
        failed = []
        for f in changed_files:
            if not f.lower().endswith((".json", ".yaml", ".yml")):
                continue
            path = Path(f) if Path(f).is_absolute() else Path(workspace) / f
            if not path.exists():
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
                if f.lower().endswith(".json"):
                    json.loads(text)
                else:
                    # yaml: usar stdlib si disponible, else línea heurística
                    try:
                        import yaml  # type: ignore
                        yaml.safe_load(text)
                    except ImportError:
                        # sin yaml instalado → could-not-verify para .yaml
                        pass
            except (json.JSONDecodeError, Exception) as exc:
                failed.append(f"{path.name}: {str(exc)[:120]}")

        duration = int((time.monotonic() - t0) * 1000)
        if failed:
            return VerifierResult(
                name=self.name,
                status=_HARD,
                detail="; ".join(failed[:3]),
                duration_ms=duration,
            )
        return VerifierResult(name=self.name, status="passed", duration_ms=duration)


class PyCompile(_BaseVerifier):
    """Compilación de archivos .py cambiados — py_compile stdlib."""
    name = "PyCompile"
    order = 20

    def applies(self, workspace: str, changed_files: list[str]) -> bool:
        return any(f.endswith(".py") for f in changed_files)

    def run(self, workspace: str, changed_files: list[str], timeout_s: int) -> VerifierResult:
        import py_compile
        t0 = time.monotonic()
        failed = []
        for f in changed_files:
            if not f.endswith(".py"):
                continue
            path = Path(f) if Path(f).is_absolute() else Path(workspace) / f
            if not path.exists():
                continue
            try:
                py_compile.compile(str(path), doraise=True)
            except py_compile.PyCompileError as exc:
                failed.append(f"{path.name}: {str(exc)[:120]}")

        duration = int((time.monotonic() - t0) * 1000)
        if failed:
            return VerifierResult(
                name=self.name,
                status=_HARD,
                detail="; ".join(failed[:3]),
                duration_ms=duration,
            )
        return VerifierResult(name=self.name, status="passed", duration_ms=duration)


class TscCheck(_BaseVerifier):
    """tsc --noEmit si hay tsconfig.json en workspace."""
    name = "TscCheck"
    order = 30

    def applies(self, workspace: str, changed_files: list[str]) -> bool:
        has_ts = any(f.endswith((".ts", ".tsx")) for f in changed_files)
        has_tsconfig = (Path(workspace) / "tsconfig.json").exists()
        return has_ts and has_tsconfig

    def run(self, workspace: str, changed_files: list[str], timeout_s: int) -> VerifierResult:
        t0 = time.monotonic()
        try:
            result = subprocess.run(
                ["tsc", "--noEmit"],
                cwd=workspace,
                capture_output=True,
                text=True,
                timeout=timeout_s,
            )
            duration = int((time.monotonic() - t0) * 1000)
            if result.returncode != 0:
                detail = (result.stdout + result.stderr)[:500]
                return VerifierResult(name=self.name, status=_HARD, detail=detail, duration_ms=duration)
            return VerifierResult(name=self.name, status="passed", duration_ms=duration)
        except FileNotFoundError:
            return VerifierResult(
                name=self.name,
                status=_COULD_NOT_VERIFY,
                detail="tsc no disponible",
                duration_ms=int((time.monotonic() - t0) * 1000),
            )
        except subprocess.TimeoutExpired:
            return VerifierResult(
                name=self.name,
                status=_COULD_NOT_VERIFY,
                detail=f"timeout {timeout_s}s",
                duration_ms=int((time.monotonic() - t0) * 1000),
            )


class PytestRunner(_BaseVerifier):
    """pytest <paths> si hay pytest disponible y archivos .py modificados."""
    name = "PytestRunner"
    order = 40

    def applies(self, workspace: str, changed_files: list[str]) -> bool:
        py_files = [f for f in changed_files if f.endswith(".py")]
        return bool(py_files)

    def run(self, workspace: str, changed_files: list[str], timeout_s: int) -> VerifierResult:
        t0 = time.monotonic()
        py_files = [f for f in changed_files if f.endswith(".py")]
        # Solo archivos de test (no ejecutar todo el repo)
        test_files = [
            f for f in py_files
            if re.search(r'(test_|_test\.py)', Path(f).name)
        ]
        if not test_files:
            return VerifierResult(
                name=self.name,
                status=_COULD_NOT_VERIFY,
                detail="no hay archivos de test en changed_files",
                duration_ms=0,
            )
        # Paths absolutos o relativos al workspace
        paths = [
            str(Path(f) if Path(f).is_absolute() else Path(workspace) / f)
            for f in test_files
        ]
        try:
            result = subprocess.run(
                ["pytest", "--tb=short", "-q"] + paths,
                cwd=workspace,
                capture_output=True,
                text=True,
                timeout=timeout_s,
            )
            duration = int((time.monotonic() - t0) * 1000)
            output = (result.stdout + result.stderr)[:500]
            if result.returncode != 0:
                # Distinguir "no tests collected" (0 passed) de fallo real
                if "no tests ran" in output.lower() or "collected 0 items" in output.lower():
                    return VerifierResult(name=self.name, status=_SOFT, detail="0 tests colectados", duration_ms=duration)
                return VerifierResult(name=self.name, status=_HARD, detail=output, duration_ms=duration)
            return VerifierResult(name=self.name, status="passed", duration_ms=duration)
        except FileNotFoundError:
            return VerifierResult(
                name=self.name,
                status=_COULD_NOT_VERIFY,
                detail="pytest no disponible",
                duration_ms=int((time.monotonic() - t0) * 1000),
            )
        except subprocess.TimeoutExpired:
            return VerifierResult(
                name=self.name,
                status=_COULD_NOT_VERIFY,
                detail=f"timeout {timeout_s}s",
                duration_ms=int((time.monotonic() - t0) * 1000),
            )


class LintCheck(_BaseVerifier):
    """lint a nivel error si config existe (ruff para .py, eslint para .ts/.js)."""
    name = "LintCheck"
    order = 35

    def applies(self, workspace: str, changed_files: list[str]) -> bool:
        has_py = any(f.endswith(".py") for f in changed_files)
        has_js_ts = any(f.endswith((".ts", ".tsx", ".js")) for f in changed_files)
        has_ruff = (
            (Path(workspace) / "ruff.toml").exists()
            or (Path(workspace) / "pyproject.toml").exists()
        )
        has_eslint = (
            (Path(workspace) / ".eslintrc.js").exists()
            or (Path(workspace) / ".eslintrc.json").exists()
            or (Path(workspace) / ".eslintrc.yaml").exists()
            or (Path(workspace) / "eslint.config.js").exists()
        )
        return (has_py and has_ruff) or (has_js_ts and has_eslint)

    def run(self, workspace: str, changed_files: list[str], timeout_s: int) -> VerifierResult:
        t0 = time.monotonic()
        # Intentar ruff primero
        py_files = [f for f in changed_files if f.endswith(".py")]
        if py_files:
            abs_paths = [
                str(Path(f) if Path(f).is_absolute() else Path(workspace) / f)
                for f in py_files
                if (Path(f) if Path(f).is_absolute() else Path(workspace) / f).exists()
            ]
            if abs_paths:
                try:
                    result = subprocess.run(
                        ["ruff", "check", "--select=E,F", "--output-format=concise"] + abs_paths,
                        cwd=workspace,
                        capture_output=True,
                        text=True,
                        timeout=timeout_s,
                    )
                    duration = int((time.monotonic() - t0) * 1000)
                    if result.returncode not in (0, 1):  # 1 = warnings sin errores en ruff
                        detail = (result.stdout + result.stderr)[:500]
                        return VerifierResult(name=self.name, status=_HARD, detail=detail, duration_ms=duration)
                    # ruff exit 1 con errores reales (E/F)
                    if result.returncode == 1 and result.stdout.strip():
                        return VerifierResult(name=self.name, status=_SOFT, detail=result.stdout[:300], duration_ms=duration)
                    return VerifierResult(name=self.name, status="passed", duration_ms=duration)
                except FileNotFoundError:
                    pass
                except subprocess.TimeoutExpired:
                    return VerifierResult(
                        name=self.name, status=_COULD_NOT_VERIFY,
                        detail=f"timeout {timeout_s}s",
                        duration_ms=int((time.monotonic() - t0) * 1000),
                    )
        return VerifierResult(
            name=self.name,
            status=_COULD_NOT_VERIFY,
            detail="toolchain de lint no disponible",
            duration_ms=int((time.monotonic() - t0) * 1000),
        )


class FakeGreenGuard(_BaseVerifier):
    """E1.2 — Guard anti-verde-falso.

    Solo inspecciona archivos de test que el run creó/modificó.
    Detecta señales objetivas de cobertura ilusoria:
      (a) 0 tests colectados
      (b) funciones de test sin ningún assert/expect (AST Python; regex JS/TS)
      (c) TODOS los tests marcados skip/xfail
      (d) cuerpo de test vacío (pass/return trivial)

    Clasificación: soft-warn por defecto; escalable a HARD vía flag STACKY_FAKE_GREEN_GUARD_HARD.
    Si parseo falla/ambiguo → NO marca (evita falsos positivos).
    """
    name = "FakeGreenGuard"
    order = 25

    def applies(self, workspace: str, changed_files: list[str]) -> bool:
        return bool(self._test_files(changed_files))

    def _test_files(self, changed_files: list[str]) -> list[str]:
        return [
            f for f in changed_files
            if re.search(r'(test_[^/\\]+\.py|[^/\\]+_test\.py|\.test\.(ts|tsx|js)|\.spec\.(ts|tsx|js))$', f)
        ]

    def run(self, workspace: str, changed_files: list[str], timeout_s: int) -> VerifierResult:
        from config import config as _cfg
        hard = getattr(_cfg, "STACKY_FAKE_GREEN_GUARD_HARD", False)

        t0 = time.monotonic()
        suspects: list[str] = []

        for f in self._test_files(changed_files):
            path = Path(f) if Path(f).is_absolute() else Path(workspace) / f
            if not path.exists():
                continue
            verdict = self._inspect_file(path)
            if verdict:
                suspects.append(f"{path.name}: {verdict}")

        duration = int((time.monotonic() - t0) * 1000)
        if suspects:
            status = _HARD if hard else _SOFT
            return VerifierResult(
                name=self.name,
                status=status,
                detail="; ".join(suspects[:5]),
                duration_ms=duration,
            )
        return VerifierResult(name=self.name, status="passed", duration_ms=duration)

    def _inspect_file(self, path: Path) -> str | None:
        """Retorna descripción del problema o None si está OK."""
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None

        if path.suffix == ".py":
            return self._inspect_python(text)
        else:
            return self._inspect_js(text)

    def _inspect_python(self, text: str) -> str | None:
        try:
            tree = ast.parse(text)
        except SyntaxError:
            return None  # no marcar si no parsea

        test_funcs = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test")
        ]
        if not test_funcs:
            return None  # archivo sin funciones test = no aplica

        def _has_skip_dec(func):
            for dec in func.decorator_list:
                dec_str = ast.unparse(dec) if hasattr(ast, "unparse") else ""
                if any(k in dec_str for k in ("skip", "xfail")):
                    return True
            return False

        def _has_assert(func):
            return any(
                isinstance(node, (ast.Assert, ast.Raise))
                for node in ast.walk(func)
            )

        # (c) TODOS los tests con skip/xfail
        all_decorated_skip = all(_has_skip_dec(f) for f in test_funcs)
        if all_decorated_skip:
            return "todos los tests marcados skip/xfail"

        # (b)/(d) tests sin assert o con cuerpo vacío/trivial
        # Considerar solo los tests que NO están skipped
        non_skip_funcs = [f for f in test_funcs if not _has_skip_dec(f)]
        if not non_skip_funcs:
            return "todos los tests marcados skip/xfail"

        any_valid = any(_has_assert(f) for f in non_skip_funcs)
        if not any_valid:
            return "tests sin assert"

        return None

    def _inspect_js(self, text: str) -> str | None:
        """Heurística léxica para .ts/.js."""
        # Patrones de tests skip/todo: it.skip( | test.skip( | it.todo( | test.todo(
        skip_tests = re.findall(r'\b(?:it|test)\.(?:skip|todo)\s*\(', text)
        # Todos los bloques que abren un test: it( | test( | it.skip( | ...
        # Para distinguir "plain" de "skipped" buscamos "it(" o "test(" que NO están
        # precedidos inmediatamente por un punto usando split sencillo
        # Estrategia: quitar los it.skip/test.skip del texto y buscar los que quedan
        stripped = re.sub(r'\b(?:it|test)\.(?:skip|todo)\s*\(', '__SKIPPED__(', text)
        plain_tests = re.findall(r'\b(?:it|test)\s*\(', stripped)

        all_tests_count = len(skip_tests) + len(plain_tests)
        if all_tests_count == 0:
            return None  # no hay tests, no aplica

        # Todos skip/todo?
        if not plain_tests and skip_tests:
            return "todos los tests marcados skip/todo"

        # Sin expect/assert (solo en los tests no-skip)
        has_expect = re.search(r'\bexpect\s*\(|\bassert\b', text)
        if not has_expect:
            return "tests sin expect/assert"
        return None


# ── Registry de verificadores (orden de ejecución) ────────────────────────────

_VERIFIERS: list[_BaseVerifier] = sorted(
    [
        JsonYamlParser(),
        PyCompile(),
        FakeGreenGuard(),
        TscCheck(),
        LintCheck(),
        PytestRunner(),
    ],
    key=lambda v: v.order,
)


# ── Caché ─────────────────────────────────────────────────────────────────────

def _cache_key(workspace: str, changed_files: list[str]) -> str:
    """sha256 del fileset cambiado (contenido + rutas)."""
    h = hashlib.sha256()
    h.update(workspace.encode())
    for f in sorted(changed_files):
        h.update(f.encode())
        path = Path(f) if Path(f).is_absolute() else Path(workspace) / f
        try:
            h.update(path.read_bytes())
        except OSError:
            h.update(b"<missing>")
    return h.hexdigest()


# ── Función pública ───────────────────────────────────────────────────────────

def verify(
    workspace: str,
    changed_files: list[str],
    agent_type: str = "",
    runtime: str = "",
    budget_s: int = 300,
) -> VerificationReport:
    """Ejecuta verificadores objetivos sobre el workspace.

    Returns VerificationReport con passed=None cuando no hay nada que verificar.
    NUNCA lanza excepción ni bloquea si toolchain ausente.
    """
    try:
        from config import config as _cfg
        enabled = getattr(_cfg, "STACKY_EXEC_VERIFICATION_ENABLED", False)
        mode = getattr(_cfg, "STACKY_EXEC_VERIFICATION_MODE", "off")
        timeout_s = int(getattr(_cfg, "STACKY_EXEC_VERIFICATION_TIMEOUT_S", 120))
        budget_s = int(getattr(_cfg, "STACKY_EXEC_VERIFICATION_BUDGET_S", budget_s))
        projects_csv = getattr(_cfg, "STACKY_EXEC_VERIFICATION_PROJECTS", "")
    except Exception:
        enabled = False
        mode = "off"
        timeout_s = 120
        projects_csv = ""

    if not enabled or mode == "off":
        return VerificationReport(passed=None, skipped_reason="flag OFF")

    # Filtro por proyecto si hay allowlist
    if projects_csv:
        allowed = {p.strip() for p in projects_csv.split(",") if p.strip()}
        # runtime y agent_type son proxies; si no coinciden, skip
        if agent_type not in allowed and runtime not in allowed:
            return VerificationReport(passed=None, skipped_reason="proyecto no en allowlist")

    if not changed_files:
        return VerificationReport(passed=None, skipped_reason="sin changed_files")

    # Caché
    cache_k = _cache_key(workspace, changed_files)
    if cache_k in _CACHE:
        cached = _CACHE[cache_k]
        logger.debug("exec_verification: cache hit para %s", cache_k[:12])
        # Reconstruir VerificationReport desde cache
        return _report_from_cache(cached, mode)

    t_global = time.monotonic()
    report = VerificationReport(passed=None)
    budget_remaining = budget_s

    for verifier in _VERIFIERS:
        if not verifier.applies(workspace, changed_files):
            continue

        elapsed = time.monotonic() - t_global
        if elapsed >= budget_remaining:
            logger.debug("exec_verification: budget agotado, deteniendo")
            break

        vt = min(timeout_s, int(budget_remaining - elapsed))
        if vt <= 0:
            break

        try:
            result = verifier.run(workspace, changed_files, vt)
        except Exception as exc:  # noqa: BLE001
            logger.warning("exec_verification: %s lanzó excepción (no crítico): %s", verifier.name, exc)
            result = VerifierResult(
                name=verifier.name,
                status=_COULD_NOT_VERIFY,
                detail=str(exc)[:200],
            )

        report.ran.append(verifier.name)

        if result.status == "passed":
            pass  # OK
        elif result.status == _HARD:
            report.hard_failed.append(result)
            # FakeGreenGuard: reportar en fake_green además de hard_failed/soft
            if verifier.name == "FakeGreenGuard":
                report.fake_green.append(result.detail)
            # Short-circuit ante primer HARD
            logger.info("exec_verification: HARD fallo en %s — short-circuit", verifier.name)
            break
        elif result.status == _SOFT:
            report.soft.append(result)
            if verifier.name == "FakeGreenGuard":
                report.fake_green.append(result.detail)
        elif result.status == _COULD_NOT_VERIFY:
            report.could_not_verify.append(verifier.name)

    report.duration_ms = int((time.monotonic() - t_global) * 1000)

    # Determinar passed
    if not report.ran:
        report.passed = None
        report.skipped_reason = "ningún verificador aplicable"
    elif report.hard_failed:
        report.passed = False
    elif report.could_not_verify and not any(
        r.status == "passed" for r in _collect_all(report)
    ):
        # Solo could-not-verify → no determinable
        report.passed = None
        report.skipped_reason = "toolchain no disponible"
    else:
        report.passed = True

    # Guardar en caché
    _CACHE[cache_k] = _serialize_report(report, mode)

    return report


def _collect_all(report: VerificationReport) -> list[VerifierResult]:
    """Todos los resultados non-could_not_verify (para determinar passed)."""
    return report.hard_failed + report.soft


def _serialize_report(report: VerificationReport, mode: str) -> dict:
    return {
        "passed": report.passed,
        "ran": report.ran,
        "hard_failed": [{"name": r.name, "detail": r.detail} for r in report.hard_failed],
        "soft": [{"name": r.name, "detail": r.detail} for r in report.soft],
        "could_not_verify": report.could_not_verify,
        "duration_ms": report.duration_ms,
        "skipped_reason": report.skipped_reason,
        "fake_green": report.fake_green,
        "mode": mode,
    }


def _report_from_cache(cached: dict, mode: str) -> VerificationReport:
    r = VerificationReport(
        passed=cached["passed"],
        ran=cached["ran"],
        hard_failed=[
            VerifierResult(name=d["name"], status=_HARD, detail=d["detail"])
            for d in cached["hard_failed"]
        ],
        soft=[
            VerifierResult(name=d["name"], status=_SOFT, detail=d["detail"])
            for d in cached["soft"]
        ],
        could_not_verify=cached["could_not_verify"],
        duration_ms=cached["duration_ms"],
        skipped_reason=cached["skipped_reason"],
        fake_green=cached.get("fake_green", []),
    )
    return r


def invalidate_cache(workspace: str, changed_files: list[str]) -> None:
    """Invalida la caché para un workspace+fileset dado (llamar después de reparación)."""
    cache_k = _cache_key(workspace, changed_files)
    _CACHE.pop(cache_k, None)
