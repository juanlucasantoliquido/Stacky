"""tests/test_plan218_serie_integridad.py -- Plan 218 F7.

El catálogo de la serie 218..236 como ARTEFACTO DE DATOS validado: orden,
dependencias y propiedad de archivos dejan de depender de la memoria de nadie.
Es lo que convierte al documento 218 en un orquestador y no en una lista de deseos.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

_STACKY = _BACKEND.parent
_DOCS = _STACKY / "docs"

from services.parity_series import (  # noqa: E402
    ESTADOS_REALES_VALIDOS,
    load_estado_real,
    load_series,
    topological_order,
    validate_series,
)
from services.provider_capabilities import (  # noqa: E402
    CAPABILITY_KEYS,
    capability_status,
)
from tests.contract.known_gaps import KNOWN_GAPS  # noqa: E402

# Capacidades no-full que NINGÚN subplan de esta serie toma. Vacía a propósito:
# si algún día una capacidad queda huérfana, o se le asigna dueño o se declara acá
# con motivo. Nunca se ignora en silencio.
FUERA_DE_SCOPE_218: frozenset[str] = frozenset()


@pytest.fixture(scope="module")
def series():
    return load_series()


def test_numeros_unicos_y_consecutivos(series):
    numeros = sorted(int(s["number"]) for s in series["subplans"])
    assert len(numeros) == len(set(numeros))
    assert numeros == list(range(218, 237)), (
        "la serie debe cubrir 218..236 sin huecos, INCLUIDO el orquestador (C11)"
    )


def test_toda_dependencia_existe(series):
    violaciones = [v for v in validate_series(series) if "depende de" in v]
    assert violaciones == [], violaciones


def test_sin_ciclos(series):
    orden = topological_order(series)
    assert len(orden) == len(series["subplans"])
    posicion = {n: i for i, n in enumerate(orden)}
    for s in series["subplans"]:
        for dep in s.get("depends_on", []):
            assert posicion[int(dep)] < posicion[int(s["number"])]


def test_sin_colision_de_propiedad(series):
    """Ningún archivo aparece en owns_files de dos entradas, INCLUIDA la 218.

    C11: F8 edita frontend/src/pages/DiagnosticsPage.tsx, que ningún subplan
    reclamaba y que el 232 podía tomar sin conflicto detectado.
    """
    violaciones = [v for v in validate_series(series) if "colisión de propiedad" in v]
    assert violaciones == [], violaciones


def test_toda_capacidad_declarada_existe(series):
    desconocidas = []
    for s in series["subplans"]:
        for cap in s.get("capabilities", []):
            if cap not in CAPABILITY_KEYS:
                desconocidas.append(f"{s['number']}: {cap}")
    assert desconocidas == [], desconocidas


def test_known_gaps_tiene_dueno_en_la_serie(series):
    """Cierra el lazo del ratchet inverso: un gap sin dueño en el catálogo = rojo."""
    porn = {int(s["number"]): s for s in series["subplans"]}
    problemas = []
    for (provider, capability), valor in KNOWN_GAPS.items():
        dueno = int(valor["owner_plan"])
        if dueno not in porn:
            problemas.append(f"{provider}/{capability}: dueño {dueno} no está en la serie")
            continue
        if capability not in porn[dueno].get("capabilities", []):
            problemas.append(
                f"{provider}/{capability}: el subplan {dueno} no declara esa capacidad"
            )
    assert problemas == [], problemas


def test_estado_real_de_planes_previos_esta_verificado():
    """C12: cada símbolo declarado como evidencia EXISTE de verdad en su archivo."""
    data = load_estado_real()
    assert data["planes"], "el registro de estado real está vacío"

    problemas = []
    for entrada in data["planes"]:
        assert entrada["estado_real"] in ESTADOS_REALES_VALIDOS, entrada
        if entrada["estado_real"] == "NO_IMPLEMENTADO":
            continue
        assert entrada["evidencia"], f"plan {entrada['plan']}: sin evidencia"
        for ev in entrada["evidencia"]:
            archivo = _STACKY / ev["file"]
            if not archivo.exists():
                problemas.append(f"plan {entrada['plan']}: no existe {ev['file']}")
                continue
            if ev["symbol"] not in archivo.read_text(encoding="utf-8"):
                problemas.append(
                    f"plan {entrada['plan']}: {ev['symbol']!r} no aparece en {ev['file']}"
                )
    assert problemas == [], problemas


def test_toda_capacidad_no_full_tiene_dueño(series):
    """Hace IMPOSIBLE olvidarse de un gap."""
    declaradas = set()
    for s in series["subplans"]:
        declaradas.update(s.get("capabilities", []))

    huerfanas = []
    for key in CAPABILITY_KEYS:
        estados = {capability_status(p, key) for p in ("azure_devops", "gitlab")}
        if not (estados & {"absent", "partial"}):
            continue
        if key in declaradas or key in FUERA_DE_SCOPE_218:
            continue
        huerfanas.append(key)

    assert huerfanas == [], (
        "capacidades sin paridad y sin subplan dueño (asignalas o declaralas en "
        f"FUERA_DE_SCOPE_218 con motivo): {huerfanas}"
    )


def test_prioridad_y_hito_validos(series):
    violaciones = [
        v for v in validate_series(series)
        if "prioridad inválida" in v or "hito inexistente" in v
    ]
    assert violaciones == [], violaciones

    declarados = set()
    for m in series["milestones"]:
        declarados.update(int(p) for p in m["plans"])
    numeros = {int(s["number"]) for s in series["subplans"]}
    assert declarados == numeros, (
        f"milestones y subplans no coinciden: solo en milestones={declarados - numeros}, "
        f"solo en subplans={numeros - declarados}"
    )


def test_docs_existentes_coinciden(series):
    patron = re.compile(r"^[A-Z0-9_]+$")
    problemas = []
    for s in series["subplans"]:
        numero = int(s["number"])
        assert patron.match(s["slug"]), f"{numero}: slug inválido {s['slug']!r}"
        assert s.get("acceptance", "").strip(), f"{numero}: sin criterio de aceptación"
        for doc in _DOCS.glob(f"{numero}_PLAN_*.md"):
            esperado = f"{numero}_PLAN_{s['slug']}"
            if not doc.stem.startswith(esperado):
                problemas.append(f"{doc.name} no empieza con {esperado}")
    assert problemas == [], problemas
