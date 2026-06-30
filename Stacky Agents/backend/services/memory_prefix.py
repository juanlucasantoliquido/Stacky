"""Plan 54 F0 — Helper compartido de inyección de rejection_lessons.

Función PURA (salvo lectura de env/servicios). Centraliza la inyección de
rejection_lessons para que los 3 runtimes la llamen idéntica.
FA-10 (style_memory) queda copilot-only por herencia del Plan 48 — NO se mueve aquí.
"""
from __future__ import annotations


def build_memory_prefix(
    *,
    project: str | None,
    agent_type: str,
    existing_patterns: set[str] | None = None,
    push_rejections_enabled: bool | None = None,
) -> tuple[str, dict]:
    """NUNCA lanza. Devuelve (prefix_text, meta).

    prefix_text: inyección de rejection_lessons SOLO si flag ON y hay lecciones.
    meta: {"rejection_lessons_count": int, "memory_prefix_error": str?}

    Casos borde (deterministas, en orden):
    1. push_rejections_enabled is None → lee config.STACKY_PUSH_REJECTIONS_ENABLED
       (hot-apply UI efectivo sin reinicio).
    2. flag OFF → prefix="", count=0 (NO llama rejection_lessons).
    3. existing_patterns is None → set().
    4. Excepción en rejection_lessons → prefix="", meta["memory_prefix_error"]=str(exc).
    5. Resultado vacío → prefix_text=="".
    """
    meta: dict = {"rejection_lessons_count": 0}

    # 1. Resolver flag — leer de config para respetar hot-apply de la UI
    if push_rejections_enabled is None:
        try:
            from config import config as _cfg  # noqa: PLC0415
            push_rejections_enabled = _cfg.STACKY_PUSH_REJECTIONS_ENABLED
        except Exception:  # noqa: BLE001
            push_rejections_enabled = False

    # 2. Flag OFF → salir inmediatamente
    if not push_rejections_enabled:
        return "", meta

    # 3. Normalizar patterns existentes
    _existing = existing_patterns if existing_patterns is not None else set()

    # 4. Llamar al servicio con fallback total
    try:
        from services import rejection_lessons  # noqa: PLC0415

        items = rejection_lessons.load_for_run(
            project=project,
            agent_type=agent_type,
            existing_patterns=_existing,
        )
        if not items:
            return "", meta

        prefix_text = rejection_lessons.build_prefix(items)
        meta["rejection_lessons_count"] = len(items)
        return prefix_text, meta

    except Exception as exc:  # noqa: BLE001
        meta["memory_prefix_error"] = str(exc)
        return "", meta
