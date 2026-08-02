"""Plan 283 F3 - De lo que el operador pega a turnos estructurados. PURO.

D3: si el modelo tuviera que separar hablantes y marcas de tiempo, cada error de
parseo se volveria una alucinacion imposible de auditar. Aca no hay modelo, no
hay red y no hay base: es una funcion de texto a texto, 100% testeable sola.

Este modulo NO importa `requests`, `copilot_bridge`, `flask`, `db` ni `config`.
Hay un gate por AST que lo verifica (F3 caso 9), y ese gate se prueba PRIMERO
contra un fuente que si los importa.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# Constante del modulo, NO flag: no es una decision del operador, es el techo
# tecnico de lo que se le puede mandar de una a un modelo.
MAX_TRANSCRIPT_CHARS = 120_000


@dataclass(frozen=True)
class TranscriptTurn:
    speaker: str            # "" si el formato no lo trae
    start_ms: int | None    # None si no hay marca de tiempo
    text: str


# `HH:MM:SS.mmm -->` y tambien la forma corta `MM:SS.mmm -->`. Se acepta coma
# decimal porque algunos exportadores la usan.
_TIME_RE = re.compile(r"^(?:(\d{1,3}):)?(\d{1,2}):(\d{2})[.,](\d{1,3})\s*-->")
# `<v Nombre Apellido>texto</v>` (con cierre) y su variante sin cierre.
_VOICE_RE = re.compile(r"<v\s+([^>]*)>(.*?)</v>", re.DOTALL)
_VOICE_OPEN_RE = re.compile(r"^<v\s+([^>]*)>(.*)$", re.DOTALL)
_TAG_RE = re.compile(r"</?[a-zA-Z][^>]*>")
# Identificador de cue: numerico, o el UUID que emite Teams (con su sufijo
# `/1-0` opcional). REGLA LITERAL: una linea se descarta como cue-id SI Y SOLO
# SI es la PRIMERA del bloque, la SIGUIENTE es la linea de tiempo, y matchea
# esto. Cualquier otra cosa se CONSERVA COMO TEXTO: perder un turno en silencio
# es peor que arrastrar un identificador.
_CUE_ID_RE = re.compile(
    r"^(?:[0-9]+"
    r"|[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}(?:/\d+-\d+)?"
    r")$"
)
# Prefijo `Nombre Apellido: texto`. Conservador a proposito: como mucho 5
# palabras y sin puntuacion de oracion, para no partir "la fecha: el viernes".
_PREFIJO_RE = re.compile(r"^([^:<>\n]{1,60}):\s*(.*)$", re.DOTALL)


def detect_format(raw: str) -> str:
    """`"vtt"` si la primera linea no vacia es exactamente `WEBVTT`; si no, `"txt"`."""
    for linea in (raw or "").splitlines():
        limpia = linea.strip().lstrip("﻿")
        if not limpia:
            continue
        return "vtt" if limpia.upper() == "WEBVTT" else "txt"
    return "txt"


def _ms(match: re.Match) -> int:
    horas = int(match.group(1) or 0)
    minutos = int(match.group(2))
    segundos = int(match.group(3))
    milis = int(match.group(4).ljust(3, "0"))
    return ((horas * 3600) + (minutos * 60) + segundos) * 1000 + milis


def _parece_nombre(cabeza: str) -> bool:
    cabeza = cabeza.strip()
    if not cabeza or len(cabeza) > 60:
        return False
    if len(cabeza.split()) > 5:
        return False
    return not any(c in cabeza for c in ".!?;")


def _partir_prefijo(texto: str) -> tuple[str, str]:
    """`("Ana", "hola")` si el texto arranca con `Nombre: `; si no, `("", texto)`."""
    m = _PREFIJO_RE.match(texto)
    if m and _parece_nombre(m.group(1)):
        return m.group(1).strip(), m.group(2).strip()
    return "", texto.strip()


def _extraer_hablante(texto: str) -> tuple[str, str]:
    partes = _VOICE_RE.findall(texto)
    if partes:
        hablante = partes[0][0].strip()
        cuerpo = " ".join(p[1].strip() for p in partes).strip()
        return hablante, _TAG_RE.sub("", cuerpo).strip()
    abierto = _VOICE_OPEN_RE.match(texto)
    if abierto:
        return abierto.group(1).strip(), _TAG_RE.sub("", abierto.group(2)).strip()
    return _partir_prefijo(_TAG_RE.sub("", texto).strip())


def parse_vtt(raw: str) -> list[TranscriptTurn]:
    texto = (raw or "").replace("\r\n", "\n").replace("\r", "\n")
    turnos: list[TranscriptTurn] = []
    for bloque in re.split(r"\n[ \t]*\n", texto):
        lineas = [x.strip() for x in bloque.split("\n")]
        lineas = [x for x in lineas if x]
        if not lineas:
            continue
        if lineas[0].lstrip("﻿").upper().startswith("WEBVTT"):
            lineas = lineas[1:]
        if not lineas or lineas[0].upper().startswith("NOTE"):
            continue
        idx = next((i for i, l in enumerate(lineas) if _TIME_RE.match(l)), None)
        if idx is None:
            continue                       # bloque sin linea de tiempo: no es un cue
        previas = lineas[:idx]
        if idx == 1 and _CUE_ID_RE.match(previas[0]):
            previas = []                   # era el identificador del cue
        cuerpo = " ".join(previas + lineas[idx + 1:]).strip()
        if not cuerpo:
            continue
        hablante, contenido = _extraer_hablante(cuerpo)
        if contenido:
            turnos.append(TranscriptTurn(hablante, _ms(_TIME_RE.match(lineas[idx])), contenido))
    return turnos


def parse_plain(raw: str) -> list[TranscriptTurn]:
    lineas = [x.strip() for x in (raw or "").splitlines()]
    lineas = [x for x in lineas if x]
    if not lineas:
        return []
    if not any(":" in x for x in lineas):
        # Sin ningun `:` en todo el texto no hay a quien atribuirle nada: un solo
        # turno anonimo. Es lo correcto — inventar hablantes seria peor.
        return [TranscriptTurn("", None, " ".join(lineas))]

    turnos: list[TranscriptTurn] = []
    for linea in lineas:
        hablante, contenido = _partir_prefijo(linea)
        if hablante:
            turnos.append(TranscriptTurn(hablante, None, contenido))
        elif turnos:
            previo = turnos[-1]
            turnos[-1] = TranscriptTurn(
                previo.speaker, previo.start_ms, f"{previo.text} {linea}".strip()
            )
        else:
            turnos.append(TranscriptTurn("", None, linea))
    return turnos


def _linea(turno: TranscriptTurn) -> str:
    return f"{turno.speaker}: {turno.text}" if turno.speaker else turno.text


def _render(turnos: list[TranscriptTurn]) -> str:
    return "\n".join(_linea(t) for t in turnos)


def normalize_transcript(raw: str, *, max_chars: int = MAX_TRANSCRIPT_CHARS) -> dict:
    """Turnos + la CADENA CANONICA contra la que se verifica cada cita (D4).

    `texto` es exactamente lo que se le manda al modelo, y exactamente contra lo
    que `parse_minutes_response` comprueba que la cita sea literal. Si fueran
    dos cadenas distintas, la verificacion seria teatro.

    K7 - nada se pierde en silencio: `turnos_totales` vs `turnos_incluidos` y
    `chars_totales` vs `chars` declaran TODO lo que se recorto. Los turnos se
    sacan DESDE EL FINAL y nunca se parte uno por la mitad.
    """
    formato = detect_format(raw)
    turnos = parse_vtt(raw) if formato == "vtt" else parse_plain(raw)
    chars_totales = len(_render(turnos))

    incluidos: list[TranscriptTurn] = []
    acumulado = 0
    for turno in turnos:
        largo = len(_linea(turno)) + (1 if incluidos else 0)
        if acumulado + largo > max_chars:
            break
        acumulado += largo
        incluidos.append(turno)

    if not incluidos and turnos:
        # Caso degenerado: un unico turno mas largo que el techo (texto plano sin
        # ningun `:`). Aca SI se corta, porque la alternativa es devolver vacio y
        # perderlo todo. Queda declarado por `chars < chars_totales`.
        primero = turnos[0]
        incluidos = [TranscriptTurn(primero.speaker, primero.start_ms, primero.text[:max_chars])]

    texto = _render(incluidos)
    # Hablantes DISTINTOS, en orden de aparicion, sin el vacio, y calculados
    # SOBRE LOS INCLUIDOS: si a alguien lo dejo afuera el recorte, su frase
    # tampoco esta en `texto`, asi que tampoco puede respaldar una cita.
    hablantes = tuple(dict.fromkeys(t.speaker for t in incluidos if t.speaker))
    return {
        "formato": formato,
        "turnos": incluidos,
        "texto": texto,
        "turnos_totales": len(turnos),
        "turnos_incluidos": len(incluidos),
        "chars": len(texto),
        "chars_totales": chars_totales,
        "hablantes": hablantes,
    }


_SEPARADOR_TOKENS_RE = re.compile(r"[\s,;.]+")


def _tokens(nombre: str) -> frozenset[str]:
    return frozenset(t for t in _SEPARADOR_TOKENS_RE.split((nombre or "").casefold()) if t)


def hablante_matchea(responsable: str, hablantes: tuple[str, ...]) -> bool:
    """[D9] Compara por TOKENS, no por cadena: `"Juan"` ~ `"Juan Perez"` y
    `"Perez, Juan"` ~ `"Juan Perez"`.

    NO usa comparacion difusa ni distancia de edicion, a proposito: o es
    determinista y explicable, o no sirve como evidencia. Un falso NEGATIVO
    degrada el pendiente a `sin_hablante`, que es seguro; un falso POSITIVO le
    asignaria trabajo real a una persona real. Ante la duda, no matchea.
    """
    buscado = _tokens(responsable)
    if not buscado or not hablantes:
        return False
    for hablante in hablantes:
        propios = _tokens(hablante)
        if not propios:
            continue
        if buscado <= propios or propios <= buscado:
            return True
    return False
