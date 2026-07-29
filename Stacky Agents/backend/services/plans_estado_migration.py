"""Plan 263 F3 + F2.5 — normalización de estado con evidencia (preview + apply HITL).

Servicio de solo-cálculo (`preview_estado_migration`) + escritura HITL con
transacción de 3 patas (`apply_estado_migration`). NO reimplementa la regla de
qué es un plan ni de qué es un estado: importa `_PLAN_FILE_RE` / `_ESTADO_RE` /
`_HEADER_READ_CHARS` / `_LEDGER_OK_VEREDICTOS` de `services.plans_board`.

Ninguna de las dos funciones públicas lanza. `apply_estado_migration` es el
ÚNICO escritor de `.md` de este módulo: cada item se escribe atómicamente
(.tmp + os.replace) o se omite con una razón; si la pata 2 (ledger) o la 3
(baseline) fallan, el `.md` se restaura desde el contenido que se leyó antes
de escribir (rollback), nunca queda un archivo a medias.
"""
from __future__ import annotations

import difflib
import hashlib
import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import services.plans_board as plans_board
from services.plans_board import (
    _ESTADO_RE,
    _HEADER_READ_CHARS,
    _LEDGER_OK_VEREDICTOS,
    _PLAN_FILE_RE,
)

logger = logging.getLogger(__name__)

# Vocabulario cerrado de estados que se pueden ESCRIBIR en un .md (nota: el
# "parcial" usa GUION, es el literal que después normalize_estado() reconoce
# vía `"IMPLEMENTADO-PARCIAL" in u` -> "IMPLEMENTADO_PARCIAL" con GUION BAJO).
ESTADOS_ELEGIBLES = ("PROPUESTO", "CRITICADO", "IMPLEMENTADO", "IMPLEMENTADO-PARCIAL")

_PREVIEW_READ_CHARS = 8000

_REGISTRO_IMPL_RE = re.compile(r"^#{1,4}\s*.*Registro de implementaci", re.MULTILINE)
_TABLA_IMPLEMENTADA_RE = re.compile(r"^\|[^|\n]*\|\s*IMPLEMENTADA\s*\|", re.MULTILINE)

# Plan 263 — el baseline es una estructura FIJA del repo (igual que
# silence_ratchet_baseline.json / uiDebtBaseline.json): no depende de
# `docs_dir`. Constante de MÓDULO (no función) para que los tests puedan
# monkeypatchearla a un tmp_path y no tocar el archivo real del repo.
_BASELINE_PATH = Path(__file__).resolve().parents[1] / "tests" / "plans_estado_baseline.json"


def _leer_texto(path: Path, max_chars: int) -> str:
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        return fh.read(max_chars)


def _find_insert_after_line(texto_completo: str) -> int:
    """Índice 0-based de la línea `# titulo` (H1). Si no hay H1, 0 (tope)."""
    for i, linea in enumerate(texto_completo.splitlines()):
        if linea.startswith("# "):
            return i
    return 0


def _raw_ledger_entry(docs_dir: Path, number: int) -> tuple[dict | None, str | None]:
    """Lectura CRUDA del ledger (NO usa plans_board.load_ledger(), que traga
    errores de parseo devolviendo {}). Devuelve (entry_o_None, error_o_None).
    `error` sólo es no-None si el archivo EXISTE y es ilegible/malformado —
    "no existe" NUNCA es error: significa "nada que resellar todavía"."""
    path = docs_dir / "_supervision" / "ledger.json"
    if not path.exists():
        return None, None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None, "ledger.json no parsea"
    planes = data.get("planes") if isinstance(data, dict) else None
    if not isinstance(planes, dict):
        return None, "ledger.json sin la clave 'planes'"
    return planes.get(str(number)), None


