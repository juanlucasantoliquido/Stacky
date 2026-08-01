"""Plan 279 F7 — Variables faltantes POR NOMBRE. El valor no entra a este modulo.

Regla dura: este archivo NO puede importar secrets_store (resolve_secret_in_payload
:204 / read_secret_from_file :258 devuelven PLAINTEXT). El gate lo verifica por
`ast` en tests/test_pipeline_copilot_secrets.py caso 4.

Lo que este modulo maneja es un HANDLE: el NOMBRE de una variable. Con eso alcanza
para decirle al operador que le falta, y sobra para que ningun valor exista en el
camino del copiloto.
"""
from __future__ import annotations

from services.ci_variables import looks_secret


def _get_provider(project: str):
    """Seam inyectable (los tests lo parchean). Import LAZY a proposito: la
    fabrica resuelve tracker + config, y este modulo tiene que poder importarse
    sin que nada de eso este configurado."""
    from services.ci_variables import get_variables_provider

    return get_variables_provider(project)


def required_variable_names(spec_dict: dict, provider: str, project: str) -> tuple[str, ...]:
    """Nombres de variables que la spec referencia y el proyecto NO define.

    Cruza:
      - services/pipeline_preflight.py:79  referenced_variables(spec_dict, target)
      - services/ci_variables.py:50        CIVariablesProvider.list_variables()  <- SIN valores

    Devuelve NOMBRES ordenados. NUNCA lanza; ante cualquier error devuelve ().
    """
    try:
        if not isinstance(spec_dict, dict):
            return ()
        from services.pipeline_preflight import referenced_variables

        target = "gitlab" if provider == "gitlab" else "ado"
        referenciadas = referenced_variables(spec_dict, target)
        if not referenciadas:
            return ()

        # Las definidas EN LA SPEC no faltan (mismo criterio que
        # check_undefined_variables: spec.variables + jobs[].variables).
        definidas: set[str] = set((spec_dict.get("variables") or {}).keys())
        for stage in spec_dict.get("stages") or []:
            for job in stage.get("jobs") or []:
                definidas |= set((job.get("variables") or {}).keys())

        # Y las que el proyecto ya tiene cargadas. SOLO se lee la key: el dict del
        # puerto es {"key","is_secret","has_value","masked"} — no trae `value`, y
        # aunque un adapter lo agregara, aca nunca se lo mira.
        for fila in (_get_provider(project).list_variables() or []):
            key = fila.get("key") if isinstance(fila, dict) else None
            if isinstance(key, str) and key:
                definidas.add(key)

        return tuple(sorted(n for n in referenciadas if n not in definidas))
    except Exception:
        # Degradacion honesta: si el tracker no responde, el copiloto no puede
        # afirmar que falta nada. Mejor no decir nada que inventar una lista.
        return ()


def secret_names(names: tuple[str, ...]) -> tuple[str, ...]:
    """Subconjunto que parece secreto, por services/ci_variables.py:31 looks_secret(key)
    ("Solo por key, nunca por valor"). NUNCA lanza."""
    try:
        return tuple(n for n in (names or ()) if isinstance(n, str) and looks_secret(n))
    except Exception:  # pragma: no cover - defensa: NUNCA lanza
        return ()
