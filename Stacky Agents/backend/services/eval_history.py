"""V2.3 (plan 22) — Persistencia e historia de corridas de evals (golden loop).

Convierte los `GoldenResult` de `evals.golden_runner` en filas `EvalRun` para
poder graficar la tendencia de calidad por `agent_type` y correlacionarla con el
`prompt_sha` (V1.1). Lo consume el daemon programado y el endpoint de historia.
"""
from __future__ import annotations

import json
import logging

logger = logging.getLogger("stacky_agents.services.eval_history")


def record_run(agent_type: str, results, *, prompt_sha: str | None = None) -> int | None:
    """Persiste una corrida de goldens. Devuelve el id de la fila (o None si vacía)."""
    results = list(results or [])
    if not results:
        return None

    from db import session_scope
    from models import EvalRun

    passed = sum(1 for r in results if getattr(r, "ok", False))
    failed = len(results) - passed
    scores = [
        {
            "name": getattr(getattr(r, "case", None), "name", "?"),
            "score": getattr(r, "score", None),
            "ok": getattr(r, "ok", False),
        }
        for r in results
    ]
    with session_scope() as session:
        row = EvalRun(
            agent_type=agent_type,
            passed=passed,
            failed=failed,
            scores_json=json.dumps(scores, ensure_ascii=False),
            prompt_sha=prompt_sha,
        )
        session.add(row)
        session.flush()
        return row.id


def list_runs(agent_type: str | None = None, *, limit: int = 50) -> list[dict]:
    """Historia de corridas, más recientes primero. Filtra por agent_type si se da."""
    from db import session_scope
    from models import EvalRun

    with session_scope() as session:
        q = session.query(EvalRun)
        if agent_type:
            q = q.filter(EvalRun.agent_type == agent_type)
        rows = q.order_by(EvalRun.ran_at.desc(), EvalRun.id.desc()).limit(limit).all()
        return [r.to_dict() for r in rows]


def run_and_record_all() -> list[int]:
    """Corre todos los golden sets y persiste una fila por agent_type.

    Usado por el daemon programado (V2.3). Devuelve los ids creados. Best-effort:
    un agent_type que falle al correr no aborta el resto.
    """
    from evals import golden_runner

    created: list[int] = []
    try:
        grouped = golden_runner.run_all()
    except Exception:  # noqa: BLE001
        logger.warning("eval_history: run_all falló", exc_info=True)
        return created

    for agent_type, results in (grouped or {}).items():
        try:
            rid = record_run(agent_type, results)
            if rid is not None:
                created.append(rid)
        except Exception:  # noqa: BLE001
            logger.warning("eval_history: no se pudo registrar '%s'", agent_type, exc_info=True)
    return created


def schedule_evals(interval_hours: float) -> None:
    """Daemon thread que corre `run_and_record_all` cada `interval_hours`.

    `interval_hours <= 0` ⇒ no-op (feature apagada, default). Mismo patrón que el
    reaper de app.py: thread daemon, best-effort, nunca tumba el proceso.
    """
    if not interval_hours or interval_hours <= 0:
        return
    import threading
    import time

    interval_s = max(60.0, float(interval_hours) * 3600.0)

    def _loop() -> None:
        while True:
            time.sleep(interval_s)
            try:
                created = run_and_record_all()
                logger.info("evals programados: %d corridas registradas", len(created))
            except Exception:  # noqa: BLE001
                logger.warning("evals programados: ciclo falló", exc_info=True)

    t = threading.Thread(target=_loop, daemon=True, name="evals-scheduler")
    t.start()