def infer_estado_con_evidencia(plan_card: dict, docs_dir: Path) -> dict:
    """Propone el **Estado:** a escribir para UN plan, con su evidencia.

    NUNCA lanza. NUNCA escribe. Ver contrato completo en el plan 263 F3.
    """
    number = plan_card["number"]
    filename = plan_card["filename"]
    path = docs_dir / filename

    try:
        contenido = path.read_bytes()
    except OSError:
        contenido = b""
    try:
        texto_completo = contenido.decode("utf-8", errors="replace")
    except Exception:      # noqa: BLE001 — defensivo, nunca debería pasar con errors="replace"
        texto_completo = ""
    texto = texto_completo[:_PREVIEW_READ_CHARS]
    sha256_visto = hashlib.sha256(contenido).hexdigest() if contenido else ""

    entry, _err_ignorado_en_infer = _raw_ledger_entry(docs_dir, number)
    resella_ledger = bool(entry and entry.get("doc_sha256"))

    estado_propuesto: str | None
    confianza: str
    evidencia: list[str] = []

    if entry and entry.get("veredicto") in _LEDGER_OK_VEREDICTOS:
        estado_propuesto = "IMPLEMENTADO"
        confianza = "alta"
        evidencia.append(
            f"El supervisor lo aprobó el {entry.get('fecha', '?')} y el documento "
            "cambió después (ledger.json)."
        )
    elif _REGISTRO_IMPL_RE.search(texto) or _TABLA_IMPLEMENTADA_RE.search(texto):
        estado_propuesto = "IMPLEMENTADO"
        confianza = "alta"
        # Nota: la frase SIEMPRE cita "Registro de implementaci" (mismo texto en
        # los dos sub-marcadores, encabezado o fila de tabla) porque el centinela
        # del corpus vivo (test_plan263_migration.py caso 23) verifica esa
        # substring literal en TODA propuesta "alta", sin distinguir cuál de los
        # dos patrones estructurales disparó.
        evidencia.append(
            "El documento trae su Registro de implementación "
            "(encabezado o fila de tabla marcada IMPLEMENTADA)."
        )
    elif "veredicto" in texto.lower() and ("APROBADO" in texto or "RECHAZADO" in texto):
        estado_propuesto = "CRITICADO"
        confianza = "media"
        evidencia.append("El documento trae un veredicto del juez, pero no registro de implementacion.")
    else:
        estado_propuesto = None
        confianza = "sin_evidencia"
        evidencia.append(
            "Sin evidencia en el documento ni en el ledger. El tablero lo muestra "
            "como implementado (inferido), pero NO hay nada verificable que "
            "escribir: decidilo vos."
        )

    aplicable = estado_propuesto is not None
    insert_after_line = _find_insert_after_line(texto_completo)

    if estado_propuesto is not None:
        hoy = datetime.now(timezone.utc).date().isoformat()
        linea_a_insertar = (
            f"**Estado:** {estado_propuesto} (normalizado {hoy}, Plan 263) — "
            "sin veredicto de supervisor"
        )
    else:
        linea_a_insertar = None

    return {
        "number": number,
        "filename": filename,
        "estado_propuesto": estado_propuesto,
        "confianza": confianza,
        "aplicable": aplicable,
        "evidencia": evidencia,
        "linea_a_insertar": linea_a_insertar,
        "insert_after_line": insert_after_line,
        "sha256_visto": sha256_visto,
        "resella_ledger": resella_ledger,
    }


def preview_estado_migration(docs_dir: Path) -> dict:
    """SOLO LECTURA. Nunca escribe. Nunca lanza.

    {"ok": True, "total": int, "propuestas": [...], "por_confianza": {...},
     "aplicables": int, "ya_resueltos_por_ledger": [str]}
    """
    board = plans_board.build_board(docs_dir, None)

    propuestas: list[dict] = []
    ya_resueltos: list[str] = []

    for card in board["plans"]:
        if card.get("estado_efectivo") == "SIN_DOCUMENTO":
            continue                                   # no es un .md real
        origen = card.get("estado_origen")
        if origen == plans_board.ORIGEN_LEDGER:
            ya_resueltos.append(card["filename"])
            continue
        if origen != plans_board.ORIGEN_INFERIDO:
            continue                                   # ya declara estado: nada que proponer
        propuestas.append(infer_estado_con_evidencia(card, docs_dir))

    por_confianza = {"alta": 0, "media": 0, "sin_evidencia": 0}
    for p in propuestas:
        por_confianza[p["confianza"]] = por_confianza.get(p["confianza"], 0) + 1

    return {
        "ok": True,
        "total": len(propuestas),
        "propuestas": propuestas,
        "por_confianza": por_confianza,
        "aplicables": sum(1 for p in propuestas if p["aplicable"]),
        "ya_resueltos_por_ledger": ya_resueltos,
    }


