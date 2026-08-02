"""Plan 294 F0 — Censo ejecutable: congelar lo que YA existe.

POR QUE EXISTE. Este plan construye muy poco codigo nuevo de dominio: el
inventario de pipelines (plan 246), el perfilador (247), el disparo (72/95), la
maquina de estados (279) y el renderizador de YAML YA ESTAN CONSTRUIDOS. El
riesgo numero uno es que un implementador los reescriba. Este archivo es la
mitad de contraste del plan: tres casos NACEN ROJOS (6, 7 y 8) y los otros ocho
congelan lo que no se toca.

CRITERIO AL CREAR F0: 8 passed, 3 failed.
CRITERIO AL CERRAR F2:  11 passed, 0 failed.
Si al crearlo da 11 passed, el test no prueba nada.
"""
from __future__ import annotations

import pathlib
import re

_BACKEND = pathlib.Path(__file__).resolve().parents[1]
_STACKY = _BACKEND.parent
_FRONTEND = _STACKY / "frontend"


# ---------------------------------------------------------------- 1..5, 9..11
# Casos que NACEN VERDES: congelan capacidades que ya existen.


def test_inventario_ya_existe():
    """Plan 246. Si esto falla, alguien movio o reescribio el inventario."""
    from services.pipeline_inventory import (  # noqa: PLC0415
        CATEGORIES,
        build_inventory,
        identity_key,
        make_entry,
        reconcile,
        scan_repo_pipelines,
    )

    assert callable(build_inventory)
    assert callable(reconcile)
    assert callable(scan_repo_pipelines)
    assert callable(identity_key)
    assert callable(make_entry)
    assert len(CATEGORIES) == 4, f"las 4 categorias de reconciliacion: {CATEGORIES}"


def test_trigger_ya_existe():
    """Plan 72/95. El puerto CI declara trigger_pipeline; no se reimplementa."""
    from services.ci_provider import CI_PORT_METHODS  # noqa: PLC0415

    assert "trigger_pipeline" in CI_PORT_METHODS


def test_perfilador_ya_existe():
    """Plan 247. La frase en castellano determinista ya esta construida."""
    from services.pipeline_profiler import (  # noqa: PLC0415
        build_purpose_template,
        detect_artifacts,
        detect_phases,
        detect_triggers,
    )

    assert callable(build_purpose_template)
    assert callable(detect_phases)
    assert callable(detect_triggers)
    assert callable(detect_artifacts)


def test_maquina_de_estados_ya_existe():
    """Plan 279. El wizard REUSA esta maquina; no escribe otra."""
    from services.pipeline_session import (  # noqa: PLC0415
        PIPELINE_SESSION_STATES,
        TRANSITIONS,
        advance,
    )

    assert len(PIPELINE_SESSION_STATES) == 8
    assert callable(advance)
    assert set(TRANSITIONS) == set(PIPELINE_SESSION_STATES)


def test_escritor_de_repo_ya_existe_en_los_dos_proveedores():
    """La paridad ADO/GitLab de ESCRITURA ya esta resuelta. No se reimplementa."""
    for modulo in ("ado_provider.py", "gitlab_provider.py"):
        texto = (_BACKEND / "services" / modulo).read_text(encoding="utf-8")
        assert "def commit_file" in texto, f"{modulo} perdio commit_file"


def test_no_hay_segundo_renderizador():
    """Guarda anti-duplicacion permanente: un solo motor de YAML."""
    archivos = [
        p.name
        for p in sorted((_BACKEND / "services").glob("*.py"))
        if "def to_ado_yaml" in p.read_text(encoding="utf-8")
    ]
    assert archivos == ["pipeline_renderers.py"], (
        f"hay mas de un renderizador de YAML de pipelines: {archivos}"
    )


def test_los_cuatro_montajes_del_trigger_siguen_ahi():
    """C1 — el v1 del plan afirmaba que habia UN solo montaje. Son CUATRO.

    Este caso impide que alguien 'consolide' el disparo creyendo el dato viejo y
    rompa tres superficies vivas.
    """
    montajes = (
        "src/components/devops/PipelineBuilderSection.tsx",
        "src/components/devops/EnvironmentsSection.tsx",
        "src/components/devops/ProductionFlow.tsx",
        "src/components/devops/PublicationsSection.tsx",
    )
    faltan = [
        rel
        for rel in montajes
        if "<TriggerPipelineSection" not in (_FRONTEND / rel).read_text(encoding="utf-8")
    ]
    assert faltan == [], f"se perdio el montaje de TriggerPipelineSection en: {faltan}"


def test_exports_reales_del_modelo_del_copiloto():
    """C2 — STATE_LABELS y AVAILABLE_BY_STATE son const PRIVADAS del modulo.

    Importarlas rompe tsc. Lo exportado son stateLabel() y availableActionIds().
    Si alguien las exporta para 'arreglar' un import, este caso se pone rojo y
    obliga a discutirlo en vez de ampliar la superficie publica del plan 279.
    """
    texto = (
        _FRONTEND / "src" / "components" / "devops" / "pipelineCopilotModel.ts"
    ).read_text(encoding="utf-8")

    for presente in (
        "export const SESSION_STATES",
        "export function stateLabel",
        "export function availableActionIds",
        "export const COPILOT_RUNTIMES",
    ):
        assert presente in texto, f"falta el export real: {presente}"

    for ausente in ("export const STATE_LABELS", "export const AVAILABLE_BY_STATE"):
        assert ausente not in texto, (
            f"{ausente} paso a ser publico: eso es alcance del plan 279, no del 294"
        )


# ------------------------------------------------------------------ 6, 7 y 8
# Casos que NACEN ROJOS. Son la mitad de contraste de F2 (6) y F1 (7 y 8).


def test_get_pipeline_yaml_falta():
    """NACE ROJO. Contraste de F2 (GAP-6: bug vivo, el perfilador da 501 siempre).

    C18: el import va DENTRO del cuerpo. A nivel de modulo pytest reporta error
    de coleccion y NINGUN otro caso del archivo corre.
    """
    from services.pipeline_inventory import get_pipeline_yaml  # noqa: PLC0415

    assert callable(get_pipeline_yaml)


def test_flags_294_registradas():
    """NACE ROJO. Contraste de F1."""
    from services.harness_flags import FLAG_REGISTRY  # noqa: PLC0415

    keys = {s.key for s in FLAG_REGISTRY}
    esperadas = {
        "STACKY_PIPELINE_WIZARD_ENABLED",
        "STACKY_PIPELINE_WIZARD_COMMIT_ENABLED",
        "STACKY_PIPELINE_TRIGGER_VARS_ENABLED",
    }
    assert esperadas <= keys, f"faltan en FLAG_REGISTRY: {sorted(esperadas - keys)}"


def test_docstring_de_ci_no_miente():
    """NACE ROJO. Contraste de F1.

    El docstring de api/ci.py dice 'default OFF' desde antes de que el operador
    encendiera la flag el 2026-07-05. El default efectivo vive en config.py y es
    "true". Al corregirlo NO se puede escribir esa cadena en ningun comentario
    nuevo del archivo: este caso la grepea.
    """
    texto = (_BACKEND / "api" / "ci.py").read_text(encoding="utf-8")
    assert "default OFF" not in texto, (
        "api/ci.py sigue afirmando 'default OFF' sobre STACKY_PIPELINE_TRIGGER_ENABLED; "
        "el default efectivo es ON (config.py, decision del operador 2026-07-05)"
    )
    # el regex existe para dejar constancia de que se mira el docstring de modulo
    assert re.search(r"STACKY_PIPELINE_TRIGGER_ENABLED", texto)
