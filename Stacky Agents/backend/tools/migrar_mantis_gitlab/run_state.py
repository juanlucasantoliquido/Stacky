"""tools/migrar_mantis_gitlab/run_state.py — Plan 217 Batch 4, F5a (§11).

Checkpoint de progreso de una corrida `execute`/`resume`: solo un
ACELERADOR/hint informativo, NO la fuente de verdad de idempotencia (esa la
da el mapeo persistido `mantis_gitlab_map`, ver `migrator_mg_executor.py`).

Escritura atómica: se escribe a `{path}.tmp` (en el MISMO directorio que el
destino final, para que `os.replace` sea atómico incluso si `path` está en
un filesystem distinto al del directorio temporal del sistema) y se
reemplaza con `os.replace`, atómico tanto en POSIX como en NTFS — así un
`kill -9` a mitad de la escritura (§17 del plan: "matar el proceso a mitad
de camino") nunca deja un checkpoint corrupto/truncado: o queda el anterior
completo, o queda el nuevo completo.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Optional


def save_checkpoint(
    path: str,
    *,
    last_mantis_issue_id: str,
    run_id: str,
    extra: Optional[dict] = None,
) -> None:
    """Persiste `{last_mantis_issue_id, run_id, extra}` como JSON, de forma
    atómica (tmp + os.replace). Crea el directorio padre si no existe."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "last_mantis_issue_id": str(last_mantis_issue_id),
        "run_id": run_id,
        "extra": extra or {},
    }

    fd, tmp_path = tempfile.mkstemp(
        prefix=f"{target.name}.", suffix=".tmp", dir=str(target.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, sort_keys=True)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_path, str(target))
    except BaseException:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def load_checkpoint(path: str) -> Optional[dict]:
    """Devuelve el checkpoint deserializado, o `None` si el archivo no
    existe (primera corrida, o checkpoint nunca guardado)."""
    target = Path(path)
    if not target.exists():
        return None
    with open(target, "r", encoding="utf-8") as fh:
        return json.load(fh)


__all__ = ["load_checkpoint", "save_checkpoint"]
