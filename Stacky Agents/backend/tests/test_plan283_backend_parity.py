"""Plan 283 F6 [ADICION A2] - La paridad deja de ser un argumento y pasa a ser
una MEDICION.

El gate K4 del v1 corria por AST sobre `services/meeting_minutes.py` para
verificar que NO importa los runners de agente. Pero ese archivo lo escribe este
mismo plan: nadie iba a importar un runner ahi. El gate pasa POR CONSTRUCCION,
no puede ponerse rojo nunca, y seguiria verde aunque la paridad se rompiera en
el unico lugar donde puede romperse, que es `copilot_bridge`. Un gate que no
puede fallar no mide nada.

Lo que si se verifico abriendo el archivo: `copilot_bridge.invoke()` despacha
por `config.LLM_BACKEND`, cuyos valores son `mock | vscode_bridge | copilot |
claude_cli | local_llm`, y ese eje es ORTOGONAL al runtime de agente (Codex CLI,
Claude Code CLI, GitHub Copilot). La afirmacion es correcta; lo que faltaba era
medirla. Este archivo corre el destilado una vez POR CADA backend y exige salida
identica.

Cabecera obligatoria: DATABASE_URL en memoria ANTES de importar la app (R8).
"""
from __future__ import annotations

import ast
import json
import os
import pathlib

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import pytest  # noqa: E402

# Los 5 valores que despacha copilot_bridge.invoke(). No es una lista de deseos:
# el caso 6 la coteja contra las ramas REALES del archivo, por AST.
BACKENDS = ("mock", "vscode_bridge", "copilot", "claude_cli", "local_llm")

_BRIDGE = pathlib.Path(__file__).resolve().parents[1] / "copilot_bridge.py"

FUENTE = (
    "Juan Perez: arrancamos con el estado del proyecto.\n"
    "Ana Gomez: yo reviso el informe el viernes.\n"
    "Juan Perez: perfecto, lo vemos el lunes entonces."
)

RESPUESTA = json.dumps({
    "resumen": "Se reviso el estado del proyecto y quedaron dos compromisos.",
    "decisiones": [{"texto": "Se revisa el lunes",
                    "cita": "perfecto, lo vemos el lunes entonces"}],
    "pendientes": [
        {"titulo": "Revisar el informe", "responsable": "Ana",
         "fecha_compromiso": "2026-08-07", "cita": "yo reviso el informe el viernes"},
        {"titulo": "Confirmar la sala", "responsable": "Marcela",
         "fecha_compromiso": None, "cita": "arrancamos con el estado del proyecto"},
    ],
    "riesgos": [],
}, ensure_ascii=False)


class _RespuestaFalsa:
    def __init__(self, text: str):
        self.text = text
        self.format = "markdown"
        self.metadata = {}


@pytest.fixture(autouse=True)
def _db():
    import db

    db.init_db()
    with db.session_scope() as s:
        from services.meetings_store import Meeting, MeetingActionItem

        s.query(MeetingActionItem).delete(synchronize_session=False)
        s.query(Meeting).delete(synchronize_session=False)
    yield


def _corrida(monkeypatch, backend: str) -> dict:
    import copilot_bridge
    from config import config as _cfg
    from services import meeting_minutes, meetings_store

    monkeypatch.setattr(_cfg, "LLM_BACKEND", backend, raising=False)
    monkeypatch.setattr(
        copilot_bridge, "invoke", lambda **kwargs: _RespuestaFalsa(RESPUESTA)
    )

    mid = meetings_store.create_meeting(project="PARIDAD", subject="Semanal")
    meetings_store.save_transcript(mid, content=FUENTE, fmt="txt")
    salida = meeting_minutes.build_minutes_payload(meeting_id=mid, project="PARIDAD")
    # `meeting_id` cambia entre corridas por el autoincremental: se saca a
    # proposito, porque lo que se compara es el DESTILADO, no el identificador.
    salida.pop("meeting_id", None)
    return salida


@pytest.mark.parametrize("backend", BACKENDS)
def test_el_destilado_es_identico_en_los_5_backends(backend, monkeypatch):
    """Casos 1-5, uno por valor de `LLM_BACKEND`.

    El resultado se compara contra el de `mock`, que se recalcula dentro del
    mismo caso: asi cada caso vale solo y no depende del orden de ejecucion.
    """
    referencia = _corrida(monkeypatch, "mock")
    medido = _corrida(monkeypatch, backend)

    assert medido == referencia, (
        f"el destilado difiere con LLM_BACKEND={backend!r}: la paridad se rompio"
    )
    # Y no es una comparacion de dos dicts vacios: guard positivo sobre el
    # contenido que de verdad importa.
    assert medido["ok"] is True and medido["estado"] == "done"
    assert medido["minutes"]["pendientes"][0]["atribucion"] == "confirmada"
    assert medido["minutes"]["pendientes"][1]["atribucion"] == "sin_hablante"


def test_guard_positivo_el_parametrize_selecciono_5_y_son_los_reales():
    """Sin esto, un `parametrize` vacio o un `-k` sin match daria EXIT 0 y
    pareceria verde. Ademas la lista no se copia a mano: se coteja contra las
    ramas reales de `copilot_bridge.invoke`, por AST."""
    assert len(BACKENDS) == 5
    assert len(set(BACKENDS)) == 5

    arbol = ast.parse(_BRIDGE.read_text(encoding="utf-8"))
    invoke = next(
        n for n in ast.walk(arbol)
        if isinstance(n, ast.FunctionDef) and n.name == "invoke"
    )
    ramas: set[str] = set()
    for nodo in ast.walk(invoke):
        if isinstance(nodo, ast.Compare) and isinstance(nodo.left, ast.Name):
            if nodo.left.id == "backend":
                for comparado in nodo.comparators:
                    if isinstance(comparado, ast.Constant) and isinstance(comparado.value, str):
                        ramas.add(comparado.value)
    # Guard del propio guard: si el lector de AST se rompe, esto lo dice.
    assert ramas, "no se pudo leer ninguna rama de LLM_BACKEND en copilot_bridge.invoke"
    assert ramas == set(BACKENDS), (
        f"las ramas reales de copilot_bridge son {sorted(ramas)}; "
        f"la matriz de paridad cubre {sorted(BACKENDS)}"
    )