def _escribir_atomico(path: Path, contenido: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as fh:
        fh.write(contenido)
    os.replace(tmp, path)


def _insertar_linea(texto_completo: str, insert_after_line: int, linea: str) -> str:
    lineas = texto_completo.splitlines()
    nuevas = lineas[: insert_after_line + 1] + ["", linea] + lineas[insert_after_line + 1:]
    nuevo = "\n".join(nuevas)
    if texto_completo.endswith("\n"):
        nuevo += "\n"
    return nuevo


def _unified_diff(antes: str, despues: str, filename: str) -> str:
    return "".join(
        difflib.unified_diff(
            antes.splitlines(keepends=True),
            despues.splitlines(keepends=True),
            fromfile=filename, tofile=filename,
        )
    )


def _resellar_ledger_si_corresponde(docs_dir: Path, number: int, nuevo_sha: str) -> tuple[bool, str | None]:
    """Pata 2. Devuelve (hizo_resello, error). NO usa load_ledger() (Contrato,
    regla 1): lee el documento COMPLETO y toca UNA sola clave.

    "No existe" -> (False, None): nada que resellar, no es un error.
    "Existe pero no parsea / sin 'planes' dict" -> (False, "<motivo>"): error,
    dispara rollback en el llamador.
    "Existe, sin entrada para este plan (o sin doc_sha256)" -> (False, None).
    """
    path = docs_dir / "_supervision" / "ledger.json"
    if not path.exists():
        return False, None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False, "ledger.json no parsea"
    planes = data.get("planes") if isinstance(data, dict) else None
    if not isinstance(planes, dict):
        return False, "ledger.json sin la clave 'planes'"

    entry = planes.get(str(number))
    if not isinstance(entry, dict) or not entry.get("doc_sha256"):
        return False, None                             # nada que resellar para ESTE plan

    entry["doc_sha256"] = nuevo_sha
    entry["normalizado_por"] = "plan-263"
    entry["normalizado_en"] = datetime.now(timezone.utc).date().isoformat()

    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)
    return True, None


def _podar_baseline(filename: str) -> tuple[bool, str | None]:
    """Pata 3. Devuelve (podo_algo, error). "No existe" no es error (nada que
    podar). Malformado -> error, dispara rollback."""
    if not _BASELINE_PATH.exists():
        return False, None
    try:
        data = json.loads(_BASELINE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False, "plans_estado_baseline.json no parsea"
    sin_estado = data.get("sin_estado")
    if not isinstance(sin_estado, list):
        return False, "plans_estado_baseline.json sin la clave 'sin_estado'"
    if filename not in sin_estado:
        return False, None
    data["sin_estado"] = [f for f in sin_estado if f != filename]
    tmp = _BASELINE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, _BASELINE_PATH)
    return True, None


