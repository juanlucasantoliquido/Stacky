"""Risk engine determinístico para PM Intelligence Suite — Fase 1 MVP.

Sin IA. Sin confidence inventada. Cada regla:
- Tiene un `rule` name único y trazable
- Genera evidencia explícita (qué datos disparan la regla)
- Asigna severidad por umbrales claros, no por sentimiento

Reglas implementadas:
- delay_velocity_deficit       — completion_rate vs días transcurridos
- aging_blocked_item           — item en estado blocked > umbral
- high_aging_item              — item abierto > umbral de aging
- scope_creep_detected         — items agregados al sprint después del start
- data_quality_missing_points  — % items sin story points > umbral
- data_quality_missing_owner   — % items sin assigned_to > umbral

El output de detect_risks() es input para la capa de persistencia (api/pm.py),
que se encarga de upsert en pm_risk_items con risk_id determinista.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Iterable

from services.pm.pm_kpi_engine import (
    DEFAULT_STATE_MAP,
    SprintKPIs,
    StateMap,
)


# ── Umbrales por regla (override-able vía RiskConfig) ──────────────────────────
@dataclass(frozen=True)
class RiskConfig:
    """Umbrales determinísticos. Defaults conservadores; ajustar por proyecto si hace falta."""
    blocked_aging_days_warn: float = 2.0
    blocked_aging_days_high: float = 5.0
    high_aging_days_warn: float = 14.0
    high_aging_days_high: float = 30.0
    velocity_deficit_pct_warn: float = 10.0
    velocity_deficit_pct_high: float = 25.0
    missing_points_pct_warn: float = 25.0
    missing_points_pct_high: float = 50.0
    missing_owner_pct_warn: float = 15.0
    missing_owner_pct_high: float = 30.0
    scope_creep_grace_hours: float = 24.0   # margen post start_date antes de considerar creep


DEFAULT_RISK_CONFIG = RiskConfig()


@dataclass
class DetectedRisk:
    """Riesgo determinista detectado. `confidence` no existe a propósito —
    las reglas son booleanas con umbrales; no hay incertidumbre que reportar."""
    risk_id: str
    category: str
    severity: str
    rule: str
    description: str
    affected_items: list[int] = field(default_factory=list)
    evidence: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "risk_id": self.risk_id,
            "category": self.category,
            "severity": self.severity,
            "rule": self.rule,
            "description": self.description,
            "affected_items": self.affected_items,
            "evidence": self.evidence,
        }


# ── helpers ────────────────────────────────────────────────────────────────────

def _stable_risk_id(project: str, sprint_id: str, rule: str, affected_items: list[int]) -> str:
    """Genera un risk_id determinístico: re-sync del mismo sprint reusa el mismo id."""
    payload = f"{project}|{sprint_id}|{rule}|{','.join(str(i) for i in sorted(affected_items))}"
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]
    return f"RSK-{digest}"


def _severity_for_threshold(value: float, warn: float, high: float) -> str | None:
    if value >= high:
        return "HIGH"
    if value >= warn:
        return "MEDIUM"
    return None


# ── reglas individuales ────────────────────────────────────────────────────────

def _detect_delay_velocity_deficit(
    *, project: str, sprint_id: str, kpis: SprintKPIs, cfg: RiskConfig
) -> DetectedRisk | None:
    """Si completion_rate < % esperado según fracción del sprint transcurrida."""
    if kpis.days_remaining is None or kpis.total_items == 0:
        return None
    # Heurística: si quedan días, hacemos un check simple: completion debería ser >= 100 - (days_remaining/total_days * 100).
    # Sin total_days no podemos calcular fracción; usamos un proxy: si quedan <= 2 días y completion < 80, riesgo.
    # Mejor: comparar contra umbral simple ajustable; sin histórico no podemos hacer mejor.
    if kpis.days_remaining > 3:
        return None  # Demasiado temprano para juzgar
    expected_completion = 90.0 if kpis.days_remaining <= 1 else 75.0
    deficit = expected_completion - kpis.completion_rate_pct
    if deficit <= 0:
        return None
    severity = _severity_for_threshold(deficit, cfg.velocity_deficit_pct_warn, cfg.velocity_deficit_pct_high)
    if severity is None:
        return None
    affected = []  # delay agregado, no ítems individuales
    return DetectedRisk(
        risk_id=_stable_risk_id(project, sprint_id, "delay_velocity_deficit", affected),
        category="DELAY",
        severity=severity,
        rule="delay_velocity_deficit",
        description=(
            f"Sprint con {kpis.days_remaining} día(s) restantes y "
            f"completion {kpis.completion_rate_pct:.1f}% — déficit de {deficit:.1f}pp "
            f"vs esperado ({expected_completion:.0f}%)."
        ),
        affected_items=affected,
        evidence={
            "days_remaining": kpis.days_remaining,
            "completion_rate_pct": kpis.completion_rate_pct,
            "expected_completion_pct": expected_completion,
            "deficit_pp": round(deficit, 2),
        },
    )


def _detect_blocked_aging(
    *,
    project: str,
    sprint_id: str,
    work_items: list[dict],
    transitions_by_id: dict[int, list[dict]],
    cfg: RiskConfig,
    now: datetime,
    state_map: StateMap,
) -> list[DetectedRisk]:
    """Items actualmente en estado blocked, agrupados por severidad según días bloqueado."""
    risks: list[DetectedRisk] = []
    by_severity: dict[str, list[tuple[int, float]]] = {"MEDIUM": [], "HIGH": []}
    for wi in work_items:
        if state_map.category(wi.get("state")) != "blocked":
            continue
        ado_id = wi.get("ado_id")
        if not ado_id:
            continue
        transitions = transitions_by_id.get(int(ado_id)) or []
        # Buscamos la entrada más reciente al estado blocked
        blocked_since: datetime | None = None
        for t in reversed(transitions):
            if state_map.category(t.get("state")) == "blocked":
                blocked_since = t.get("entered_at") if isinstance(t.get("entered_at"), datetime) else None
                break
        if blocked_since is None:
            # Fallback conservador: tiempo desde changed_at
            changed = wi.get("changed_at")
            if isinstance(changed, datetime):
                blocked_since = changed
        if blocked_since is None:
            continue
        days_blocked = (now - blocked_since).total_seconds() / 86400.0
        severity = _severity_for_threshold(days_blocked, cfg.blocked_aging_days_warn, cfg.blocked_aging_days_high)
        if severity is None:
            continue
        by_severity[severity].append((int(ado_id), round(days_blocked, 2)))

    for severity, items in by_severity.items():
        if not items:
            continue
        affected = [ado_id for ado_id, _ in items]
        evidence_items = [{"ado_id": ado_id, "days_blocked": d} for ado_id, d in items]
        risks.append(DetectedRisk(
            risk_id=_stable_risk_id(project, sprint_id, f"aging_blocked_{severity.lower()}", affected),
            category="BLOCKED",
            severity=severity,
            rule="aging_blocked_item",
            description=(
                f"{len(items)} item(s) en estado blocked más de "
                f"{cfg.blocked_aging_days_warn if severity == 'MEDIUM' else cfg.blocked_aging_days_high} días."
            ),
            affected_items=affected,
            evidence={"items": evidence_items, "threshold_days": cfg.blocked_aging_days_warn if severity == "MEDIUM" else cfg.blocked_aging_days_high},
        ))
    return risks


def _detect_high_aging(
    *,
    project: str,
    sprint_id: str,
    work_items: list[dict],
    cfg: RiskConfig,
    now: datetime,
    state_map: StateMap,
) -> list[DetectedRisk]:
    """Items abiertos (no done) con aging > umbral. Agrupado por severidad."""
    by_severity: dict[str, list[tuple[int, float]]] = {"MEDIUM": [], "HIGH": []}
    for wi in work_items:
        if state_map.category(wi.get("state")) == "done":
            continue
        created = wi.get("created_at")
        if not isinstance(created, datetime):
            continue
        aging = (now - created).total_seconds() / 86400.0
        severity = _severity_for_threshold(aging, cfg.high_aging_days_warn, cfg.high_aging_days_high)
        if severity is None:
            continue
        by_severity[severity].append((int(wi["ado_id"]), round(aging, 2)))

    risks: list[DetectedRisk] = []
    for severity, items in by_severity.items():
        if not items:
            continue
        affected = [ado_id for ado_id, _ in items]
        evidence_items = [{"ado_id": ado_id, "aging_days": d} for ado_id, d in items]
        risks.append(DetectedRisk(
            risk_id=_stable_risk_id(project, sprint_id, f"high_aging_{severity.lower()}", affected),
            category="DELAY",
            severity=severity,
            rule="high_aging_item",
            description=(
                f"{len(items)} item(s) abierto(s) con aging > "
                f"{cfg.high_aging_days_warn if severity == 'MEDIUM' else cfg.high_aging_days_high} días."
            ),
            affected_items=affected,
            evidence={"items": evidence_items, "threshold_days": cfg.high_aging_days_warn if severity == "MEDIUM" else cfg.high_aging_days_high},
        ))
    return risks


def _detect_scope_creep(
    *,
    project: str,
    sprint_id: str,
    sprint: dict,
    work_items: list[dict],
    cfg: RiskConfig,
) -> DetectedRisk | None:
    """Items cuya created_at es posterior al start_date del sprint + grace.

    Heurística conservadora para v1: si el ítem se creó después de empezado el sprint,
    asumimos que fue agregado mid-sprint. No tenemos historial de iteration_path
    para detectar moves de otros sprints (eso es Fase 2+).
    """
    start = sprint.get("start_date")
    if not isinstance(start, datetime):
        return None
    grace = start + timedelta(hours=cfg.scope_creep_grace_hours)
    creeped: list[tuple[int, str]] = []
    for wi in work_items:
        created = wi.get("created_at")
        if not isinstance(created, datetime):
            continue
        if created > grace:
            creeped.append((int(wi["ado_id"]), created.isoformat()))
    if not creeped:
        return None
    affected = [ado_id for ado_id, _ in creeped]
    severity = "HIGH" if len(creeped) >= 5 else "MEDIUM"
    return DetectedRisk(
        risk_id=_stable_risk_id(project, sprint_id, "scope_creep_detected", affected),
        category="SCOPE_CREEP",
        severity=severity,
        rule="scope_creep_detected",
        description=(
            f"{len(creeped)} item(s) creado(s) después del inicio del sprint "
            f"(+{cfg.scope_creep_grace_hours:.0f}h de gracia)."
        ),
        affected_items=affected,
        evidence={
            "sprint_start": start.isoformat(),
            "grace_hours": cfg.scope_creep_grace_hours,
            "items": [{"ado_id": a, "created_at": c} for a, c in creeped],
        },
    )


def _detect_data_quality(
    *, project: str, sprint_id: str, kpis: SprintKPIs, cfg: RiskConfig
) -> list[DetectedRisk]:
    """Riesgos de calidad de datos: degradan la confianza del resto de KPIs."""
    risks: list[DetectedRisk] = []
    if kpis.total_items == 0:
        return risks

    pct_no_points = 100.0 * kpis.items_without_estimation / kpis.total_items
    severity = _severity_for_threshold(pct_no_points, cfg.missing_points_pct_warn, cfg.missing_points_pct_high)
    if severity is not None:
        risks.append(DetectedRisk(
            risk_id=_stable_risk_id(project, sprint_id, f"data_quality_missing_points_{severity.lower()}", []),
            category="DATA_QUALITY",
            severity=severity,
            rule="data_quality_missing_points",
            description=(
                f"{kpis.items_without_estimation}/{kpis.total_items} item(s) sin story points "
                f"({pct_no_points:.1f}%) — completion_rate cae a métrica por items."
            ),
            affected_items=[],
            evidence={
                "items_without_estimation": kpis.items_without_estimation,
                "total_items": kpis.total_items,
                "percentage": round(pct_no_points, 2),
            },
        ))

    pct_no_owner = 100.0 * kpis.items_without_owner / kpis.total_items
    severity = _severity_for_threshold(pct_no_owner, cfg.missing_owner_pct_warn, cfg.missing_owner_pct_high)
    if severity is not None:
        risks.append(DetectedRisk(
            risk_id=_stable_risk_id(project, sprint_id, f"data_quality_missing_owner_{severity.lower()}", []),
            category="DATA_QUALITY",
            severity=severity,
            rule="data_quality_missing_owner",
            description=(
                f"{kpis.items_without_owner}/{kpis.total_items} item(s) sin assigned_to "
                f"({pct_no_owner:.1f}%) — indica falta de ownership."
            ),
            affected_items=[],
            evidence={
                "items_without_owner": kpis.items_without_owner,
                "total_items": kpis.total_items,
                "percentage": round(pct_no_owner, 2),
            },
        ))

    return risks


# ── orquestador público ────────────────────────────────────────────────────────

def detect_risks(
    *,
    project: str,
    sprint: dict,
    work_items: Iterable[dict],
    kpis: SprintKPIs,
    transitions_by_ado_id: dict[int, list[dict]] | None = None,
    config: RiskConfig = DEFAULT_RISK_CONFIG,
    state_map: StateMap = DEFAULT_STATE_MAP,
    now: datetime | None = None,
) -> list[DetectedRisk]:
    """Ejecuta todas las reglas determinísticas. Devuelve lista de DetectedRisk."""
    now = now or datetime.utcnow()
    transitions_by_ado_id = transitions_by_ado_id or {}
    items_list = list(work_items)
    sprint_id = str(sprint.get("id") or sprint.get("path") or "unknown")

    risks: list[DetectedRisk] = []

    delay = _detect_delay_velocity_deficit(
        project=project, sprint_id=sprint_id, kpis=kpis, cfg=config
    )
    if delay:
        risks.append(delay)

    risks.extend(_detect_blocked_aging(
        project=project, sprint_id=sprint_id, work_items=items_list,
        transitions_by_id=transitions_by_ado_id, cfg=config, now=now, state_map=state_map,
    ))

    risks.extend(_detect_high_aging(
        project=project, sprint_id=sprint_id, work_items=items_list,
        cfg=config, now=now, state_map=state_map,
    ))

    creep = _detect_scope_creep(
        project=project, sprint_id=sprint_id, sprint=sprint, work_items=items_list, cfg=config,
    )
    if creep:
        risks.append(creep)

    risks.extend(_detect_data_quality(
        project=project, sprint_id=sprint_id, kpis=kpis, cfg=config,
    ))

    return risks
