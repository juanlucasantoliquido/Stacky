"""Plan 283 F3 - El parseo es puro, determinista y no pierde turnos en silencio.

Cabecera obligatoria: DATABASE_URL en memoria ANTES de importar la app (R8).
Este modulo no toca la base, pero la cabecera va igual: es barata y el dia que
alguien agregue un import de conveniencia, ya esta puesta.
"""
from __future__ import annotations

import ast
import os
import pathlib

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from services.transcript_parser import (  # noqa: E402
    MAX_TRANSCRIPT_CHARS,
    TranscriptTurn,
    detect_format,
    hablante_matchea,
    normalize_transcript,
    parse_plain,
    parse_vtt,
)

_MODULO = pathlib.Path(__file__).resolve().parents[1] / "services" / "transcript_parser.py"

VTT_TEAMS = """WEBVTT

NOTE Esta transcripcion la genero Microsoft Teams
y esta nota ocupa dos lineas

1cb3a9f4-4a4f-4b0e-9b3d-1e2f3a4b5c6d/1-0
00:00:01.000 --> 00:00:04.500
<v Juan Perez>Arrancamos con el estado del proyecto.</v>

2
00:00:05.000 --> 00:00:09.000
<v Ana Gomez>Yo reviso el informe el viernes.</v>

3
00:01:23.450 --> 00:01:28.000
<v Juan Perez>Perfecto, lo vemos el lunes entonces.</v>
"""


def test_1_detect_format():
    assert detect_format(VTT_TEAMS) == "vtt"
    assert detect_format("\n\n  WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nhola") == "vtt"
    assert detect_format("Juan: hola\nAna: chau") == "txt"
    assert detect_format("") == "txt"
    # Un archivo que solo MENCIONA la palabra no es un archivo de subtitulos.
    assert detect_format("hablamos de WEBVTT en la reunion") == "txt"


def test_2_vtt_con_etiqueta_de_voz():
    turnos = parse_vtt(VTT_TEAMS)
    assert [t.speaker for t in turnos] == ["Juan Perez", "Ana Gomez", "Juan Perez"]
    # Sin etiquetas en el texto.
    assert turnos[0].text == "Arrancamos con el estado del proyecto."
    assert "<v" not in turnos[0].text and "</v>" not in turnos[0].text


def test_3_vtt_con_prefijo_nombre_dos_puntos():
    crudo = (
        "WEBVTT\n\n"
        "00:00:01.000 --> 00:00:03.000\n"
        "Marcela Diaz: el presupuesto se aprueba manana.\n"
    )
    turnos = parse_vtt(crudo)
    assert len(turnos) == 1
    assert turnos[0].speaker == "Marcela Diaz"
    assert turnos[0].text == "el presupuesto se aprueba manana."


def test_4_cabecera_notas_y_cue_ids_no_producen_turnos():
    turnos = parse_vtt(VTT_TEAMS)
    assert len(turnos) == 3, [t.text for t in turnos]
    todo = " ".join(t.text for t in turnos)
    assert "WEBVTT" not in todo
    assert "Microsoft Teams" not in todo         # el bloque NOTE entero se descarta
    assert "1cb3a9f4" not in todo                # el cue-id con forma de UUID
    assert not any(t.text.strip() in ("1", "2", "3") for t in turnos)

    # Guard: una linea con forma de cue-id que NO esta antes de la linea de
    # tiempo SE CONSERVA. Ante la duda no se descarta.
    conservado = parse_vtt(
        "WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nAna: el codigo es 12345\n"
    )
    assert conservado[0].text == "el codigo es 12345"


def test_5_marcas_de_tiempo_en_milisegundos():
    turnos = parse_vtt(VTT_TEAMS)
    assert turnos[0].start_ms == 1000
    assert turnos[2].start_ms == 83450          # 00:01:23.450

    corto = parse_vtt("WEBVTT\n\n01:23.450 --> 01:28.000\nAna: forma corta\n")
    assert corto[0].start_ms == 83450

    # En texto plano no hay marcas de tiempo.
    assert parse_plain("Ana: hola")[0].start_ms is None


def test_6_texto_plano_linea_sin_dos_puntos_se_concatena():
    turnos = parse_plain(
        "Juan: arranquemos\n"
        "y despues vemos el resto\n"
        "Ana: dale\n"
    )
    assert len(turnos) == 2
    assert turnos[0].speaker == "Juan"
    assert turnos[0].text == "arranquemos y despues vemos el resto"
    assert turnos[1].text == "dale"


def test_7_texto_plano_sin_ningun_dos_puntos_es_un_solo_turno():
    turnos = parse_plain("hablamos del informe\ny quedamos en verlo el viernes")
    assert len(turnos) == 1
    assert turnos[0].speaker == ""
    assert turnos[0].text == "hablamos del informe y quedamos en verlo el viernes"


