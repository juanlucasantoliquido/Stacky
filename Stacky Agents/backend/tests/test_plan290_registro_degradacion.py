"""Plan 290 F1 — el registro de degradacion: bordes, dedup y el riel "nunca levanta".

NO importa db: la sesion se inyecta por `session_factory`, igual que
tests/test_plan289_stat_de_contexto.py.
"""
from __future__ import annotations

import contextlib
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ARGS = {
    "capability": "tracker.comments.list",
    "reason": "tracker no-ADO: sin cross-check de comentarios",
    "provider": "gitlab",
    "site": "business_preflight._evaluate_functional",
}


class _FilaFalsa:
    def __init__(self, md=None):
        self.metadata_dict = md if md is not None else {}


class _SesionFalsa:
    def __init__(self, fila):
        self._fila = fila
        self.gets = []

    def get(self, modelo, pk):
        self.gets.append((modelo, pk))
        return self._fila


def _factory(fila):
    @contextlib.contextmanager
    def _f():
        yield _SesionFalsa(fila)

    return _f


def _entradas(fila):
    from services.capability_degradation import CLAVE_METADATA

    return fila.metadata_dict.get(CLAVE_METADATA) or []


# ── Bordes ───────────────────────────────────────────────────────────────────

def test_execution_id_none_no_escribe_ni_levanta():
    """api/agents.py:542 evalua ANTES de que exista la fila: no hay destino."""
    from services.capability_degradation import declarar

    fila = _FilaFalsa()
    assert declarar(execution_id=None, session_factory=_factory(fila), **ARGS) is False
    assert fila.metadata_dict == {}


def test_fila_inexistente_no_escribe_ni_levanta():
    from services.capability_degradation import declarar

    @contextlib.contextmanager
    def _sin_fila():
        yield types.SimpleNamespace(get=lambda *a, **k: None)

    assert declarar(execution_id=999, session_factory=_sin_fila, **ARGS) is False


def test_metadata_dict_none_se_trata_como_dict_vacio():
    from services.capability_degradation import declarar

    fila = _FilaFalsa()
    fila.metadata_dict = None
    assert declarar(execution_id=7, session_factory=_factory(fila), **ARGS) is True
    assert len(_entradas(fila)) == 1
    assert _entradas(fila)[0]["capability"] == "tracker.comments.list"


def test_preserva_las_otras_claves_de_la_metadata():
    """Se afirma la PRESENCIA de lo previo, no la ausencia de errores: un assert
    de ausencia suelto pasa por accidente."""
    from services.capability_degradation import declarar

    fila = _FilaFalsa({
        "ado_context": {"comments_count": 3},
        "egress_sentinel": {"hallazgos": []},
    })
    assert declarar(execution_id=11, session_factory=_factory(fila), **ARGS) is True
    assert fila.metadata_dict["ado_context"] == {"comments_count": 3}
    assert fila.metadata_dict["egress_sentinel"] == {"hallazgos": []}
    assert len(_entradas(fila)) == 1


def test_la_misma_capability_y_sitio_no_se_duplica():
    """Un backlog de 200 tickets no puede escribir 200 entradas identicas."""
    from services.capability_degradation import declarar

    fila = _FilaFalsa()
    factory = _factory(fila)
    assert declarar(execution_id=3, session_factory=factory, **ARGS) is True
    assert declarar(execution_id=3, session_factory=factory, **ARGS) is False
    assert len(_entradas(fila)) == 1


def test_distinta_capability_en_el_mismo_sitio_agrega_las_dos():
    from services.capability_degradation import declarar

    fila = _FilaFalsa()
    factory = _factory(fila)
    assert declarar(execution_id=3, session_factory=factory, **ARGS) is True
    otra = dict(ARGS, capability="tracker.acceptance_criteria")
    assert declarar(execution_id=3, session_factory=factory, **otra) is True
    assert [e["capability"] for e in _entradas(fila)] == [
        "tracker.comments.list",
        "tracker.acceptance_criteria",
    ]


def test_una_sesion_rota_no_tumba_el_run():
    from services.capability_degradation import declarar

    @contextlib.contextmanager
    def _rompe():
        raise RuntimeError("database is locked")
        yield  # pragma: no cover

    avisos = []
    assert declarar(
        execution_id=5,
        session_factory=_rompe,
        log=lambda nivel, msg: avisos.append((nivel, msg)),
        **ARGS,
    ) is False
    assert avisos and avisos[0][0] == "warn"


def test_declarar_sin_log_y_con_sesion_rota_no_levanta():
    """C7 — con el default `log=None`, el `except` llamaria `None("warn", ...)` y
    lanzaria TypeError DESDE el manejador: `declarar()` levantaria exactamente en
    el escenario que el riel R2 dice cubrir. Sin este caso el bug es invisible:
    los otros siete pasan con el defecto puesto."""
    from services.capability_degradation import declarar

    @contextlib.contextmanager
    def _rompe():
        raise RuntimeError("database is locked")
        yield  # pragma: no cover

    assert declarar(execution_id=5, session_factory=_rompe, **ARGS) is False


# ── Pureza ───────────────────────────────────────────────────────────────────

def test_construir_entrada_es_pura():
    """Mismos argumentos -> mismo dict, salvo `at`. Y las CINCO claves del
    contrato congelado, ni una mas."""
    from services.capability_degradation import construir_entrada

    a = construir_entrada(**ARGS)
    b = construir_entrada(**ARGS)
    assert set(a) == {"capability", "reason", "provider", "site", "at"}
    assert {k: v for k, v in a.items() if k != "at"} == {
        k: v for k, v in b.items() if k != "at"
    }
    assert a["capability"] == "tracker.comments.list"
    assert a["site"] == "business_preflight._evaluate_functional"
