"""services/cicd_corpus_mirror.py — Plan 243 F3.5.

Espejo contra el corpus: "¿en qué se diferencia de uno que YA funciona?".

Los gates G1-G3 responden *"¿está bien formado y no viola ninguna regla conocida?"*.
Ninguno responde la pregunta que de verdad se hace el operador frente a un draft
generado: ***"¿esto se parece a un pipeline que anda?"***. Y el caso típico no es un
YAML roto: es uno **correcto al que le falta un paso** — compila y testea pero nunca
publica el artefacto. Ningún gate lo ve.

La idea: ya tenemos 9 pipelines que corren en producción, vendorizados por F0. Se usan
como espejo — se compara la espina de tareas del draft contra la del golden más
parecido y se muestra la diferencia. Es la diferencia entre "pasó el linter" y "mirá
en qué se aparta de uno que ya funciona".

REGLAS DURAS:
  - DETERMINISTA: gana la mayor similaridad; empate -> nombre de archivo alfabético.
    Nunca aleatorio, nunca dependiente del orden de listdir.
  - NUNCA BLOQUEA: es `info`. No es un gate, no cambia el estado del artefacto, no
    puede impedir que el operador siga. Amplifica, no reemplaza.
  - SIN LLM, SIN RED: paridad automática en los 3 runtimes (Codex CLI, Claude Code
    CLI, GitHub Copilot Pro) — no hay nada específico de runtime que probar.
  - SILENCIO > CONSEJO INVENTADO: por debajo de MIN_SIMILARITY devuelve None y la UI
    no muestra nada.
  - El `hint` es DERIVADO, no redactado por un modelo.
"""
from __future__ import annotations

import io
import os
from dataclasses import dataclass

import yaml

from services.cicd_task_catalog import PROFILE_DOTNET_FRAMEWORK, extract_task_refs
from services.pipeline_lint import SEV_INFO

MIRROR_VERSION = "243.1"

# El espejo es informativo POR CONTRATO: esta constante es lo único que define su
# severidad y el test la fija. No hay ningún camino que produzca otra cosa.
SEVERITY = SEV_INFO

# Por debajo de esto no hay referencia razonable: mejor no decir nada.
MIN_SIMILARITY = 0.3

_GOLDEN_DIRS = {
    PROFILE_DOTNET_FRAMEWORK: os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "tests", "fixtures", "cicd_nl", "golden",
    ),
}

_CACHE: dict = {}


@dataclass(frozen=True)
class SpineDiff:
    reference: str        # "ci-cd-online.yml"
    similarity: float     # 0.0..1.0 — Jaccard sobre el conjunto de refs task:
    missing: tuple        # refs que el golden tiene y el draft NO -> "¿te falta esto?"
    extra: tuple          # refs que el draft tiene y el golden NO
    order_changed: bool   # misma composición, distinta secuencia
    hint: str             # español, accionable, derivado (no redactado por un LLM)
    severity: str = SEVERITY


def task_spine(yaml_text: str) -> tuple:
    """Espina de tareas de un YAML, en orden de aparición. PURA. NUNCA lanza.

    Reusa el extractor canónico de F0 (yaml.safe_load + recorrido recursivo), así que
    los `- task:` comentados no cuentan, por construcción.
    """
    try:
        return extract_task_refs(yaml_text or "")
    except yaml.YAMLError:
        return ()


def _load_golden(profile: str) -> dict:
    """{nombre: espina} del corpus del perfil. Cacheado, ordenado alfabéticamente."""
    if profile in _CACHE:
        return _CACHE[profile]

    carpeta = _GOLDEN_DIRS.get(profile)
    corpus: dict = {}
    if carpeta and os.path.isdir(carpeta):
        for nombre in sorted(os.listdir(carpeta)):       # sorted => determinismo
            if not nombre.endswith((".yml", ".yaml")):
                continue
            try:
                with io.open(os.path.join(carpeta, nombre), "r", encoding="utf-8") as fh:
                    espina = task_spine(fh.read())
            except OSError:
                continue
            if espina:
                corpus[nombre] = espina
    _CACHE[profile] = corpus
    return corpus


def _jaccard(a: set, b: set) -> float:
    union = a | b
    return (len(a & b) / len(union)) if union else 0.0


def _hint(reference: str, missing: tuple, extra: tuple, order_changed: bool) -> str:
    partes = []
    if missing:
        partes.append("le falta: %s" % ", ".join(missing))
    if extra:
        partes.append("agrega: %s" % ", ".join(extra))
    if not partes and order_changed:
        partes.append("tiene los mismos pasos pero en otro orden")
    if not partes:
        return ("Coincide paso por paso con %s, que hoy corre en producción." % reference)
    return ("Comparado con %s (que hoy corre en producción), a este draft %s."
            % (reference, " y ".join(partes)))


def nearest_golden(yaml_text: str, *, profile: str) -> "SpineDiff | None":
    """Golden más parecido al draft, o None si no hay referencia razonable.

    NUNCA lanza y NUNCA bloquea: su salida es `info` y no participa de ningún gate.
    """
    espina_draft = task_spine(yaml_text)
    if not espina_draft:
        return None

    corpus = _load_golden(profile)
    if not corpus:
        return None

    set_draft = set(espina_draft)
    # Determinismo: mayor similaridad primero; empate -> nombre alfabético.
    # `corpus` ya viene ordenado, y `min` con clave (-similarity, nombre) es estable.
    mejor_nombre, mejor_espina, mejor_sim = None, (), 0.0
    for nombre, espina in sorted(corpus.items()):
        sim = _jaccard(set_draft, set(espina))
        if sim > mejor_sim:
            mejor_nombre, mejor_espina, mejor_sim = nombre, espina, sim

    if mejor_nombre is None or mejor_sim < MIN_SIMILARITY:
        return None

    set_golden = set(mejor_espina)
    missing = tuple(r for r in dict.fromkeys(mejor_espina) if r not in set_draft)
    extra = tuple(r for r in dict.fromkeys(espina_draft) if r not in set_golden)
    # "Mismo conjunto, distinta secuencia": comparar la secuencia deduplicada evita
    # que una tarea repetida (VSBuild@1 dos veces) se lea como cambio de orden.
    order_changed = (
        not missing and not extra
        and tuple(dict.fromkeys(espina_draft)) != tuple(dict.fromkeys(mejor_espina))
    )

    return SpineDiff(
        reference=mejor_nombre,
        similarity=round(mejor_sim, 4),
        missing=missing,
        extra=extra,
        order_changed=order_changed,
        hint=_hint(mejor_nombre, missing, extra, order_changed),
    )
