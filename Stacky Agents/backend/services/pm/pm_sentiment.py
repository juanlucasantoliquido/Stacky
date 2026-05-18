"""Sentiment Analyzer para PM Intelligence Suite — Fase 2 (advisory).

Toma comentarios indexados de pm_work_item_comments y los enriquece con
sentiment_label / sentiment_score / flags vía LLM.

Gates:
- Solo opera si el eval del componente "comment_sentiment" pasa (gate_passed=True).
- Si el caller fuerza force_unsafe=True, igualmente persiste pero marca advisory_only=true
  en los registros (no hay otro modo en F2).

NO publica nada a ADO. NO usa información PII cruda (los comentarios ya vienen
con pii_masker aplicado al indexarlos).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Iterable

from services.pm.pm_evals import is_advisory_enabled
from services.pm.pm_llm_client import LLMCallSpec, call_llm
from services.pm.pm_prompts import SENTIMENT_SYSTEM_V1, build_sentiment_user

logger = logging.getLogger("stacky_agents.pm.sentiment")


@dataclass
class SentimentAnalysisResult:
    project: str
    requested: int
    analyzed: int
    skipped_already_analyzed: int
    failures: int
    tokens_in: int
    tokens_out: int
    cost_usd: float
    gate_passed: bool
    advisory_only: bool = True

    def to_dict(self) -> dict:
        return {
            "project": self.project,
            "requested": self.requested,
            "analyzed": self.analyzed,
            "skipped_already_analyzed": self.skipped_already_analyzed,
            "failures": self.failures,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "cost_usd": round(self.cost_usd, 6),
            "gate_passed": self.gate_passed,
            "advisory_only": self.advisory_only,
        }


def analyze_sentiment_for_comments(
    *,
    project: str,
    sprint_name: str = "unknown",
    comment_ids: Iterable[int],
    model: str = "claude-haiku-4-5",
    force_unsafe: bool = False,
    skip_gate_check: bool = False,
) -> SentimentAnalysisResult:
    """Enriquece comentarios con sentiment. Bloquea si el eval gate no pasó.

    Args:
        project: proyecto al que pertenecen los comments (para tracking).
        sprint_name: nombre del sprint para contexto del prompt.
        comment_ids: ids de pm_work_item_comments a procesar.
        model: modelo LLM a usar.
        force_unsafe: ignora el gate si True. Solo para testing/debug.
        skip_gate_check: si True, no corre evals (asumir que el caller ya validó).
    """
    from db import session_scope
    from services.pm.models import PmWorkItemComment

    comment_ids = list({int(i) for i in comment_ids})
    if not comment_ids:
        return SentimentAnalysisResult(
            project=project, requested=0, analyzed=0,
            skipped_already_analyzed=0, failures=0,
            tokens_in=0, tokens_out=0, cost_usd=0.0,
            gate_passed=False,
        )

    gate_passed = True
    if not skip_gate_check and not force_unsafe:
        try:
            gate_passed = is_advisory_enabled("comment_sentiment", model=model)
        except Exception as e:  # noqa: BLE001
            logger.warning("pm_sentiment: gate check falló (%s) — bloqueando análisis", e)
            gate_passed = False
        if not gate_passed:
            logger.info("pm_sentiment: eval gate NO pasó — análisis bloqueado")
            return SentimentAnalysisResult(
                project=project, requested=len(comment_ids), analyzed=0,
                skipped_already_analyzed=0, failures=0,
                tokens_in=0, tokens_out=0, cost_usd=0.0,
                gate_passed=False,
            )

    # Levantamos los comments solicitados
    with session_scope() as session:
        rows = (
            session.query(PmWorkItemComment)
            .filter(PmWorkItemComment.id.in_(comment_ids))
            .all()
        )
        # Detach: cargamos todos los campos antes de salir del scope
        to_analyze: list[tuple[int, str]] = []
        skipped = 0
        for r in rows:
            if r.ai_analyzed:
                skipped += 1
                continue
            text = r.text_plain or ""
            # Quitamos el marker `[hash:...]` final para no contaminar el prompt
            if "\n[hash:" in text:
                text = text.split("\n[hash:")[0]
            to_analyze.append((r.id, text))

    if not to_analyze:
        return SentimentAnalysisResult(
            project=project, requested=len(comment_ids), analyzed=0,
            skipped_already_analyzed=skipped, failures=0,
            tokens_in=0, tokens_out=0, cost_usd=0.0,
            gate_passed=gate_passed,
        )

    # Construir comments_block; usamos `id` interno (no ado_id) para correlación 1:1
    spec = LLMCallSpec(
        project=project,
        agent_kind="sentiment",
        prompt_type="comment_sentiment_v1",
        model=model,
        system=SENTIMENT_SYSTEM_V1,
        user=build_sentiment_user(
            project=project,
            sprint_name=sprint_name,
            comments=[{"id": cid, "text_plain": text} for cid, text in to_analyze],
        ),
        max_output_tokens=1024,
        temperature=0.0,
        expect_json=True,
    )

    result = call_llm(spec)
    if not result.success or not isinstance(result.parsed_json, dict):
        logger.warning("pm_sentiment: LLM falló o devolvió JSON inválido: %s", result.error)
        return SentimentAnalysisResult(
            project=project, requested=len(comment_ids),
            analyzed=0, skipped_already_analyzed=skipped,
            failures=len(to_analyze),
            tokens_in=result.tokens_in, tokens_out=result.tokens_out,
            cost_usd=result.cost_usd, gate_passed=gate_passed,
        )

    output = result.parsed_json
    items = output.get("results") or []
    by_id = {int(r.get("comment_id")): r for r in items if isinstance(r, dict) and r.get("comment_id") is not None}

    analyzed = 0
    failures = 0
    with session_scope() as session:
        for cid, _text in to_analyze:
            data = by_id.get(int(cid))
            if not data:
                failures += 1
                continue
            label = str(data.get("sentiment_label") or "").lower()
            if label not in {"positive", "neutral", "negative", "blocking"}:
                failures += 1
                continue
            try:
                score = float(data.get("sentiment_score") or 0)
            except (TypeError, ValueError):
                score = 0.0
            row = session.query(PmWorkItemComment).filter(PmWorkItemComment.id == int(cid)).one_or_none()
            if not row:
                failures += 1
                continue
            row.ai_analyzed = True
            row.sentiment_label = label
            row.sentiment_score = max(0.0, min(1.0, score))
            analyzed += 1

    return SentimentAnalysisResult(
        project=project,
        requested=len(comment_ids),
        analyzed=analyzed,
        skipped_already_analyzed=skipped,
        failures=failures,
        tokens_in=result.tokens_in,
        tokens_out=result.tokens_out,
        cost_usd=result.cost_usd,
        gate_passed=gate_passed,
    )
