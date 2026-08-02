"""services/pipeline_project_probe.py — Plan 294 F5. El paso 1 se llena solo.

QUE HACE. COMPONE lo que ya existe y devuelve, en UNA llamada, todo lo que el
paso 1 del asistente muestra: proveedor, repositorio, rama, tecnologia, comandos
sugeridos, nombres de variables y el inventario de pipelines DESCRIPTO.

QUE NO HACE. No barre el repositorio por su cuenta (eso es del plan 246), no
construye ningun cliente de proveedor a mano, no habla por red, no llama a
ningun modelo y no escribe un solo byte. Cero gasto en reposo: todo sale de un
clic del usuario.

REGLA DURA — NUNCA LANZA. Cada bloque va en su propio try/except y su fallo
agrega una entrada a `sources` con `available: False` y un `reason` no vacio:
degradacion VISIBLE. Que falle uno no puede vaciar los otros.
"""
from __future__ import annotations

#: Tope duro de fichas que LEEN el archivo del disco. Sin esto, un repositorio
#: con 200 archivos de pipeline mata el paso 1. OJO: el tope limita la LECTURA,
#: no la ficha: TODAS las entradas pasan por describe_pipeline, y las que no
#: leyeron el archivo salen con purpose_source == "sin_datos", que es el
#: contrato honesto ("no pude determinarlo"), no una afirmacion.
_MAX_DESCRIBED: int = 25

_SRC_CONTEXT = "project_context"
_SRC_STACK = "stack_detect"
_SRC_INVENTORY = "pipeline_inventory"
_SRC_VARIABLES = "ci_variables"

#: Tabla CERRADA por tecnologia. Si no hay senal, cadena vacia. NUNCA se inventa.
_BY_STACK: dict[str, dict[str, str]] = {
    "python": {
        "framework": "",
        "package_manager": "pip",
        "build_command": "pip install -r requirements.txt",
        "test_command": "pytest",
    },
    "node": {
        "framework": "",
        "package_manager": "npm",
        "build_command": "npm run build",
        "test_command": "npm test",
    },
    "dotnet": {
        "framework": ".NET",
        "package_manager": "nuget",
        "build_command": "dotnet build",
        "test_command": "dotnet test",
    },
}


# ── Indirecciones deliberadas ────────────────────────────────────────────────
# Cada dependencia entra por una funcion de modulo. No es ceremonia: es lo que
# permite que un test sustituya UNA pieza sin tocar disco ni proveedor, y lo que
# mantiene este archivo como un COMPOSITOR y no como una reimplementacion.

def _build_inventory(project: str | None, refresh: bool = False) -> dict:
    from services.pipeline_inventory import build_inventory   # noqa: PLC0415

    return build_inventory(project, refresh=refresh)


def _get_pipeline_yaml(key: str):
    from services.pipeline_inventory import get_pipeline_yaml   # noqa: PLC0415

    return get_pipeline_yaml(key)


def _describe(entry: dict, texto):
    from services.pipeline_inventory import describe_pipeline   # noqa: PLC0415

    return describe_pipeline(entry, texto)


def _detect_stack(root: str) -> str | None:
    from services.pipeline_stack_detector import detect_stack   # noqa: PLC0415

    return detect_stack(root)


def _variable_names(project: str | None) -> list[str]:
    """SOLO NOMBRES. Jamas un valor: es el riel R3 / KPI-5."""
    from services.ci_variables import get_variables_provider   # noqa: PLC0415

    proveedor = get_variables_provider(project)
    return [str(v.get("key") or "") for v in proveedor.list_variables() if v.get("key")]


def _workspace_root_str() -> str:
    """C11 — OJO CON LOS TIPOS. `detect_stack` toma `str`; `_active_workspace_root`
    devuelve `Path | None`. Con el workspace ausente, pasarle None a secas revienta.
    """
    from runtime_paths import _active_workspace_root   # noqa: PLC0415

    root = _active_workspace_root()
    return str(root) if root else ""


def _fuente_caida(source_id: str, capability: str, exc: Exception, workaround: str) -> dict:
    from services.pipeline_inventory import source_unavailable   # noqa: PLC0415

    motivo = str(exc).strip() or exc.__class__.__name__
    return source_unavailable(
        source_id,
        capability=capability,
        provider="desconocido",
        reason=motivo[:200],
        workaround=workaround,
    )