def test_8_k7_el_truncado_se_declara_y_nunca_parte_un_turno():
    partes = ["WEBVTT"]
    for i in range(20):
        partes.append(
            f"\n{i + 1}\n00:00:{i:02d}.000 --> 00:00:{i + 1:02d}.000\n"
            f"<v Hablante {i % 3}>Frase numero {i} con relleno suficiente para ocupar lugar.</v>\n"
        )
    crudo = "".join(partes)

    completo = normalize_transcript(crudo)
    assert completo["turnos_totales"] == 20
    assert completo["turnos_incluidos"] == 20

    recortado = normalize_transcript(crudo, max_chars=200)
    assert recortado["turnos_incluidos"] < recortado["turnos_totales"]
    assert recortado["turnos_totales"] == 20
    assert len(recortado["texto"]) <= 200
    assert recortado["chars"] < recortado["chars_totales"]      # el recorte se declara

    # NINGUN turno incluido quedo cortado: cada uno es identico al original.
    originales = {t.text for t in completo["turnos"]}
    for turno in recortado["turnos"]:
        assert turno.text in originales, f"turno partido por la mitad: {turno.text!r}"

    assert MAX_TRANSCRIPT_CHARS == 120_000


def test_9_pureza_del_modulo_por_ast():
    """Gate D3. Se prueba PRIMERO contra el defecto: el mismo detector corre
    sobre un fuente que SI importa lo prohibido y tiene que encontrarlo. Sin ese
    guard, el caso pasaria por accidente si el detector estuviera roto."""
    prohibidos = {"requests", "copilot_bridge", "flask", "db", "config"}

    def _imports(fuente: str) -> set[str]:
        encontrados: set[str] = set()
        for nodo in ast.walk(ast.parse(fuente)):
            if isinstance(nodo, ast.Import):
                for alias in nodo.names:
                    encontrados.update(alias.name.split("."))
            elif isinstance(nodo, ast.ImportFrom):
                if nodo.module:
                    encontrados.update(nodo.module.split("."))
                # `from services import db` deja el nombre en `names`, NO en
                # `module`: un detector que solo mire `module` es ciego a eso.
                for alias in nodo.names:
                    encontrados.add(alias.name)
        return encontrados

    # GUARD POSITIVO, PRIMERO: las DOS formas de import.
    sucio = "import requests\nfrom db import Base\nfrom services import config\nimport ast\n"
    assert _imports(sucio) & prohibidos == {"requests", "db", "config"}

    real = _imports(_MODULO.read_text(encoding="utf-8"))
    assert real & prohibidos == set(), f"transcript_parser.py importa {sorted(real & prohibidos)}"


def test_10_entrada_vacia_no_lanza():
    for crudo in ("", "   ", "\n\n\t\n"):
        resultado = normalize_transcript(crudo)
        assert resultado["turnos"] == []
        assert resultado["texto"] == ""
        assert resultado["hablantes"] == ()
        assert resultado["turnos_totales"] == 0
        assert resultado["turnos_incluidos"] == 0


def test_11_hablantes_distintos_en_orden_y_calculados_sobre_los_incluidos():
    partes = ["WEBVTT"]
    nombres = ["Juan Perez", "Ana Gomez", "Luis Sosa"]
    for i in range(8):
        partes.append(
            f"\n{i + 1}\n00:00:{i:02d}.000 --> 00:00:{i + 1:02d}.000\n"
            f"<v {nombres[i % 3]}>Intervencion numero {i} de esta reunion.</v>\n"
        )
    crudo = "".join(partes)

    completo = normalize_transcript(crudo)
    assert completo["hablantes"] == ("Juan Perez", "Ana Gomez", "Luis Sosa")
    assert len(completo["hablantes"]) == 3        # distintos, sin duplicados
    assert "" not in completo["hablantes"]

    # Recortado hasta dejar afuera al tercero: `hablantes` trae 2, no 3. Si su
    # frase no esta en `texto`, tampoco puede respaldar una cita.
    parcial = normalize_transcript(crudo, max_chars=120)
    assert parcial["turnos_incluidos"] < 8
    assert parcial["hablantes"] == ("Juan Perez", "Ana Gomez")


def test_12_hablante_matchea_es_conservador_y_determinista():
    hablantes = ("Juan Perez", "Ana Gomez")
    assert hablante_matchea("Juan", hablantes) is True
    assert hablante_matchea("Juan Perez", hablantes) is True
    assert hablante_matchea("Perez, Juan", hablantes) is True     # orden distinto
    assert hablante_matchea("juan perez", hablantes) is True      # casefold
    assert hablante_matchea("Marcela", hablantes) is False        # nadie con ese nombre
    assert hablante_matchea("", hablantes) is False
    assert hablante_matchea("Juan", ()) is False
    assert hablante_matchea(None, hablantes) is False
    # Nada de comparacion difusa: un nombre parecido NO matchea.
    assert hablante_matchea("Juana", hablantes) is False
    assert isinstance(TranscriptTurn("a", None, "b"), TranscriptTurn)