def apply_estado_migration(
    docs_dir: Path, items: list[dict], *, dry_run: bool = True
) -> dict:
    """Escribe la línea **Estado:** en los planes pedidos, UNO POR UNO
    (transacción F2.5). Ver contrato completo en el plan 263 F3. NUNCA lanza."""
    aplicados: list[str] = []
    omitidos: list[dict] = []
    diffs: dict[str, str] = {}
    ledger_resellado: list[str] = []
    baseline_podado: list[str] = []

    docs_dir_resuelto = docs_dir.resolve()

    for item in items:
        filename = item.get("filename")
        sha256_visto = item.get("sha256_visto")
        estado_elegido = item.get("estado_elegido")

        if not isinstance(filename, str) or not _PLAN_FILE_RE.match(filename):
            omitidos.append({"filename": str(filename), "razon": "nombre de archivo invalido"})
            continue

        path = docs_dir / filename
        try:
            if path.resolve().parent != docs_dir_resuelto:
                omitidos.append({"filename": filename, "razon": "nombre de archivo invalido"})
                continue
        except OSError:
            omitidos.append({"filename": filename, "razon": "nombre de archivo invalido"})
            continue

        if estado_elegido is not None and estado_elegido not in ESTADOS_ELEGIBLES:
            omitidos.append({"filename": filename, "razon": "estado elegido invalido"})
            continue

        if not path.exists():
            omitidos.append({"filename": filename, "razon": "archivo inexistente"})
            continue

        try:
            contenido_original = path.read_bytes()
        except OSError:
            omitidos.append({"filename": filename, "razon": "no se pudo leer el archivo"})
            continue

        sha_actual = hashlib.sha256(contenido_original).hexdigest()
        if not sha256_visto or sha_actual != sha256_visto:
            omitidos.append({"filename": filename, "razon": "cambio en disco desde la vista previa"})
            continue

        texto_original = contenido_original.decode("utf-8", errors="replace")

        if _ESTADO_RE.search(texto_original[:_HEADER_READ_CHARS]):
            omitidos.append({"filename": filename, "razon": "ya declara estado"})
            continue

        m = _PLAN_FILE_RE.match(filename)
        number = int(m.group(1))
        propuesta = infer_estado_con_evidencia({"number": number, "filename": filename}, docs_dir)

        if propuesta["confianza"] == "sin_evidencia":
            if estado_elegido not in ESTADOS_ELEGIBLES:
                omitidos.append({
                    "filename": filename,
                    "razon": "sin evidencia y sin estado elegido por el operador",
                })
                continue
            hoy = datetime.now(timezone.utc).date().isoformat()
            linea = (
                f"**Estado:** {estado_elegido} (normalizado {hoy}, Plan 263) — "
                "elegido por el operador, sin evidencia en el documento"
            )
            insert_after_line = _find_insert_after_line(texto_original)
        else:
            linea = propuesta["linea_a_insertar"]
            insert_after_line = propuesta["insert_after_line"]

        texto_nuevo = _insertar_linea(texto_original, insert_after_line, linea)
        diffs[filename] = _unified_diff(texto_original, texto_nuevo, filename)

        if dry_run:
            continue

        try:
            _escribir_atomico(path, texto_nuevo)
        except OSError:
            omitidos.append({"filename": filename, "razon": "no se pudo escribir el archivo"})
            continue

        nuevo_sha = hashlib.sha256(texto_nuevo.encode("utf-8")).hexdigest()
        hizo_resello, err_ledger = _resellar_ledger_si_corresponde(docs_dir, number, nuevo_sha)
        err_baseline = None
        podo_algo = False
        if err_ledger is None:
            podo_algo, err_baseline = _podar_baseline(filename)

        if err_ledger is not None or err_baseline is not None:
            razon = "rollback: no se pudo actualizar el ledger o el baseline"
            _escribir_atomico(path, texto_original)          # restaurar el .md
            logger.error("[plan263] rollback de normalizacion: %s (%s)", filename, razon)
            omitidos.append({"filename": filename, "razon": razon})
            continue

        aplicados.append(filename)
        if hizo_resello:
            ledger_resellado.append(filename)
        if podo_algo:
            baseline_podado.append(filename)

    if not dry_run and aplicados:
        plans_board._BOARD_CACHE = None      # invalidar cache (v2/C14)

    return {
        "ok": True,
        "aplicados": aplicados,
        "omitidos": omitidos,
        "diffs": diffs,
        "ledger_resellado": ledger_resellado,
        "baseline_podado": baseline_podado,
    }
