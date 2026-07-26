"""services/cicd_audit_core.py — Plan 248 F0. Contrato común de la auditoría.

PURO: sin red, sin LLM, sin config. Determinista => paridad trivial en los 3 runtimes.

C1 — el walk canónico del Plan 243 se IMPORTA con alias de este lado.
`services/cicd_semantic_rules.py` es superficie EXCLUSIVA del Plan 249 (246 §0.3): este
plan no le escribe ni un byte.
"""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field

import yaml

from services.cicd_semantic_rules import (
    MAX_YAML_BYTES,
    MODE_AUDIT,
    MODE_NL_STRICT,
    _MODES,
    _iter_steps as iter_steps,      # cicd_semantic_rules.py:105
    _StepCtx as StepCtx,            # cicd_semantic_rules.py:73-82
    _task_inputs,
)
from services.pipeline_lint import SEV_ERROR, SEV_INFO, SEV_WARNING

AUDIT_RULES_VERSION = "248.1"

__all__ = [
    "AUDIT_RULES_VERSION", "AuditFinding", "AuditReport", "RuleSpec",
    "MODE_AUDIT", "MODE_NL_STRICT", "SEV_ERROR", "SEV_WARNING", "SEV_INFO",
    "iter_steps", "StepCtx", "audit_rule", "audit_yaml", "evidence_fingerprint",
    "effective_pool", "finding", "is_dynamic", "job_key", "line_of",
    "pool_is_self_hosted", "AUDIT_RULES", "line_of_pair",
]


@dataclass(frozen=True)
class AuditFinding:
    code: str            # "SEC003" | "OPT002"
    severity: str        # SEV_ERROR | SEV_WARNING | SEV_INFO
    message: str         # es-AR, llano, dice POR QUE importa
    location: str        # "stages[1].jobs[0].steps[2]" — del walk, NUNCA vacio
    line: object         # int | None — 1-based sobre el YAML fuente; best-effort
    evidence: str        # el fragmento/valor exacto que la disparo
    remediation: str     # es-AR, imperativo, COMO se arregla. NUNCA vacio
    providers: tuple     # ("ado",) | ("ado", "gitlab")

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "location": self.location,
            "line": self.line,
            "evidence": self.evidence,
            "remediation": self.remediation,
            "providers": list(self.providers),
            "evidence_fingerprint": evidence_fingerprint(
                self.code, self.location, self.evidence),
        }


@dataclass(frozen=True)
class AuditReport:
    ok: bool
    findings: tuple
    counts: dict
    suppressed: tuple = ()
    undetermined: int = 0
    undetermined_notes: tuple = ()
    rules_version: str = AUDIT_RULES_VERSION
    mode: str = MODE_AUDIT
    duration_ms: float = 0.0

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "findings": [f.to_dict() for f in self.findings],
            "counts": dict(self.counts),
            "suppressed": [f.to_dict() for f in self.suppressed],
            "undetermined": self.undetermined,
            "undetermined_notes": list(self.undetermined_notes),
            "rules_version": self.rules_version,
            "mode": self.mode,
            "duration_ms": self.duration_ms,
        }


@dataclass(frozen=True)
class RuleSpec:
    code: str
    severity_audit: str
    severity_nl: object       # str | None (None = la regla no existe en ese modo)
    providers: tuple
    modes: tuple
    repro: tuple              # (provider, yaml_minimo) — OBLIGATORIO
    family: str = ""


AUDIT_RULES: dict = {}
_AUDIT_RULES = AUDIT_RULES   # alias interno del plan


def audit_rule(code: str, *, severity_audit: str, severity_nl: object,
               providers: tuple, modes: tuple, repro: object):
    """Registra una regla. `repro` es OBLIGATORIO: sin el, la regla podria quedar
    inerte (0 hits por bug y no por corpus limpio) y el panel mostraria verde falso.
    """
    if not repro or not isinstance(repro, tuple) or len(repro) != 2:
        raise ValueError(
            "la regla %r debe declarar repro=(provider, yaml_minimo): sin reproductor "
            "no hay forma de probar que dispara" % code
        )

    def deco(fn):
        AUDIT_RULES[code] = RuleSpec(
            code=code,
            severity_audit=severity_audit,
            severity_nl=severity_nl,
            providers=tuple(providers),
            modes=tuple(modes),
            repro=repro,
            family="seguridad" if code.startswith("SEC") else "optimizacion",
        )
        return fn

    return deco


# ── Helpers puros ─────────────────────────────────────────────────────────────

def line_of(lines: list, needle: str, occurrence: int = 1) -> object:
    """1-based de la `occurrence`-esima linea que contiene `needle`. None si no esta."""
    if not needle:
        return None
    visto = 0
    for idx, texto in enumerate(lines or []):
        if needle in texto:
            visto += 1
            if visto >= max(1, occurrence):
                return idx + 1
    return None


def line_of_pair(lines: list, needle_a: str, needle_b: str) -> object:
    """Primera linea que contiene AMBOS needles. None si no hay.

    Existe porque el corpus real documenta sus propias decisiones EN COMENTARIOS: buscar
    solo `"ubuntu-latest"` cae en `ci-dacpac.yml:12` (un comentario) en vez de en el
    `vmImage:` de `:38`. La evidencia ya se confirmo en el arbol; esto solo la ancla bien.
    """
    for idx, texto in enumerate(lines or []):
        if needle_a in texto and needle_b in texto:
            return idx + 1
    return None


def is_dynamic(value) -> bool:
    """`${{ }}` o `$( )` dentro de un string. No-strings -> False."""
    if not isinstance(value, str):
        return False
    return "${{" in value or "$(" in value


