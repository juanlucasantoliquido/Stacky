"""
quality_intake.py — Sprint 4: Quality Intake with Layer Router.

PURPOSE
-------
Classify each acceptance criterion (CA) from a ticket by the most appropriate
test layer BEFORE handing anything to Playwright.  The layer router uses
keyword/signal matching on the CA text and maps each item to one of:

    unit | integration | api_contract | component | smoke_e2e | uat | manual_review

Only items classified as "uat" or "smoke_e2e" need a browser.  The rest are
documented in test_portfolio.json with an owner and handoff note, giving the
development team full visibility of what else needs testing.

DESIGN GOALS
------------
- Deterministic rules — no LLM calls for classification (speed + predictability)
- Tool-first: generates a typed artifact (test_portfolio.json) per run
- Traceable: emits quality_intake_result event to execution.jsonl
- Safe: read-only, no side effects outside evidence dir
- Integrates with Sprint 3 data_readiness_preconditions auto-generation

ARTIFACT
--------
evidence/<ticket_id>/<run_id>/test_portfolio.json

EVENT (execution.jsonl)
-----------------------
{
  "event": "quality_intake_result",
  "ticket_id": 122,
  "items_total": 6,
  "layers": {"unit": 2, "integration": 1, "api_contract": 1, "uat": 2},
  "uat_required": true,
  "manual_review_required": false
}

USAGE
-----
    from quality_intake import run_quality_intake
    result = run_quality_intake(
        ticket_id=122,
        title="RF-008 — Filtros de provincia/departamento",
        description_md="...",
        acceptance_criteria=["Validar que al seleccionar provincia...", ...],
        analisis_tecnico="...",
        plan_pruebas="...",
        exec_logger=exec_log,
        evidence_dir=evidence_dir,
        run_id="122",
    )
    # Filter to UAT items for compiler
    uat_items = [i for i in result.items if i.needs_browser]

VERSION
-------
1.0.0 — Sprint 4
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("stacky.qa_uat.quality_intake")

_TOOL_VERSION = "1.0.0"

# ── Layer definitions ──────────────────────────────────────────────────────────

VALID_LAYERS = frozenset({
    "unit", "integration", "api_contract", "component",
    "smoke_e2e", "uat", "manual_review",
})

# Layers that require a browser
BROWSER_LAYERS = frozenset({"uat", "smoke_e2e"})

# Priority: earlier rules in _LAYER_RULES take precedence over later ones.
# Each entry: (layer, needs_browser, keywords_pattern, reason_template)
# The pattern is compiled as case-insensitive over the full CA text.
_LAYER_RULES: list[tuple[str, bool, str, str]] = [
    # --- manual_review (highest priority for sensitive/ambiguous signals) ---
    (
        "manual_review", False,
        r"\bproducci[oó]n\b|datos\s+sensibles|juicio\s+(de\s+)?experto|requiere\s+revisi[oó]n\s+manual",
        "texto menciona producción, datos sensibles o requiere juicio experto",
    ),
    # --- api_contract ---
    (
        "api_contract", False,
        r"\bendpoint\b|\bAPI\b|\brequest\b|\bresponse\b|\bcontrato\b|\bDTO\b|\bOpenAPI\b|\bswagger\b|\bwebservice\b|\bweb\s+service\b",
        "criterio evalúa un contrato API/endpoint",
    ),
    # --- integration ---
    (
        "integration", False,
        r"\bservicio\b|\brepositorio\b|\bbase\s+de\s+datos\b|\b[bB][dD]\b|\bacceso\s+a\b|\bdatos?\s+en\s+base\b|\bpersistencia\b|\bintegra(?:ción|cion)\b|\bconexión\b",
        "criterio valida integración con servicio o base de datos",
    ),
    # --- component ---
    (
        "component", False,
        r"\bcomponente\b|\bwidget\b|\brender\b(?!\s+(?:la\s+)?p[aá]gina)|\bunit\s+component\b",
        "criterio valida un componente aislado sin contexto de navegación",
    ),
    # --- unit (pure logic rules) ---
    (
        "unit", False,
        r"validar\s+que\s+al\s+calcular|regla\s+de\b|c[aá]lculo\b|campo\s+obligatorio|formato\s+de\b|m[aá]scara\b|validaci[oó]n\s+de\s+(?:formato|campo|regla)|expresi[oó]n\s+regular|mapeo\b|\bpure\s+rule\b|\bregla\s+pura\b",
        "criterio valida una regla de negocio pura o cálculo sin interacción UI",
    ),
    # --- smoke_e2e ---
    (
        "smoke_e2e", True,
        r"\blogin\b|\bflujo\s+m[ií]nimo\b|\bsmoke\b|\bruta\s+cr[ií]tica\b|\baccess[oa]\s+b[aá]sico\b",
        "criterio verifica ruta crítica o flujo mínimo de acceso",
    ),
    # --- uat (visual/browser interaction) ---
    (
        "uat", True,
        r"validar\s+que\s+al\s+hacer\s+clic|navegar\s+a\b|seleccionar\s+en\s+pantalla|formulari[oa]\b|grilla\b|visualmente|pantalla\b|tabla\b|bot[oó]n\b|campo\s+de\s+texto|desplegable\b|combo\b|dropdown\b|ddl\b|modal\b|popup\b|filtrar?\b|filtros?\s+de\b|columna\b|columnas\b|pesta[nñ]a\b|lista\s+de\b|se\s+(?:filtr|muestr|cargu|actualiz)|abrir\s+(?:el\s+)?(?:formulari[oa]|domicilio|registro|pesta[nñ]a)|guardar\b|reabrir\b|seleccionad[ao]\b|modificaci[oó]n\b|dar\s+de\s+alta|mantenedor\b|alta\s+de\b",
        "criterio implica interacción visual o navegación de negocio en pantalla",
    ),
]

# Compiled patterns (lazy, built once)
_COMPILED_RULES: Optional[list[tuple[str, bool, re.Pattern, str]]] = None


def _get_compiled_rules() -> list[tuple[str, bool, re.Pattern, str]]:
    global _COMPILED_RULES
    if _COMPILED_RULES is None:
        _COMPILED_RULES = [
            (layer, nb, re.compile(pattern, re.IGNORECASE | re.UNICODE), reason)
            for layer, nb, pattern, reason in _LAYER_RULES
        ]
    return _COMPILED_RULES


# ── Dataclasses ────────────────────────────────────────────────────────────────

@dataclass
class QualityIntakeItem:
    item_id: str
    description: str
    business_risk: str          # "high" | "medium" | "low"
    layer_recommended: str      # one of VALID_LAYERS
    needs_browser: bool
    needs_ui_map: Optional[str] # screen name if needs_browser else None
    needs_data_seed: bool
    reason: str                 # why this layer was chosen
    owner: str                  # "qa_automation" | "developer" | "qa_manual"
    handoff: Optional[str]      # note for non-UAT items

    def to_dict(self) -> dict:
        return {
            "id": self.item_id,
            "description": self.description,
            "layer": self.layer_recommended,
            "priority": _risk_to_priority(self.business_risk),
            "business_risk": self.business_risk,
            "needs_browser": self.needs_browser,
            "needs_ui_map": self.needs_ui_map,
            "needs_data_seed": self.needs_data_seed,
            "reason": self.reason,
            "owner": self.owner,
            **({"handoff": self.handoff} if self.handoff else {}),
        }


@dataclass
class QualityIntakeResult:
    ticket_id: int
    feature: str
    items_total: int
    items: List[QualityIntakeItem]
    uat_required: bool
    manual_review_required: bool
    artifact_path: Optional[str]

    @property
    def uat_items(self) -> List[QualityIntakeItem]:
        return [i for i in self.items if i.layer_recommended in BROWSER_LAYERS]

    @property
    def non_uat_items(self) -> List[QualityIntakeItem]:
        return [i for i in self.items if i.layer_recommended not in BROWSER_LAYERS]

    def layer_counts(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for item in self.items:
            counts[item.layer_recommended] = counts.get(item.layer_recommended, 0) + 1
        return counts

    def to_dict(self) -> dict:
        return {
            "ticket_id": self.ticket_id,
            "feature": self.feature,
            "items_total": self.items_total,
            "uat_required": self.uat_required,
            "manual_review_required": self.manual_review_required,
            "layers": self.layer_counts(),
            "artifact_path": self.artifact_path,
        }


# ── Layer Router ───────────────────────────────────────────────────────────────

def _route_layer(ca_text: str) -> tuple[str, bool, str]:
    """
    Apply ordered rule set to classify a CA.

    Returns (layer, needs_browser, reason).

    Precedence: manual_review > api_contract > integration > component > unit
                > smoke_e2e > uat > manual_review (catch-all fallback).
    """
    text = ca_text.strip()
    if not text:
        return "manual_review", False, "criterio vacío o sin texto"

    for layer, needs_browser, pattern, reason in _get_compiled_rules():
        if pattern.search(text):
            return layer, needs_browser, reason

    # No rule matched — ambiguous, send to manual_review
    return "manual_review", False, "texto ambiguo — ninguna señal clara identificada"


def _infer_business_risk(ca_text: str, layer: str) -> str:
    """
    Infer business risk from layer and presence of risk-signal words.
    Rules:
    - uat/smoke_e2e with high-risk signals → high
    - uat/smoke_e2e without signals → medium
    - unit/integration/api_contract → medium (dev risk)
    - manual_review → high (unknown risk)
    - component → low
    """
    high_risk_re = re.compile(
        r"pago\b|factura\b|cobro\b|liquidaci[oó]n\b|cr[eé]dito\b|deuda\b|acceso\b|autenticaci[oó]n\b|"
        r"permiso\b|seguridad\b|dato\s+sensible\b|alta\s+de\b|cr[íi]tico\b",
        re.IGNORECASE,
    )
    if layer == "manual_review":
        return "high"
    if layer == "component":
        return "low"
    if layer in BROWSER_LAYERS:
        return "high" if high_risk_re.search(ca_text) else "medium"
    return "medium"


def _infer_needs_data_seed(ca_text: str, layer: str) -> bool:
    """
    Items that need browser AND reference entities, grids, or test users
    are likely to need data seed.
    """
    if layer not in BROWSER_LAYERS:
        return False
    seed_signals = re.compile(
        r"grilla\b|datos?\s+de\s+prueba|semilla\b|CLCOD\b|cliente\b|obligacion(es)?\b|"
        r"registro(s)?\b|cargado(s)?\b|existente(s)?\b|previamente\b",
        re.IGNORECASE,
    )
    return bool(seed_signals.search(ca_text))


def _infer_owner(layer: str) -> str:
    if layer in BROWSER_LAYERS:
        return "qa_automation"
    if layer == "manual_review":
        return "qa_manual"
    return "developer"


def _infer_handoff(layer: str) -> Optional[str]:
    _handoffs = {
        "unit": "crear test unitario en Developer Agent",
        "integration": "crear test de integración en Developer Agent",
        "api_contract": "validar contrato en API Contract Validator",
        "component": "crear test de componente en Developer Agent",
        "manual_review": "revisar manualmente — incluir en checklist de release",
        "smoke_e2e": None,  # goes to UAT runner
        "uat": None,        # goes to UAT runner
    }
    return _handoffs.get(layer)


def _risk_to_priority(risk: str) -> str:
    return {"high": "P0", "medium": "P1", "low": "P2"}.get(risk, "P1")


def _build_item_id(ticket_id: int, feature: str, index: int) -> str:
    """
    Build a stable item ID like RF-008-CA-01.
    Tries to extract an RF/task number from the feature title.
    Falls back to ticket_id if not found.
    """
    rf_match = re.search(r'(RF|TASK|US|BUG)[- ]?(\d+)', feature, re.IGNORECASE)
    prefix = f"{rf_match.group(1).upper()}-{rf_match.group(2)}" if rf_match else str(ticket_id)
    return f"{prefix}-CA-{index:02d}"


def _infer_ui_map_screen(ca_text: str, analisis_tecnico: str, plan_pruebas: str) -> Optional[str]:
    """
    Try to find the screen name for UAT items by scanning text for .aspx filenames
    or known screen aliases.
    """
    # Look for explicit .aspx screen names
    aspx_re = re.compile(r'(Frm\w+\.aspx)', re.IGNORECASE)
    for text in (ca_text, analisis_tecnico, plan_pruebas):
        m = aspx_re.search(text)
        if m:
            return m.group(1)
    return None


# ── Auto data_readiness_preconditions generation ──────────────────────────────

def _auto_data_preconditions(item: QualityIntakeItem) -> list[dict]:
    """
    When a UAT item needs_data_seed, generate a minimal data_readiness_preconditions
    list so Stage 3d (check_data_readiness) in Sprint 3 activates automatically.
    """
    if not item.needs_data_seed:
        return []

    # Heuristic: extract likely entity names from the description
    grid_re = re.compile(
        r'\b(Grid\w+|grilla\s+de\s+(\w+)|tabla\s+de\s+(\w+))\b', re.IGNORECASE
    )
    entity_re = re.compile(
        r'\b(CLCOD|RAGEN|ROBLG|RCLIE|RAGEN|RACON|cliente|obligaci[oó]n)\b', re.IGNORECASE
    )

    preconditions = []

    grid_match = grid_re.search(item.description)
    entity_match = entity_re.search(item.description)

    entity_name = "GridData"  # default
    if grid_match:
        # Use full match as entity name
        entity_name = grid_match.group(1).replace(" ", "")
    elif entity_match:
        entity_name = entity_match.group(1).upper()

    preconditions.append({
        "entity": entity_name,
        "type": "grid",
        "input_data": {"CLCOD": "{{CLCOD}}"},
        "expected": {"min_rows": 1},
    })

    return preconditions


# ── Artifact writer ────────────────────────────────────────────────────────────

def _write_test_portfolio(
    result: QualityIntakeResult,
    evidence_dir: Path,
    run_id: str,
) -> str:
    """
    Write test_portfolio.json to evidence/<ticket_id>/<run_id>/test_portfolio.json.
    Returns the absolute path as string.
    """
    run_dir = evidence_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    portfolio = {
        "schema": "test_portfolio/1.0",
        "ticket_id": result.ticket_id,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "strategy": "layered_quality_portfolio",
        "items": [item.to_dict() for item in result.items],
        "summary": {
            "total": result.items_total,
            **result.layer_counts(),
        },
    }

    portfolio_path = run_dir / "test_portfolio.json"
    portfolio_path.write_text(
        json.dumps(portfolio, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info("test_portfolio.json written to %s", portfolio_path)
    return str(portfolio_path)


# ── Main entry point ───────────────────────────────────────────────────────────

def run_quality_intake(
    ticket_id: int,
    title: str,
    description_md: str,
    acceptance_criteria: list[str],
    analisis_tecnico: str = "",
    plan_pruebas: str = "",
    exec_logger=None,
    evidence_dir: Optional[Path] = None,
    run_id: Optional[str] = None,
) -> QualityIntakeResult:
    """
    Classify each acceptance criterion by test layer and generate test_portfolio.json.

    Parameters
    ----------
    ticket_id : int
        ADO work item ID.
    title : str
        Feature title (used to build item IDs like RF-008-CA-01).
    description_md : str
        Full ticket description in Markdown.
    acceptance_criteria : list[str]
        List of CA strings extracted from the ticket.
    analisis_tecnico : str
        Technical analysis text (used for screen detection hints).
    plan_pruebas : str
        Test plan text (used for screen detection hints).
    exec_logger : ExecutionLogger | None
        Active execution logger for emitting quality_intake_result event.
    evidence_dir : Path | None
        Root evidence directory for this ticket.
    run_id : str | None
        Run ID for sub-directory naming. Defaults to str(ticket_id).

    Returns
    -------
    QualityIntakeResult
        Typed result with all classified items and summary flags.
    """
    _run_id = run_id or str(ticket_id)
    _evidence_dir = evidence_dir

    logger.info(
        "quality_intake: ticket=%s, %d CAs to classify",
        ticket_id, len(acceptance_criteria),
    )

    items: List[QualityIntakeItem] = []

    for idx, ca_text in enumerate(acceptance_criteria, start=1):
        item_id = _build_item_id(ticket_id, title, idx)
        layer, needs_browser, reason = _route_layer(ca_text)
        business_risk = _infer_business_risk(ca_text, layer)
        needs_data_seed = _infer_needs_data_seed(ca_text, layer)
        needs_ui_map: Optional[str] = None
        if needs_browser:
            needs_ui_map = _infer_ui_map_screen(ca_text, analisis_tecnico, plan_pruebas)
        owner = _infer_owner(layer)
        handoff = _infer_handoff(layer)

        item = QualityIntakeItem(
            item_id=item_id,
            description=ca_text.strip(),
            business_risk=business_risk,
            layer_recommended=layer,
            needs_browser=needs_browser,
            needs_ui_map=needs_ui_map,
            needs_data_seed=needs_data_seed,
            reason=reason,
            owner=owner,
            handoff=handoff,
        )
        items.append(item)
        logger.debug(
            "  [%s] layer=%s needs_browser=%s reason=%s",
            item_id, layer, needs_browser, reason,
        )

    uat_required = any(i.layer_recommended in BROWSER_LAYERS for i in items)
    manual_review_required = any(i.layer_recommended == "manual_review" for i in items)

    # Write artifact
    artifact_path: Optional[str] = None
    if _evidence_dir is not None:
        try:
            artifact_path = _write_test_portfolio(
                QualityIntakeResult(
                    ticket_id=ticket_id,
                    feature=title,
                    items_total=len(items),
                    items=items,
                    uat_required=uat_required,
                    manual_review_required=manual_review_required,
                    artifact_path=None,  # filled below
                ),
                _evidence_dir,
                _run_id,
            )
        except Exception as exc:
            logger.warning("quality_intake: failed to write test_portfolio.json: %s", exc)

    result = QualityIntakeResult(
        ticket_id=ticket_id,
        feature=title,
        items_total=len(items),
        items=items,
        uat_required=uat_required,
        manual_review_required=manual_review_required,
        artifact_path=artifact_path,
    )

    # Emit execution.jsonl event
    if exec_logger is not None:
        try:
            exec_logger.event("quality_intake_result", {
                "ticket_id": ticket_id,
                "items_total": result.items_total,
                "layers": result.layer_counts(),
                "uat_required": result.uat_required,
                "manual_review_required": result.manual_review_required,
                "artifact_path": artifact_path,
            })
        except Exception as exc:
            logger.warning("quality_intake: failed to emit event: %s", exc)

    logger.info(
        "quality_intake done: %d items, uat_required=%s, layers=%s",
        result.items_total, result.uat_required, result.layer_counts(),
    )
    return result


# ── Helper: extract CAs from ticket dict ─────────────────────────────────────

def extract_acceptance_criteria(ticket_result: dict) -> list[str]:
    """
    Extract a flat list of acceptance criterion strings from a ticket_result dict.

    Tries multiple common locations:
    1. ticket_result["acceptance_criteria"] — list of str
    2. ticket_result["plan_pruebas"] — list of str (plan de pruebas items)
    3. ticket_result["description_md"] — parse "## Criterios de Aceptación" section
    4. ticket_result["p0n_items"] — compiled P0N items list
    """
    # 1. Direct acceptance_criteria field
    ac = ticket_result.get("acceptance_criteria")
    if isinstance(ac, list) and ac:
        return [str(x).strip() for x in ac if str(x).strip()]

    # 2. plan_pruebas items
    plan = ticket_result.get("plan_pruebas")
    if isinstance(plan, list) and plan:
        cas: list[str] = []
        for item in plan:
            if isinstance(item, str):
                cas.append(item.strip())
            elif isinstance(item, dict):
                desc = item.get("description") or item.get("descripcion") or item.get("title") or ""
                datos = item.get("datos") or ""
                esperado = item.get("esperado") or ""
                full_text = " ".join(filter(None, [desc, datos, esperado])).strip()
                if full_text:
                    cas.append(full_text)
        if cas:
            return [c for c in cas if c]

    # 3. Parse description_md for "Criterios de Aceptación" section
    desc_md = ticket_result.get("description_md", "")
    if desc_md:
        ca_section = _extract_ca_section_from_md(desc_md)
        if ca_section:
            return ca_section

    # 4. p0n_items
    p0n = ticket_result.get("p0n_items")
    if isinstance(p0n, list) and p0n:
        return [
            str(item.get("description") or item.get("descripcion") or item).strip()
            for item in p0n
            if item
        ]

    return []


def _extract_ca_section_from_md(md: str) -> list[str]:
    """Parse bullet items from a 'Criterios de Aceptación' heading in Markdown."""
    section_re = re.compile(
        r'#+\s*criterios?\s+de\s+aceptaci[oó]n\b(.*?)(?=\n#+|\Z)',
        re.IGNORECASE | re.DOTALL,
    )
    m = section_re.search(md)
    if not m:
        return []
    body = m.group(1)
    bullet_re = re.compile(r'^[-*•]\s+(.+)', re.MULTILINE)
    items = [b.strip() for b in bullet_re.findall(body) if b.strip()]
    return items


# ── SKIPPED verdict builder ───────────────────────────────────────────────────

def build_no_uat_skipped_result(ticket_id: int, portfolio_path: Optional[str]) -> dict:
    """
    Build the pipeline exit dict for SKIPPED PIP NO_UAT_ITEMS.
    This is NOT an error — the ticket does not need browser testing.
    """
    return {
        "ok": True,
        "verdict": "SKIPPED",
        "category": "PIP",
        "reason": "NO_UAT_ITEMS",
        "message": (
            "No acceptance criteria were classified as UAT or smoke_e2e. "
            "All CAs can be validated in lower test layers. "
            "No Playwright tests will be generated."
        ),
        "human_action_required": (
            "revisar test_portfolio.json — todos los CAs clasificados en capas inferiores"
        ),
        "test_portfolio_path": portfolio_path,
        "ticket_id": ticket_id,
    }
