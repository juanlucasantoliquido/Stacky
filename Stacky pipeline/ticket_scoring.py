"""
ticket_scoring.py — F2. Scoring funcional de tickets (0-100) y estimación de
tiempo por etapa.

Reutiliza ``DynamicComplexityScorer`` para:
  - Detectar módulos del ticket.
  - Obtener ``similar_tickets_count`` desde el knowledge base.
  - Calcular complejidad histórica y estática.

Y agrega encima:
  - Score numérico 0-100 compuesto por 6 factores ponderables (config).
  - Delta de ajuste por ``ticket_type`` → ``project`` → ``global``.
  - Estimación por etapa (pm / dev / tester) derivada del score y los timeouts
    dinámicos que ya calcula el scorer.

Es 100% puro: no escribe en disco. La persistencia vive en
``estimation_store``.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from dynamic_complexity_scorer import DynamicComplexityScorer, ComplexityScore

logger = logging.getLogger("stacky.scoring")

_BASE_DIR = Path(__file__).resolve().parent
_CONFIG_PATH = _BASE_DIR / "config.json"
_PROJECTS_DIR = _BASE_DIR / "projects"


def _build_scorer_for_project(project: str | None) -> DynamicComplexityScorer:
    """
    Devuelve un ``DynamicComplexityScorer`` con el ``KnowledgeBase`` del
    proyecto pre-inyectado para evitar que el scorer caiga en el fallback
    ``KnowledgeBase()`` (bug preexistente: firma requiere tickets_base y
    project_name).
    """
    kb = None
    if project:
        try:
            from knowledge_base import get_kb
            tickets_base = str(_PROJECTS_DIR / project / "tickets")
            kb = get_kb(tickets_base, project)
        except Exception as e:
            logger.debug("scoring: no se pudo construir KnowledgeBase para %s: %s", project, e)
    return DynamicComplexityScorer(knowledge_base=kb)

# ── Pesos por defecto (ajustables por config) ────────────────────────────────
DEFAULT_WEIGHTS = {
    "tech_complexity": 25,   # señal estática+histórica del scorer
    "uncertainty":     20,   # inversamente proporcional a similar_tickets_count
    "impact":          15,   # estimado por tipo de ticket + blast radius
    "files_affected":  15,   # inferido de módulos detectados
    "functional_risk": 15,   # keywords de riesgo (seguridad, migración, etc.)
    "external_dep":    10,   # mención de APIs externas / webhooks
}

DEFAULT_SCORING_CONFIG: dict[str, Any] = {
    "weights": DEFAULT_WEIGHTS,
    "complexity_thresholds": {
        "simple":   {"max_score": 35},
        "medio":    {"max_score": 65},
        "complejo": {"max_score": 100},
    },
    "stage_distribution": {
        "pm":     0.25,
        "dev":    0.50,
        "tester": 0.25,
    },
    "delta_by_ticket_type": {},
    "delta_pct_default":    15.0,
    "auto_calibrate":       False,
    "min_samples_for_calibration": 20,
    # ── F2 Fase 1: multiplicadores de estimación heurística (calibrables) ────
    # Fórmula:
    #   estimated_minutes = base_minutes
    #                     × module_factor
    #                     × complexity_mult        (0.5 + score/100 × 1.5)
    #                     × uncertainty_mult       (1 + uncertainty/100 × max_uncertainty_boost)
    #                     × (1 + functional_risk/100 × functional_risk_boost)
    #                     × (1 + external_dep/100  × external_dep_boost)
    #                     × (1 + files_affected/100 × files_affected_boost)
    #                     × (1 + delta_pct/100)
    # Todos los coeficientes exponen una perilla configurable. Editarlos desde
    # `config.json.scoring_defaults.multipliers` o `projects/<P>/config.json.scoring.multipliers`.
    "base_minutes": 25,
    "multipliers": {
        "complexity_min":         0.5,   # multiplicador cuando score=0
        "complexity_range":       1.5,   # span (score=100 → complexity_mult=0.5+1.5=2.0)
        "max_uncertainty_boost":  0.5,   # +50% cuando uncertainty=100
        "functional_risk_boost":  0.3,   # +30% cuando functional_risk=100
        "external_dep_boost":     0.3,   # +30% cuando external_dep=100
        "files_affected_boost":   0.3,   # +30% cuando files_affected=100
    },
}


@dataclass
class ScoringFactors:
    tech_complexity: int = 0
    uncertainty:     int = 0
    impact:          int = 0
    files_affected:  int = 0
    functional_risk: int = 0
    external_dep:    int = 0

    def to_dict(self) -> dict[str, int]:
        return asdict(self)


@dataclass
class TicketScoring:
    """Resultado canónico de scoring para persistir/serializar."""
    score:            int
    complexity:       str  # simple / medio / complejo
    factors:          ScoringFactors
    modules_detected: list[str] = field(default_factory=list)
    similar_tickets_count: int = 0
    estimated_minutes: int = 0
    delta_pct_applied: float = 0.0
    delta_source:      str   = "global"  # ticket_type | project | global
    per_stage_minutes: dict[str, int] = field(default_factory=dict)
    # Fase 1/2 — indica qué motor produjo ``estimated_minutes``.
    # ``heuristic`` = multivariable ponderada (siempre disponible).
    # ``regression`` = modelo de regresión lineal entrenado (si hay ≥ umbral muestras).
    estimation_method: str = "heuristic"

    def to_dict(self) -> dict[str, Any]:
        return {
            "score":                 self.score,
            "complexity":            self.complexity,
            "factors":               self.factors.to_dict(),
            "modules_detected":      list(self.modules_detected),
            "similar_tickets_count": self.similar_tickets_count,
            "estimated_minutes":     self.estimated_minutes,
            "delta_pct_applied":     round(self.delta_pct_applied, 2),
            "delta_source":          self.delta_source,
            "per_stage_minutes":     dict(self.per_stage_minutes),
            "estimation_method":     self.estimation_method,
        }


# ── Config helpers ───────────────────────────────────────────────────────────

def _load_json(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except Exception as e:
        logger.debug("scoring: no se pudo leer %s: %s", path, e)
        return {}


def load_scoring_config(project_name: str | None = None) -> dict[str, Any]:
    """
    Devuelve la config de scoring resuelta:
        global (config.json)  <-  project (projects/<NAME>/config.json)
    Cada nivel extiende/overridea al anterior.
    """
    cfg: dict[str, Any] = {}

    # Nivel 1: defaults
    cfg = json.loads(json.dumps(DEFAULT_SCORING_CONFIG))  # deep copy

    # Nivel 2: config global
    global_cfg = _load_json(_CONFIG_PATH).get("scoring_defaults", {})
    _deep_merge(cfg, global_cfg)

    # Nivel 3: config de proyecto
    if project_name:
        proj_cfg = _load_json(_PROJECTS_DIR / project_name / "config.json").get("scoring", {})
        _deep_merge(cfg, proj_cfg)

    return cfg


def _deep_merge(dst: dict[str, Any], src: dict[str, Any]) -> None:
    for k, v in (src or {}).items():
        if isinstance(v, dict) and isinstance(dst.get(k), dict):
            _deep_merge(dst[k], v)
        else:
            dst[k] = v


def resolve_delta_pct(
    cfg: dict[str, Any],
    *,
    ticket_type: str | None = None,
    project: str | None = None,
    global_calibration: dict[str, Any] | None = None,
) -> tuple[float, str]:
    """
    Resuelve el delta_pct a aplicar, con la precedencia:
        ticket_type → project → global

    Devuelve ``(delta_pct, source)`` donde source ∈ {"ticket_type", "project", "global"}.
    """
    # Ticket type override
    by_type = cfg.get("delta_by_ticket_type") or {}
    if ticket_type and ticket_type in by_type:
        try:
            return float(by_type[ticket_type]), "ticket_type"
        except (TypeError, ValueError):
            pass

    # Project-level calibration (de data/estimations.json)
    if project and global_calibration:
        by_project = global_calibration.get("by_project", {})
        p = by_project.get(project) or {}
        if isinstance(p.get("suggested_delta_pct"), (int, float)):
            return float(p["suggested_delta_pct"]), "project"

    # Global fallback
    return float(cfg.get("delta_pct_default", 15.0)), "global"


# ── Heurísticas auxiliares ───────────────────────────────────────────────────

_IMPACT_KEYWORDS_HIGH = (
    "producción", "produccion", "multi-empresa", "multi empresa",
    "fiscal", "sii", "afip", "auditoría", "auditoria",
)
_IMPACT_KEYWORDS_MED = (
    "reporte", "formulario", "grilla", "búsqueda", "busqueda",
)
_FUNCTIONAL_RISK_KEYWORDS = (
    "seguridad", "autorización", "autorizacion", "permisos", "migración",
    "migracion", "irreversible", "data loss", "perdida de datos",
    "eliminar", "drop", "delete sin where",
)
_EXTERNAL_DEP_KEYWORDS = (
    "api externa", "webhook", "integración con", "integracion con",
    "servicio externo", "http://", "https://",
)


def _score_impact(content_lower: str, modules: list[str]) -> int:
    """Devuelve 0..100 sobre la dimensión impacto. Mezcla keywords + alcance módulos."""
    if any(k in content_lower for k in _IMPACT_KEYWORDS_HIGH):
        base = 80
    elif any(k in content_lower for k in _IMPACT_KEYWORDS_MED):
        base = 50
    else:
        base = 30
    if "bd" in modules:
        base = min(100, base + 20)
    if "batch_negocio" in modules:
        base = min(100, base + 15)
    return base


def _score_files_affected(modules: list[str]) -> int:
    if not modules:
        return 20
    n = len(modules)
    # 1 módulo → 25, 2 → 45, 3 → 65, 4+ → 85-100
    return min(100, 15 + n * 20)


def _score_functional_risk(content_lower: str) -> int:
    if any(k in content_lower for k in _FUNCTIONAL_RISK_KEYWORDS):
        return 75
    # Señales menores
    if any(k in content_lower for k in ("validación", "validacion", "regla de negocio")):
        return 45
    return 20


def _score_external_dep(content_lower: str) -> int:
    if any(k in content_lower for k in _EXTERNAL_DEP_KEYWORDS):
        return 70
    return 15


def _score_tech_complexity(cs: ComplexityScore) -> int:
    return {"simple": 25, "medio": 55, "complejo": 85}.get(cs.complexity, 55)


def _score_uncertainty(cs: ComplexityScore) -> int:
    # Más similares → menos incertidumbre.
    n = cs.similar_tickets_count
    if n >= 5:
        return 15
    if n >= 3:
        return 30
    if n >= 1:
        return 55
    return 80


# ── Core ─────────────────────────────────────────────────────────────────────

def compute_scoring(
    inc_content: str,
    *,
    project: str | None = None,
    ticket_type: str | None = None,
    work_item_id: int = 0,
    scorer: DynamicComplexityScorer | None = None,
    global_calibration: dict[str, Any] | None = None,
) -> TicketScoring:
    """
    Calcula scoring del ticket. Retorna ``TicketScoring`` listo para persistir.

    ``inc_content`` es el texto de INCIDENTE.md / descripción del ticket.
    ``ticket_type``: hint opcional (bug/feature/db/etc.) para delta por tipo.
    ``global_calibration`` proviene de ``estimation_store.load_calibration()``.
    """
    cfg = load_scoring_config(project)
    weights: dict[str, int] = cfg.get("weights") or DEFAULT_WEIGHTS

    sc = scorer or _build_scorer_for_project(project)
    try:
        cs = sc.score(inc_content, work_item_id=work_item_id)
    except Exception as e:
        logger.warning("scoring: DynamicComplexityScorer falló (%s) — usando fallback", e)
        cs = ComplexityScore(
            complexity="medio",
            timeout_pm=600, timeout_dev=900, timeout_qa=600,
            confidence="low", modules_detected=[],
            estimated_total_minutes=35,
        )

    content_lower = (inc_content or "").lower()

    factors = ScoringFactors(
        tech_complexity=_score_tech_complexity(cs),
        uncertainty=_score_uncertainty(cs),
        impact=_score_impact(content_lower, cs.modules_detected),
        files_affected=_score_files_affected(cs.modules_detected),
        functional_risk=_score_functional_risk(content_lower),
        external_dep=_score_external_dep(content_lower),
    )

    # Weighted sum 0..100
    total_weight = sum(weights.values()) or 1
    raw = 0.0
    for key, w in weights.items():
        value = getattr(factors, key, 0)
        raw += value * w
    score = int(round(raw / total_weight))
    score = max(0, min(100, score))

    # Complexity label por umbrales
    complexity = _score_to_complexity(score, cfg.get("complexity_thresholds"))

    # Delta
    delta_pct, delta_source = resolve_delta_pct(
        cfg, ticket_type=ticket_type, project=project,
        global_calibration=global_calibration,
    )

    # ── Estimación: Fase 2 (regresión) con fallback a Fase 1 (heurística) ──
    # 1) Intentar modelo entrenado (requiere ≥ N muestras cerradas, ver
    #    estimation_model.MIN_SAMPLES).
    # 2) Fallback: heurística multivariable ponderada usando los 6 factores.
    estimation_method = "heuristic"
    regression_minutes: int | None = None
    try:
        from estimation_model import predict as _em_predict
        regression_minutes = _em_predict(factors, cs.similar_tickets_count)
    except Exception as e:
        logger.debug("scoring: estimation_model.predict falló: %s", e)
        regression_minutes = None

    # Coeficientes de Fase 1 (calibrables por config)
    mults = cfg.get("multipliers") or DEFAULT_SCORING_CONFIG["multipliers"]
    base_minutes = float(cfg.get("base_minutes",
                                  DEFAULT_SCORING_CONFIG["base_minutes"]))
    module_factor = _safe_module_factor(cs, sc)

    # complexity_mult: 0.5 + (score/100) * 1.5  (rango 0.5× – 2×)
    complexity_mult = (float(mults.get("complexity_min", 0.5))
                       + (score / 100.0) * float(mults.get("complexity_range", 1.5)))
    # uncertainty_mult: 1 + (uncertainty/100) * max_uncertainty_boost
    uncertainty_mult = 1.0 + (factors.uncertainty / 100.0) \
                       * float(mults.get("max_uncertainty_boost", 0.5))
    fr_boost   = 1.0 + (factors.functional_risk / 100.0) \
                       * float(mults.get("functional_risk_boost", 0.3))
    ext_boost  = 1.0 + (factors.external_dep / 100.0) \
                       * float(mults.get("external_dep_boost", 0.3))
    files_boost = 1.0 + (factors.files_affected / 100.0) \
                       * float(mults.get("files_affected_boost", 0.3))
    delta_mult = 1.0 + (delta_pct / 100.0)

    heuristic_minutes = (
        base_minutes
        * module_factor
        * complexity_mult
        * uncertainty_mult
        * fr_boost
        * ext_boost
        * files_boost
        * delta_mult
    )
    heuristic_minutes_int = max(1, int(round(heuristic_minutes)))

    if regression_minutes is not None:
        # La regresión predice ``actual_minutes`` crudos (sin delta). Aplicamos
        # el delta como "safety buffer" igual que en la heurística para que
        # ambos caminos sean comparables.
        adjusted_minutes = max(1, int(round(regression_minutes * delta_mult)))
        estimation_method = "regression"
    else:
        adjusted_minutes = heuristic_minutes_int

    logger.debug(
        "scoring: ticket est=%dm method=%s (base=%.1f, mod=%.2f, cmpx=%.2f, unc=%.2f, "
        "fr=%.2f, ext=%.2f, files=%.2f, delta=%.2f)",
        adjusted_minutes, estimation_method, base_minutes, module_factor,
        complexity_mult, uncertainty_mult, fr_boost, ext_boost, files_boost, delta_mult,
    )

    # Distribución por etapa (fracción del total)
    dist = cfg.get("stage_distribution") or DEFAULT_SCORING_CONFIG["stage_distribution"]
    per_stage = {
        stage: max(1, int(round(adjusted_minutes * frac)))
        for stage, frac in dist.items()
    }

    return TicketScoring(
        score=score,
        complexity=complexity,
        factors=factors,
        modules_detected=list(cs.modules_detected),
        similar_tickets_count=cs.similar_tickets_count,
        estimated_minutes=adjusted_minutes,
        delta_pct_applied=round(delta_pct, 2),
        delta_source=delta_source,
        per_stage_minutes=per_stage,
        estimation_method=estimation_method,
    )


def _safe_module_factor(cs: ComplexityScore,
                        scorer: DynamicComplexityScorer) -> float:
    """
    Extrae el ``module_factor`` histórico del scorer para usarlo en Fase 1.
    Es público/privado hermano porque el scorer no lo expone directamente;
    recomputarlo acá es barato y evita tocar su firma.
    """
    try:
        return float(scorer._get_module_factor(cs.modules_detected))
    except Exception:
        return 1.0


def _score_to_complexity(score: int, thresholds: dict[str, Any] | None) -> str:
    thr = thresholds or DEFAULT_SCORING_CONFIG["complexity_thresholds"]
    # Ordenar por max_score ascendente
    try:
        ordered = sorted(thr.items(), key=lambda kv: kv[1].get("max_score", 100))
    except Exception:
        ordered = [("simple", {"max_score": 35}),
                   ("medio", {"max_score": 65}),
                   ("complejo", {"max_score": 100})]
    for name, meta in ordered:
        if score <= meta.get("max_score", 100):
            return name
    return ordered[-1][0] if ordered else "medio"


# ── Helper para leer INCIDENTE.md desde folder de ticket ─────────────────────

def read_incident_content(ticket_folder: str | os.PathLike[str],
                          ticket_id: str | None = None) -> str:
    """Lee INC-<id>.md o INCIDENTE.md con un fallback razonable."""
    base = Path(ticket_folder)
    candidates: list[Path] = []
    if ticket_id:
        candidates.append(base / f"INC-{ticket_id}.md")
    candidates.append(base / "INCIDENTE.md")
    for p in candidates:
        if p.exists():
            try:
                return p.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
    return ""