def effective_pool(ctx) -> dict:
    pool = getattr(ctx, "pool", None)
    return pool if isinstance(pool, dict) else {}


def pool_is_self_hosted(pool: dict) -> bool:
    """name presente, vmImage ausente y el nombre NO dinamico (dinamico => abstencion)."""
    if not isinstance(pool, dict):
        return False
    if pool.get("vmImage"):
        return False
    name = pool.get("name")
    if not isinstance(name, str) or not name.strip():
        return False
    return not is_dynamic(name)


def evidence_fingerprint(code: str, location: str, evidence: str) -> str:
    raw = "%s|%s|%s" % (code, location, evidence)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def finding(*, code: str, severity: str, message: str, location: str,
            line: object, evidence: str, remediation: str,
            providers: tuple = ("ado",)) -> AuditFinding:
    """Constructor con los invariantes de KPI-2 hechos IMPOSIBLES de violar."""
    assert location, "un hallazgo sin location es una opinion, no un hallazgo (%s)" % code
    assert remediation, "un hallazgo sin remediation no le sirve a nadie (%s)" % code
    return AuditFinding(
        code=code, severity=severity, message=message, location=location,
        line=line, evidence=evidence, remediation=remediation,
        providers=tuple(providers),
    )


# ── C2 — agrupacion por job. NUNCA hacer rsplit(".steps[") a mano. ────────────
def job_key(location: str) -> str:
    """Identidad del job/contenedor de un paso, para las reglas que razonan 'por job'.

    `_iter_steps` emite TRES formas de location (cicd_semantic_rules.py:119, :122, :126):
      "stages[1].jobs[0].steps[2]"        -> "stages[1].jobs[0]"
      "stages[1].deployments[0].steps[2]" -> "stages[1].deployments[0]"
      "steps[2]"   (pasos de RAIZ)        -> "(root)"     <-- el caso que rompia OPT002

    Un `location.rsplit(".steps[", 1)[0]` crudo devuelve "steps[2]" para el tercer caso,
    es decir UN GRUPO POR PASO, y toda regla 'mismo job' queda muda en los 5 golden de raiz.
    """
    marker = ".steps["
    if marker in location:
        return location.rsplit(marker, 1)[0]
    if location.startswith("steps["):
        return "(root)"
    return location


# ── F3 — orquestador ──────────────────────────────────────────────────────────

_PROFILE_DEFAULT = "dotnet_framework"


def _empty_counts() -> dict:
    return {SEV_ERROR: 0, SEV_WARNING: 0, SEV_INFO: 0}


def _counts_of(findings) -> dict:
    counts = _empty_counts()
    for f in findings:
        if f.severity in counts:
            counts[f.severity] += 1
    return counts


def _aud000(message: str, mode: str, started: float) -> AuditReport:
    f = finding(
        code="AUD000", severity=SEV_WARNING, message=message,
        location="(documento)", line=None, evidence=message,
        remediation="Revisá el YAML antes de auditarlo.", providers=("ado", "gitlab"),
    )
    return AuditReport(
        ok=True, findings=(f,), counts=_counts_of((f,)), mode=mode,
        duration_ms=(time.monotonic() - started) * 1000.0,
    )


def audit_yaml(yaml_text: str, *, provider: str, profile: str = _PROFILE_DEFAULT,
               mode: str = MODE_AUDIT, pipeline_key: object = None,
               suppressions: object = None) -> AuditReport:
    """SEC + OPT sobre un pipeline. Determinista, sin LLM, sin red."""
    started = time.monotonic()
    if mode not in _MODES:
        raise ValueError("mode %r invalido (validos: %s)" % (mode, ", ".join(_MODES)))
    if len(yaml_text or "") > MAX_YAML_BYTES:
        return _aud000("el YAML supera 512 KB: no se audita", mode, started)
    try:
        doc = yaml.safe_load(yaml_text)
    except yaml.YAMLError as exc:
        return _aud000(
            "el YAML no se pudo parsear: %s" % str(exc).splitlines()[0], mode, started)
    if not isinstance(doc, dict):
        return AuditReport(ok=True, findings=(), counts=_empty_counts(), mode=mode,
                           duration_ms=(time.monotonic() - started) * 1000.0)

    from services.cicd_security_rules import check_security  # noqa: PLC0415
    from services.pipeline_recommendations import check_recommendations  # noqa: PLC0415

    sec, notas_sec = check_security(yaml_text, provider=provider, profile=profile, mode=mode)
    opt, notas_opt = check_recommendations(yaml_text, provider=provider, mode=mode)

    todos = list(sec) + list(opt)
    todos.sort(key=lambda f: (f.line if isinstance(f.line, int) else 10**9, f.code, f.location))

    visibles, suprimidos = tuple(todos), ()
    if suppressions:
        from services.pipeline_audit_suppressions import apply_suppressions  # noqa: PLC0415
        visibles, suprimidos = apply_suppressions(
            tuple(todos), suppressions, pipeline_key=pipeline_key)

    notas = tuple(notas_sec) + tuple(notas_opt)
    counts = _counts_of(visibles)
    return AuditReport(
        ok=counts[SEV_ERROR] == 0,
        findings=tuple(visibles),
        counts=counts,
        suppressed=tuple(suprimidos),
        undetermined=len(notas),
        undetermined_notes=notas,
        rules_version=AUDIT_RULES_VERSION,
        mode=mode,
        duration_ms=(time.monotonic() - started) * 1000.0,
    )
