"""
evidence_extractor — T7 Fase 2: extrae evidencia objetiva por regla del diff.

A diferencia de los linters T1/T9/T8 (que detectan violaciones), este módulo
recolecta TODOS los call-sites relevantes para cada regla, con su clasificación
inicial. El objetivo: el QA recibe un bundle estructurado y solo decide
PASS/FAIL sobre evidencia objetiva — no audita a ojo.

Output:

    {
      "R1":  [{file, line, snippet, status: PASS|FAIL|REVIEW}],
      "R2":  [...],
      "R3":  [...],
      "R4":  [...],
      "R10": [...],
      "multi_empresa": [...],   # queries que tocan tablas core con/sin filtro
      "ejecutar_query": [...]   # cada EjecutarQuery con su contexto
    }

Status:
  - `PASS`   : el sistema detectó cumplimiento.
  - `FAIL`   : el sistema detectó violación (mismos hallazgos que T1).
  - `REVIEW` : ambiguo / requiere ojo humano.

Uso:

    from linters.evidence_extractor import extract_evidence
    bundle = extract_evidence(diff_text)
    # JSON ready: bundle.to_dict()

Cuando el QA recibe el prompt, el sistema le inyecta este bundle como input
adicional. El prompt no le pide al LLM "buscá strings hardcodeados" — el
sistema ya los extrajo.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path

_HERE = Path(__file__).parent
if str(_HERE.parent) not in sys.path:
    sys.path.insert(0, str(_HERE.parent))

from linters.diff_parser import parse_diff, Hunk  # noqa: E402
from linters.lint_golden_rules import (  # noqa: E402
    _RE_NEW_CCONEXION,
    _RE_TRANSACTION_CALL,
    _RE_SQL_KEYWORD_IN_STRING,
    _RE_USER_VISIBLE_LITERAL,
    _RE_RIDIOMA_USAGE,
    _RE_EJECUTAR_QUERY,
    _RE_VERIFICACION_ERRORES,
    CS_EXTENSIONS,
    _is_facade,
    _is_bus_or_dalc,
    _is_batch_orchestrator,
    lint_diff,
)
from linters.findings import Severity  # noqa: E402


# ── Tablas core para detección multi-empresa ─────────────────────────────────

CORE_TABLES_WITH_EMPRESA = {
    "RCLIE": "CLEMPRESA",
    "ROBLG": "OGEMPRESA",
    "RDEUDA": "OGEMPRESA",   # vía join
    "RPAGOS": "OGEMPRESA",
    "RCUOTAS": "OGEMPRESA",
    "RCONVP": "OGEMPRESA",
    "RAGENDA": "CLEMPRESA",
}

_RE_TABLE_IN_FROM = re.compile(r"\bFROM\s+(\w+)\b", re.IGNORECASE)
_RE_TABLE_IN_UPDATE = re.compile(r"\bUPDATE\s+(\w+)\b", re.IGNORECASE)


@dataclass
class EvidenceItem:
    file: str
    line: int
    snippet: str
    status: str  # PASS | FAIL | REVIEW
    note: str = ""


@dataclass
class EvidenceBundle:
    by_rule: dict[str, list[EvidenceItem]] = field(default_factory=dict)

    def add(self, rule: str, item: EvidenceItem) -> None:
        self.by_rule.setdefault(rule, []).append(item)

    def to_dict(self) -> dict:
        return {
            rule: [asdict(item) for item in items]
            for rule, items in self.by_rule.items()
        }

    def total(self) -> int:
        return sum(len(v) for v in self.by_rule.values())

    def fail_count(self) -> int:
        return sum(1 for items in self.by_rule.values() for i in items if i.status == "FAIL")


# ── API pública ──────────────────────────────────────────────────────────────

def extract_evidence(diff_text: str) -> EvidenceBundle:
    """
    Recorre el diff y produce un bundle por regla con call-sites clasificados.

    Reusa la lógica de los linters T1 (BLOQUEANTES → status=FAIL) y agrega
    PASS / REVIEW para call-sites no violatorios pero relevantes para QA.
    """
    bundle = EvidenceBundle()
    hunks = list(parse_diff(diff_text))

    # 1. Reusar T1 para findings tipo FAIL (violaciones detectadas)
    findings = lint_diff(diff_text)
    for f in findings:
        bundle.add(f.rule_id, EvidenceItem(
            file=f.file,
            line=f.line,
            snippet=f.snippet,
            status="FAIL",
            note=f.fix_hint,
        ))

    # 2. Cumplimientos PASS / REVIEW: recorrer hunks y agregar lo no marcado por T1
    failed_keys = {(f.file, f.line) for f in findings}

    for hunk in hunks:
        if not hunk.file.endswith(CS_EXTENSIONS):
            continue
        for added in hunk.added:
            content = added.content
            key = (hunk.file, added.line_no)

            # ─ R1: literales en RIDIOMA call-sites
            if _RE_RIDIOMA_USAGE.search(content) and (
                "Error.Agregar" in content or ".AgregarError" in content
                or ".Text" in content or ".ToolTip" in content
                or "MostrarMensaje" in content or "msgd.Show" in content
            ):
                if key not in failed_keys:
                    bundle.add("R1", EvidenceItem(
                        file=hunk.file, line=added.line_no,
                        snippet=content.strip(), status="PASS",
                        note="usa Idm.Texto / coMens",
                    ))

            # ─ R2: new cConexion en archivo Facade es PASS, en Bus/Dalc es FAIL (cubierto por T1)
            if _RE_NEW_CCONEXION.search(content):
                if key not in failed_keys and (_is_facade(hunk.file) or _is_batch_orchestrator(hunk.file)):
                    bundle.add("R2", EvidenceItem(
                        file=hunk.file, line=added.line_no,
                        snippet=content.strip(), status="PASS",
                        note="cConexion en capa autorizada",
                    ))

            # ─ R3: transacciones — idem
            if _RE_TRANSACTION_CALL.search(content) and key not in failed_keys:
                if _is_facade(hunk.file) or _is_batch_orchestrator(hunk.file):
                    bundle.add("R3", EvidenceItem(
                        file=hunk.file, line=added.line_no,
                        snippet=content.strip(), status="PASS",
                        note="transacción en capa autorizada",
                    ))

            # ─ R4: SQL parametrizado correcto (heurística inversa)
            if _RE_SQL_KEYWORD_IN_STRING.search(content) and key not in failed_keys:
                # Si el string contiene keywords SQL pero NO fue marcado por T1, es PASS o REVIEW
                if "@p_" in content or ":p_" in content:
                    bundle.add("R4", EvidenceItem(
                        file=hunk.file, line=added.line_no,
                        snippet=content.strip(), status="PASS",
                        note="usa parámetros nominales",
                    ))
                else:
                    bundle.add("R4", EvidenceItem(
                        file=hunk.file, line=added.line_no,
                        snippet=content.strip(), status="REVIEW",
                        note="SQL sin variables concatenadas detectado, sin parámetros visibles",
                    ))

            # ─ R10: EjecutarQuery PASS si seguido por verificación
            if _RE_EJECUTAR_QUERY.search(content) and key not in failed_keys:
                bundle.add("R10", EvidenceItem(
                    file=hunk.file, line=added.line_no,
                    snippet=content.strip(), status="PASS",
                    note="EjecutarQuery con verificación post próxima",
                ))

            # ─ multi_empresa: queries sobre tablas core
            multi_empresa_status, table, has_filter = _check_multi_empresa(content)
            if multi_empresa_status:
                bundle.add("multi_empresa", EvidenceItem(
                    file=hunk.file, line=added.line_no,
                    snippet=content.strip(),
                    status="PASS" if has_filter else "REVIEW",
                    note=f"tabla={table} filtro_empresa={'sí' if has_filter else 'no'}",
                ))

    return bundle


# ── Helpers ──────────────────────────────────────────────────────────────────

def _check_multi_empresa(line: str) -> tuple[bool, str, bool]:
    """
    ¿La línea contiene una query SQL sobre una tabla core?
    Retorna (aplica, tabla, tiene_filtro_empresa).
    """
    upper = line.upper()
    for table, empresa_col in CORE_TABLES_WITH_EMPRESA.items():
        if re.search(rf"\b{table}\b", upper):
            # Verificar si hay alguna mención al filtro de empresa cerca
            has_filter = empresa_col in upper or "EMPRESA" in upper
            return (True, table, has_filter)
    return (False, "", False)
