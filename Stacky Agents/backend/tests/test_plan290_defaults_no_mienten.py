"""Plan 290 F7 — ninguna FlagSpec puede afirmar un default que el codigo contradice.

KPI K2. El repo cometio este defecto 23 veces en `description=` y 1 vez en
`label=`; la peor es STACKY_TRACE_PROMPT_TEXT_ENABLED, que promete una garantia
de PRIVACIDAD ("privacidad OFF") con default=True — y la promesa estaba tanto en
la descripcion como en el TITULO que el operador lee.

Por que este gate NO es un molde de gate muerto, uno por uno:

  (a) centinela sobre un simbolo que una fase posterior borra -> NO aplica:
      recorre FlagSpec genericamente, no una key concreta, y ninguna fase de este
      plan borra FlagSpec.
  (b) test estatico sobre un defecto de ejecucion -> NO aplica: el defecto ES
      estatico (una discrepancia texto <-> codigo), asi que analizar el fuente es
      la herramienta correcta. Va por AST y no por regex sobre el archivo entero:
      una FlagSpec alcanzada por alias o con la descripcion partida en varias
      lineas tiene que contarse igual.
  (c) assert de ausencia suelto -> NEUTRALIZADO: cada test afirma las DOS cosas
      en la misma funcion — que el barrido vio >= 400 FlagSpec (o sea que
      efectivamente parseo algo; hoy son 490) Y que la lista de contradicciones
      esta vacia. Sin la primera mitad, un parser roto que devuelve cero flags
      daria verde eterno.

Lo que este gate NO cubre, y hay que escribirlo para que nadie crea que si: la
ayuda en lenguaje llano vive en un modulo SEPARADO (services/harness_flags_help.py,
PLAIN_HELP) y NO se deriva de `description`. Auditarla es alcance de otro plan.
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

FUENTE = BACKEND / "services" / "harness_flags.py"
CONFIG = BACKEND / "config.py"

#: Piso del barrido. Hoy son 490; el margen absorbe que un plan borre alguna sin
#: que el gate se vuelva inutil, pero no que el parser se rompa entero.
MINIMO_FLAGS = 400

#: Afirmaciones de default en el texto. `privacidad` entra porque el label de
#: STACKY_TRACE_PROMPT_TEXT_ENABLED promete "(C0/C1, privacidad OFF)" sin la
#: palabra "default": buscar solo "default off" lo dejaba pasar.
_AFIRMA_OFF = re.compile(r"(?:default|privacidad)\s*:?\s+(?:default\s+)?off\b", re.I)
_AFIRMA_ON = re.compile(r"(?:default|privacidad)\s*:?\s+(?:default\s+)?on\b", re.I)


def _literal(nodo):
    try:
        return ast.literal_eval(nodo)
    except Exception:  # noqa: BLE001 — un valor calculado no es una afirmacion
        return None


def _default_de_config(texto_cfg: str, key: str):
    """El default EFECTIVO sale de config.py, que es lo que corre en el arranque.

    El comentario de la FlagSpec no sirve: en este repo miente 23 veces.
    """
    m = re.search(
        r"os\.getenv\(\s*[\"']" + re.escape(key) + r"[\"']\s*,\s*[\"']([^\"']*)[\"']",
        texto_cfg,
    )
    return m.group(1) if m else None


def _censar(campo: str) -> tuple[int, list[str]]:
    """(cantidad de FlagSpec vistas, contradicciones en `campo`)."""
    texto_cfg = CONFIG.read_text(encoding="utf-8")
    arbol = ast.parse(FUENTE.read_text(encoding="utf-8"))

    vistas = 0
    contradicciones: list[str] = []
    for nodo in ast.walk(arbol):
        if not isinstance(nodo, ast.Call):
            continue
        f = nodo.func
        # Se acepta `FlagSpec(...)` y `modulo.FlagSpec(...)`: un alias no puede
        # sacar una flag del censo.
        if (getattr(f, "id", None) or getattr(f, "attr", None)) != "FlagSpec":
            continue
        vistas += 1

        kw = {k.arg: k.value for k in nodo.keywords if k.arg}
        key = _literal(kw.get("key")) if "key" in kw else None
        if not isinstance(key, str):
            continue

        cfg = _default_de_config(texto_cfg, key)
        declarado = _literal(kw.get("default")) if "default" in kw else None
        if cfg is not None:
            efectivo = cfg.strip().lower() in ("1", "true", "yes")
        elif isinstance(declarado, bool):
            efectivo = declarado
        else:
            continue  # numerica, string, o sin default resoluble: no aplica

        valor = _literal(kw.get(campo)) if campo in kw else None
        if not isinstance(valor, str):
            continue

        if efectivo and _AFIRMA_OFF.search(valor):
            contradicciones.append(f"{FUENTE.name}:{nodo.lineno} {key} dice OFF y esta ON")
        elif (not efectivo) and _AFIRMA_ON.search(valor) and not _AFIRMA_OFF.search(valor):
            contradicciones.append(f"{FUENTE.name}:{nodo.lineno} {key} dice ON y esta OFF")

    return vistas, contradicciones


def test_ninguna_descripcion_contradice_su_default():
    """KPI K2 — la mitad de `description=`."""
    vistas, contradicciones = _censar("description")
    assert vistas >= MINIMO_FLAGS, (
        f"el barrido solo vio {vistas} FlagSpec: el parser se rompio"
    )
    assert contradicciones == [], (
        f"descripciones que mienten sobre su default ({len(contradicciones)}): "
        + "\n  ".join(contradicciones)
    )


def test_ningun_label_contradice_su_default():
    """KPI K2 — la mitad de `label=`.

    Un gate que solo mirara `description=` dejaria abierta la puerta por la que ya
    entro la peor de las 23: la promesa de privacidad estaba TAMBIEN en el titulo,
    que es lo primero que el operador lee y lo que se renderiza en
    HarnessFlagsPanel.tsx:240.
    """
    vistas, contradicciones = _censar("label")
    assert vistas >= MINIMO_FLAGS, (
        f"el barrido solo vio {vistas} FlagSpec: el parser se rompio"
    )
    assert contradicciones == [], (
        f"labels que mienten sobre su default ({len(contradicciones)}): "
        + "\n  ".join(contradicciones)
    )
