"""A1.2 — Guard de independencia del contrato (inmutabilidad).

Garantiza que los artefactos generados_test del contrato no sean modificados
por el agente durante el run, preservando la integridad del examen.

API pública:
    check_integrity(checks, workspace) -> dict
        Compara hashes de archivos materialzados vs hashes originales.
        Si detecta mutación: restaura el original + marca mutated_checks.

Diseño:
- Solo actúa sobre kind=generated_test (comandos/schemas no tienen archivo en el árbol)
- Los artefactos se materializan en subdir temporal de solo-arnés (_ac_harness_/)
- Si el agente modifica un _ac_gate_*.py → detectado por sha256 → restaurado
- Flag OFF → no-op, byte-idéntico
- Metadata: "mutated_checks", "restored"
"""
from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger("stacky.acceptance_integrity")

# Directorio de solo-arnés dentro del workspace
_HARNESS_SUBDIR = "_ac_harness_"


# ── Funciones de hash (mockables en tests) ────────────────────────────────────

def _get_file_hash(path: str) -> str | None:
    """Calcula el sha256 de un archivo. None si no existe."""
    p = Path(path)
    if not p.exists():
        return None
    try:
        content = p.read_bytes()
        return hashlib.sha256(content).hexdigest()
    except Exception:  # noqa: BLE001
        return None


def _get_stored_hash(path: str) -> str | None:
    """Obtiene el hash almacenado del artefacto original.

    El hash se guarda al materializar el artefacto en un .hash sidecar.
    """
    hash_path = Path(path + ".hash")
    if not hash_path.exists():
        return None
    try:
        return hash_path.read_text(encoding="utf-8").strip()
    except Exception:  # noqa: BLE001
        return None


def _restore_file(path: str, original_content: str) -> None:
    """Restaura el archivo al contenido original del contrato."""
    try:
        Path(path).write_text(original_content, encoding="utf-8")
        logger.info("acceptance_integrity: restaurado %s", path)
    except Exception as exc:  # noqa: BLE001
        logger.warning("acceptance_integrity: no se pudo restaurar %s: %s", path, exc)


# ── API pública ───────────────────────────────────────────────────────────────

def check_integrity(checks: list[dict], workspace: str) -> dict:
    """Verifica que ningún generated_test del contrato fue modificado por el agente.

    Si detecta mutación: restaura el archivo original.

    Args:
        checks: lista de chequeos del contrato (con opcionalmente _tmp_path)
        workspace: directorio de trabajo del agente

    Returns dict:
        mutated_checks: lista de artefactos que fueron mutados (y restaurados)
        restored: True si al menos un archivo fue restaurado
    """
    try:
        from config import config as _cfg
        enabled = getattr(_cfg, "STACKY_ACCEPTANCE_INTEGRITY_ENABLED", False)
    except Exception:
        enabled = False

    if not enabled:
        return {"mutated_checks": [], "restored": False}

    mutated: list[str] = []
    any_restored = False

    for check in checks:
        kind = check.get("kind", "command")
        if kind != "generated_test":
            continue  # solo generated_test tiene archivo en el árbol

        artifact = check.get("artifact", "")
        tmp_path = check.get("_tmp_path")

        if not tmp_path:
            # Si no hay _tmp_path registrado, no podemos verificar
            continue

        current_hash = _get_file_hash(tmp_path)
        stored_hash = _get_stored_hash(tmp_path)

        if current_hash is None or stored_hash is None:
            # Archivo no existe o no hay hash guardado → skip
            continue

        if current_hash != stored_hash:
            logger.warning(
                "acceptance_integrity: generado_test mutado por el agente: %s (hash %s→%s)",
                tmp_path, stored_hash[:8], current_hash[:8],
            )
            mutated.append(artifact[:80])
            # Restaurar al original
            _restore_file(tmp_path, artifact)
            any_restored = True

    return {"mutated_checks": mutated, "restored": any_restored}


def materialize_checks(checks: list[dict], workspace: str) -> list[dict]:
    """Materializa los generated_test en el subdir de solo-arnés.

    Guarda un .hash sidecar para detectar mutaciones posteriores.
    Actualiza cada check con _tmp_path para uso en check_integrity().

    Args:
        checks: lista de chequeos del contrato
        workspace: directorio de trabajo del agente

    Returns: nueva lista de checks con _tmp_path añadido donde aplique
    """
    harness_dir = Path(workspace) / _HARNESS_SUBDIR
    try:
        harness_dir.mkdir(parents=True, exist_ok=True)
    except Exception as exc:  # noqa: BLE001
        logger.warning("acceptance_integrity: no se pudo crear harness dir: %s", exc)
        return checks

    result = []
    for i, check in enumerate(checks):
        kind = check.get("kind", "command")
        if kind != "generated_test":
            result.append(check)
            continue

        artifact = check.get("artifact", "")
        suffix = ".py"
        tmp_path = str(harness_dir / f"_ac_contract_{i}{suffix}")

        try:
            Path(tmp_path).write_text(artifact, encoding="utf-8")
            content_hash = hashlib.sha256(artifact.encode("utf-8")).hexdigest()
            Path(tmp_path + ".hash").write_text(content_hash, encoding="utf-8")
            result.append({**check, "_tmp_path": tmp_path})
        except Exception as exc:  # noqa: BLE001
            logger.warning("acceptance_integrity: no se pudo materializar check %d: %s", i, exc)
            result.append(check)

    return result
