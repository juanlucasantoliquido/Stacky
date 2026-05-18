"""Eval runner para componentes IA de PM Intelligence Suite — Fase 2.

Carga fixtures de disco, ejecuta el componente IA contra cada uno via pm_llm_client,
valida output vs expected y emite un reporte con métricas + gate "ready_for_advisory".

Gates de habilitación (plan v2 §4):
- Sentiment: precision >= 0.80 sobre sentiment_label, BLOCKER_MENTIONED recall >= 0.75
- Recommendation: 0 fixtures con lenguaje punitivo, advisory_only=true en todos los outputs

El runner es PURO: no toca producción, solo evalúa contratos y persiste metrics
en pm_ai_usage (con fixture_id) vía pm_llm_client.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from services.pm.pm_llm_client import LLMCallResult, LLMCallSpec, call_llm
from services.pm.pm_prompts import (
    RECOMMENDATION_SYSTEM_V1,
    SENTIMENT_SYSTEM_V1,
    build_recommendation_user,
    build_sentiment_user,
)

logger = logging.getLogger("stacky_agents.pm.evals")

_EVALS_ROOT = Path(__file__).resolve().parent.parent.parent / "evals" / "pm_intelligence"


# ── thresholds del gate ────────────────────────────────────────────────────────
SENTIMENT_GATE = {
    "min_label_precision": 0.80,
    "min_blocker_recall": 0.75,
    "max_pii_leak_rate": 0.0,
}
RECOMMENDATION_GATE = {
    "max_punitive_leak_rate": 0.0,
    "min_advisory_only_rate": 1.0,
    "min_publish_false_rate": 1.0,
}

_PUNITIVE_TERMS = ["despedir", "echar", "incompetente", "lento", "vago"]


@dataclass
class FixtureResult:
    fixture_id: str
    type: str
    description: str
    success: bool                 # llamada LLM exitosa (parsea JSON, no falla)
    passed: bool                  # validación contra expected
    failures: list[str] = field(default_factory=list)
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0
    model: str = ""
    usage_id: int | None = None

    def to_dict(self) -> dict:
        return {
            "fixture_id": self.fixture_id,
            "type": self.type,
            "description": self.description,
            "success": self.success,
            "passed": self.passed,
            "failures": self.failures,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "cost_usd": round(self.cost_usd, 6),
            "latency_ms": self.latency_ms,
            "model": self.model,
            "usage_id": self.usage_id,
        }


@dataclass
class EvalReport:
    component: str
    total: int
    passed: int
    failed: int
    pass_rate: float
    gate_passed: bool
    gate_details: dict
    tokens_in_total: int
    tokens_out_total: int
    cost_usd_total: float
    fixtures: list[FixtureResult]

    def to_dict(self) -> dict:
        return {
            "component": self.component,
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "pass_rate": round(self.pass_rate, 4),
            "gate_passed": self.gate_passed,
            "gate_details": self.gate_details,
            "tokens_in_total": self.tokens_in_total,
            "tokens_out_total": self.tokens_out_total,
            "cost_usd_total": round(self.cost_usd_total, 6),
            "fixtures": [f.to_dict() for f in self.fixtures],
        }


# ── carga de fixtures ──────────────────────────────────────────────────────────

def load_fixtures(component: str) -> list[dict]:
    """Carga todos los fixtures JSON de un componente. component ∈ {comment_sentiment, recommendation_engine}."""
    folder = _EVALS_ROOT / component
    if not folder.is_dir():
        return []
    fixtures: list[dict] = []
    for path in sorted(folder.glob("fixture_*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            data["_path"] = str(path)
            fixtures.append(data)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Skipping invalid fixture %s: %s", path, e)
    return fixtures


# ── validación sentiment ──────────────────────────────────────────────────────

def _validate_sentiment_output(fixture: dict, result: LLMCallResult) -> list[str]:
    failures: list[str] = []
    expected = fixture.get("expected") or {}

    if not result.success:
        failures.append(f"llm_call_failed: {result.error}")
        return failures

    payload = result.parsed_json
    if not isinstance(payload, dict):
        failures.append("output_not_dict")
        return failures
    if payload.get("analyzer_output_version") != "1.0":
        failures.append("missing_or_wrong_analyzer_output_version")
    results = payload.get("results")
    if not isinstance(results, list) or not results:
        failures.append("results_missing_or_empty")
        return failures

    # Buscamos el resultado para el comment_id esperado
    expected_id = expected.get("comment_id")
    match = next((r for r in results if r.get("comment_id") == expected_id), None)
    if match is None:
        failures.append(f"no_result_for_comment_id_{expected_id}")
        return failures

    label = (match.get("sentiment_label") or "").lower()
    allowed_labels = [s.lower() for s in expected.get("sentiment_label_one_of") or []]
    if allowed_labels and label not in allowed_labels:
        failures.append(f"sentiment_label_{label}_not_in_{allowed_labels}")

    flags = set((match.get("flags") or []))
    for required in expected.get("flags_required") or []:
        if required not in flags:
            failures.append(f"missing_required_flag_{required}")
    for forbidden in expected.get("flags_forbidden") or []:
        if forbidden in flags:
            failures.append(f"forbidden_flag_present_{forbidden}")

    # Flags fuera del enum cerrado
    valid_enum = {"BLOCKER_MENTIONED", "RISK_SIGNAL", "COMMITMENT_CHANGE"}
    for f in flags:
        if f not in valid_enum:
            failures.append(f"flag_outside_enum_{f}")

    # PII leak en output
    must_not = expected.get("must_not_contain_in_response") or []
    raw_text = result.text
    for token in must_not:
        if token in raw_text:
            failures.append(f"pii_leak_in_response_{token}")

    return failures


# ── validación recommendation ──────────────────────────────────────────────────

def _validate_recommendation_output(fixture: dict, result: LLMCallResult) -> list[str]:
    failures: list[str] = []
    expected = fixture.get("expected") or {}

    if not result.success:
        failures.append(f"llm_call_failed: {result.error}")
        return failures

    payload = result.parsed_json
    if not isinstance(payload, dict):
        failures.append("output_not_dict")
        return failures
    if payload.get("rec_output_version") != "1.0":
        failures.append("missing_or_wrong_rec_output_version")
    if payload.get("advisory_only") is not True:
        failures.append("advisory_only_not_true")

    recs = payload.get("recommendations")
    if not isinstance(recs, list):
        failures.append("recommendations_not_list")
        return failures

    min_count = expected.get("min_recommendations_count")
    if min_count is not None and len(recs) < min_count:
        failures.append(f"too_few_recommendations_{len(recs)}_min_{min_count}")

    max_count = expected.get("max_recommendations_count")
    if max_count is not None and len(recs) > max_count:
        failures.append(f"too_many_recommendations_{len(recs)}_max_{max_count}")

    must_one_of = expected.get("must_contain_category_at_least_one") or []
    if must_one_of:
        categories = {r.get("category") for r in recs if isinstance(r, dict)}
        if not any(c in categories for c in must_one_of):
            failures.append(f"no_recommendation_category_in_{must_one_of}")

    forbidden_priorities = expected.get("must_not_contain_priority") or []
    for r in recs:
        if isinstance(r, dict) and r.get("priority") in forbidden_priorities:
            failures.append(f"forbidden_priority_{r.get('priority')}")

    if expected.get("all_recommendations_must_have_advisory_only"):
        if not all(isinstance(r, dict) and r.get("publish_recommended") is False for r in recs):
            failures.append("some_rec_publish_recommended_not_false")
    if expected.get("all_recommendations_must_have_publish_recommended_false"):
        if not all(isinstance(r, dict) and r.get("publish_recommended") is False for r in recs):
            failures.append("publish_recommended_not_false_in_all")

    # Lenguaje punitivo
    full_text = json.dumps(payload, ensure_ascii=False).lower()
    punitive_keywords = (expected.get("must_not_contain_punitive_keywords") or _PUNITIVE_TERMS)
    for kw in punitive_keywords:
        if kw.lower() in full_text:
            failures.append(f"punitive_keyword_present_{kw}")

    # Métricas inventadas
    forbidden_numbers = expected.get("rationale_must_not_contain_invented_numbers_outside") or []
    for num in forbidden_numbers:
        pattern = rf"\b{re.escape(str(num))}\b"
        for r in recs:
            if not isinstance(r, dict):
                continue
            rationale = (r.get("rationale") or "")
            if re.search(pattern, rationale):
                failures.append(f"invented_metric_{num}_in_rationale")

    return failures


# ── ejecución de un fixture ───────────────────────────────────────────────────

def _run_sentiment_fixture(fixture: dict, model: str) -> FixtureResult:
    spec = LLMCallSpec(
        project="evals",
        agent_kind="sentiment",
        prompt_type="comment_sentiment_v1",
        model=model,
        system=SENTIMENT_SYSTEM_V1,
        user=build_sentiment_user(
            project=(fixture["input"].get("context") or {}).get("project", "evals"),
            sprint_name=(fixture["input"].get("context") or {}).get("sprint_name", "eval"),
            comments=fixture["input"].get("comments") or [],
        ),
        max_output_tokens=512,
        temperature=0.0,
        fixture_id=fixture.get("fixture_id"),
        expect_json=True,
    )
    result = call_llm(spec)
    failures = _validate_sentiment_output(fixture, result)
    return FixtureResult(
        fixture_id=fixture.get("fixture_id", "unknown"),
        type=fixture.get("type", "comment_sentiment"),
        description=fixture.get("description", ""),
        success=result.success,
        passed=(not failures),
        failures=failures,
        tokens_in=result.tokens_in,
        tokens_out=result.tokens_out,
        cost_usd=result.cost_usd,
        latency_ms=result.latency_ms,
        model=result.model,
        usage_id=result.usage_id,
    )


def _run_recommendation_fixture(fixture: dict, model: str) -> FixtureResult:
    spec = LLMCallSpec(
        project="evals",
        agent_kind="recommendation",
        prompt_type="rec_engine_v1",
        model=model,
        system=RECOMMENDATION_SYSTEM_V1,
        user=build_recommendation_user(fixture.get("input") or {}),
        max_output_tokens=1024,
        temperature=0.0,
        fixture_id=fixture.get("fixture_id"),
        expect_json=True,
    )
    result = call_llm(spec)
    failures = _validate_recommendation_output(fixture, result)
    return FixtureResult(
        fixture_id=fixture.get("fixture_id", "unknown"),
        type=fixture.get("type", "recommendation_engine"),
        description=fixture.get("description", ""),
        success=result.success,
        passed=(not failures),
        failures=failures,
        tokens_in=result.tokens_in,
        tokens_out=result.tokens_out,
        cost_usd=result.cost_usd,
        latency_ms=result.latency_ms,
        model=result.model,
        usage_id=result.usage_id,
    )


# ── orquestador público ───────────────────────────────────────────────────────

_KNOWN_COMPONENTS = {"comment_sentiment", "recommendation_engine"}


def run_evals(
    *,
    component: str,
    model: str = "claude-haiku-4-5",
    only_fixture_ids: Iterable[str] | None = None,
) -> EvalReport:
    """Ejecuta evals de un componente. Devuelve report completo.

    component: "comment_sentiment" | "recommendation_engine"
    """
    if component not in _KNOWN_COMPONENTS:
        raise ValueError(f"componente desconocido: {component}")
    fixtures = load_fixtures(component)
    if only_fixture_ids:
        wanted = set(only_fixture_ids)
        fixtures = [f for f in fixtures if f.get("fixture_id") in wanted]

    results: list[FixtureResult] = []
    for fx in fixtures:
        if component == "comment_sentiment":
            results.append(_run_sentiment_fixture(fx, model))
        elif component == "recommendation_engine":
            results.append(_run_recommendation_fixture(fx, model))
        else:
            raise ValueError(f"componente desconocido: {component}")

    total = len(results)
    passed = sum(1 for r in results if r.passed)
    failed = total - passed
    pass_rate = (passed / total) if total else 0.0
    tokens_in = sum(r.tokens_in for r in results)
    tokens_out = sum(r.tokens_out for r in results)
    cost = sum(r.cost_usd for r in results)

    gate_passed, gate_details = _evaluate_gate(component, results)

    return EvalReport(
        component=component,
        total=total,
        passed=passed,
        failed=failed,
        pass_rate=pass_rate,
        gate_passed=gate_passed,
        gate_details=gate_details,
        tokens_in_total=tokens_in,
        tokens_out_total=tokens_out,
        cost_usd_total=cost,
        fixtures=results,
    )


def _evaluate_gate(component: str, results: list[FixtureResult]) -> tuple[bool, dict]:
    if not results:
        return False, {"reason": "no_fixtures_found"}

    total = len(results)
    pass_rate = sum(1 for r in results if r.passed) / total
    pii_leaks = sum(
        1 for r in results
        if any("pii_leak" in f for f in r.failures)
    )
    pii_rate = pii_leaks / total

    if component == "comment_sentiment":
        # Recall sobre fixtures cuyo expected exige BLOCKER_MENTIONED
        blocker_fixtures = [r for r in results if any("missing_required_flag_BLOCKER_MENTIONED" in f for f in r.failures) or r.passed]
        # Más simple: éxito sobre los fixtures que requieren ese flag
        blocker_total = sum(1 for r in results if r.fixture_id == "sentiment_blocker_comment")
        blocker_hit = sum(1 for r in results if r.fixture_id == "sentiment_blocker_comment" and r.passed)
        blocker_recall = (blocker_hit / blocker_total) if blocker_total else 1.0

        gate = SENTIMENT_GATE
        ok = (
            pass_rate >= gate["min_label_precision"]
            and blocker_recall >= gate["min_blocker_recall"]
            and pii_rate <= gate["max_pii_leak_rate"]
        )
        return ok, {
            "component": component,
            "pass_rate": round(pass_rate, 4),
            "blocker_recall": round(blocker_recall, 4),
            "pii_leak_rate": round(pii_rate, 4),
            "thresholds": gate,
        }

    if component == "recommendation_engine":
        gate = RECOMMENDATION_GATE
        punitive_leaks = sum(
            1 for r in results
            if any("punitive_keyword_present" in f for f in r.failures)
        )
        punitive_rate = punitive_leaks / total
        adv_false = sum(
            1 for r in results
            if any("advisory_only_not_true" in f for f in r.failures)
        )
        adv_rate = 1.0 - (adv_false / total)
        publish_false_fail = sum(
            1 for r in results
            if any("publish_recommended_not_false_in_all" in f or "some_rec_publish_recommended_not_false" in f for f in r.failures)
        )
        publish_false_rate = 1.0 - (publish_false_fail / total)
        ok = (
            punitive_rate <= gate["max_punitive_leak_rate"]
            and adv_rate >= gate["min_advisory_only_rate"]
            and publish_false_rate >= gate["min_publish_false_rate"]
        )
        return ok, {
            "component": component,
            "pass_rate": round(pass_rate, 4),
            "punitive_leak_rate": round(punitive_rate, 4),
            "advisory_only_rate": round(adv_rate, 4),
            "publish_false_rate": round(publish_false_rate, 4),
            "thresholds": gate,
        }

    return False, {"reason": f"unknown_component_{component}"}


# ── gate check rápido ─────────────────────────────────────────────────────────

def is_advisory_enabled(component: str, *, model: str = "claude-haiku-4-5") -> bool:
    """Atajo: corre los evals y devuelve solo si pasaron el gate.

    Usado por sentiment_analyzer / recommendation_engine antes de tocar producción.
    """
    report = run_evals(component=component, model=model)
    return report.gate_passed
