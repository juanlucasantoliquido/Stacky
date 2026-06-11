"""H6.1 — Harvest: convierte una AgentExecution real en un golden case.

Uso programático:
    from evals.harvest import harvest
    harvest(execution_id=42, name="mi_golden")

Uso CLI (via __main__):
    python -m evals harvest <execution_id> [--name <caso>]

El archivo se escribe en:
    evals/agents/<agent_type>/<name>.json

El output se limpia con PII mask irreversible antes de persistir.
El min_score del golden es el score actual del contrato (floor → int).
"""
from __future__ import annotations

import json
import math
from pathlib import Path

_DEFAULT_AGENTS_DIR = Path(__file__).resolve().parent / "agents"


class HarvestError(Exception):
    """Error de harvest con mensaje legible (no traza)."""


def harvest(
    execution_id: int,
    *,
    name: str | None = None,
    agents_dir: Path | None = None,
) -> Path:
    """Crea un golden case a partir de una AgentExecution completada.

    Parámetros
    ----------
    execution_id : int
        ID de la AgentExecution a convertir en golden.
    name : str | None
        Nombre del caso (sin extensión). Si es None, usa ``execution_<id>``.
    agents_dir : Path | None
        Directorio raíz de goldens. Por defecto ``evals/agents/``.
        Útil para tests (tmp_path).

    Retorna
    -------
    Path
        Ruta del archivo JSON creado.

    Lanza
    -----
    HarvestError
        Si la ejecución no existe, no está completada o no tiene output.
    """
    from db import session_scope
    from models import AgentExecution
    import contract_validator
    from services.pii_masker import redact_irreversible

    # 1. Cargar execution
    try:
        with session_scope() as session:
            exec_row = session.get(AgentExecution, execution_id)
            if exec_row is None:
                raise HarvestError(
                    f"Execution #{execution_id} no encontrada. "
                    "Verificá el id con la DB."
                )
            if exec_row.status != "completed":
                raise HarvestError(
                    f"Execution #{execution_id} no está completada "
                    f"(status='{exec_row.status}'). Solo se pueden harvestear "
                    "ejecuciones con status='completed'."
                )
            if not exec_row.output:
                raise HarvestError(
                    f"Execution #{execution_id} no tiene output registrado. "
                    "No se puede crear un golden sin output."
                )
            agent_type: str = exec_row.agent_type
            raw_output: str = exec_row.output
    except HarvestError:
        raise
    except Exception as exc:
        # Truncar mensajes de error de SQLAlchemy para no mostrar SQL en el CLI
        short = str(exc).split("\n")[0][:200]
        raise HarvestError(
            f"Error al acceder a la DB para execution #{execution_id}: {short}. "
            "Verificá DATABASE_URL y que la DB esté inicializada."
        ) from exc

    # 2. PII mask irreversible
    clean_output = redact_irreversible(raw_output)

    # 3. Score actual
    result = contract_validator.validate(agent_type, clean_output)
    min_score = math.floor(result.score)

    # 4. Nombre del caso
    case_name = name or f"execution_{execution_id}"

    # 5. Construir payload golden (formato exacto del golden_runner)
    payload = {
        "name": case_name,
        "agent_type": agent_type,
        "output": clean_output,
        "expect": {
            "min_score": min_score,
            "must_pass": True,
        },
    }

    # 6. Escribir archivo
    base_dir = agents_dir or _DEFAULT_AGENTS_DIR
    type_dir = base_dir / agent_type
    type_dir.mkdir(parents=True, exist_ok=True)
    out_file = type_dir / f"{case_name}.json"
    out_file.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return out_file