def _fuente_ok(source_id: str, count: int) -> dict:
    from services.pipeline_inventory import source_ok   # noqa: PLC0415

    return source_ok(source_id, count)


def _inventario_vacio() -> dict:
    return {"ok": False, "pipelines": [], "sources": [], "counts": {}}


def probe_project(project: str | None = None, *, refresh: bool = False) -> dict:
    """READ-ONLY ABSOLUTO. NUNCA LANZA. Devuelve SIEMPRE el mismo shape de 13 claves."""
    out: dict = {
        "ok": True,
        "project": str(project or ""),
        "provider": "",
        "repository": "",
        "default_branch": "",
        "stack": "",
        "framework": "",
        "package_manager": "",
        "build_command": "",
        "test_command": "",
        "variables": [],
        "inventory": _inventario_vacio(),
        "sources": [],
    }
    fuentes: list[dict] = []

    # ── 1. proveedor / repositorio / rama ────────────────────────────────────
    try:
        from services.project_context import resolve_project_context   # noqa: PLC0415

        ctx = resolve_project_context(project)
        if ctx is not None:
            tracker = (ctx.tracker_type or "").strip().lower()
            out["provider"] = "gitlab" if tracker == "gitlab" else ("ado" if tracker else "")
            out["repository"] = str(ctx.tracker_project or "")
            out["project"] = str(ctx.stacky_project_name or out["project"])
        fuentes.append(_fuente_ok(_SRC_CONTEXT, 1 if ctx is not None else 0))
    except Exception as exc:      # noqa: BLE001 — degrada visible, nunca rompe
        fuentes.append(_fuente_caida(
            _SRC_CONTEXT, "resolve_project_context", exc,
            "Revisa la configuracion del proyecto en Proyectos.",
        ))

    # ── 2. tecnologia y comandos sugeridos ───────────────────────────────────
    try:
        raiz = _workspace_root_str()
        stack = (_detect_stack(raiz) or "") if raiz else ""
        out["stack"] = stack
        sugerido = _BY_STACK.get(stack, {})
        out["framework"] = sugerido.get("framework", "")
        out["package_manager"] = sugerido.get("package_manager", "")
        out["build_command"] = sugerido.get("build_command", "")
        out["test_command"] = sugerido.get("test_command", "")
        fuentes.append(_fuente_ok(_SRC_STACK, 1 if stack else 0))
    except Exception as exc:      # noqa: BLE001
        fuentes.append(_fuente_caida(
            _SRC_STACK, "detect_stack", exc,
            "Abri el repositorio del proyecto como espacio de trabajo activo.",
        ))

    # ── 3. nombres de variables (JAMAS valores) ──────────────────────────────
    try:
        nombres = [n for n in _variable_names(project) if n]
        out["variables"] = nombres
        fuentes.append(_fuente_ok(_SRC_VARIABLES, len(nombres)))
    except Exception as exc:      # noqa: BLE001
        fuentes.append(_fuente_caida(
            _SRC_VARIABLES, "list_variables", exc,
            "Cargá el acceso al proveedor en Configuracion para ver los nombres.",
        ))

    # ── 4. inventario DESCRIPTO ──────────────────────────────────────────────
    try:
        payload = dict(_build_inventory(project, refresh) or {})
        entradas = list(payload.get("pipelines") or [])
        descriptas: list[dict] = []
        for i, entry in enumerate(entradas):
            texto = None
            if i < _MAX_DESCRIBED:
                try:
                    texto, _ = _get_pipeline_yaml(entry.get("key") or "")
                except Exception:      # noqa: BLE001 — sin archivo legible: sin ficha
                    texto = None
            descriptas.append(_describe(entry, texto))   # TODAS pasan por aca
        payload["pipelines"] = descriptas
        out["inventory"] = payload
        fuentes.extend(list(payload.get("sources") or []))
        fuentes.append(_fuente_ok(_SRC_INVENTORY, len(descriptas)))
    except Exception as exc:      # noqa: BLE001
        out["inventory"] = _inventario_vacio()
        fuentes.append(_fuente_caida(
            _SRC_INVENTORY, "build_inventory", exc,
            "Revisa el acceso al proveedor o volve a intentar en unos minutos.",
        ))

    out["sources"] = fuentes
    return out
