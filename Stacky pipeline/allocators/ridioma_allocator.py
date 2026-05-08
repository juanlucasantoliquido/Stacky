"""
ridioma_allocator — Asignación transaccional de IDs RIDIOMA.

Lee el archivo maestro ``600804 - Inserts RIDIOMA.sql``, calcula el próximo
IDTEXTO libre (max + 1), y opcionalmente agrega los nuevos INSERTs formateados
con trazabilidad ADO.

Uso:
    from allocators.ridioma_allocator import allocate, RidiomaEntry

    entry = allocate(
        ado_id=1234,
        fecha="2026-05-02",
        textos={"ESP": "Fecha inválida", "ENG": "Invalid date", "POR": "Data inválida"},
        contexto_uso="Validación en GuardarConvenio",
        master_path="trunk/BD/1 - Inicializacion BD/600804 - Inserts RIDIOMA.sql",
        apply=False,  # dry-run
    )
    print(entry.idtexto)       # próximo ID libre
    print(entry.sql_inserts)   # SQL listo para append
    print(entry.code_const)    # constante C# sugerida
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Optional

try:
    import fcntl as _fcntl  # Unix only
    _HAS_FCNTL = True
except ImportError:
    _fcntl = None  # type: ignore
    _HAS_FCNTL = False

# ── Regex para parsear INSERTs del archivo maestro ────────────────────────────

# Captura: IDIDIOMA, IDTEXTO, IDDESCRIPCION
_RE_INSERT = re.compile(
    r"""insert\s+into\s+RIDIOMA\s*\(
        \s*IDIDIOMA\s*,\s*IDTEXTO\s*,\s*IDDESCRIPCION\s*
    \)\s*values\s*\(
        \s*'([^']+)'\s*,\s*(\d+)\s*,\s*(.+?)\s*
    \)\s*;""",
    re.IGNORECASE | re.VERBOSE,
)

# Detecta línea comentada
_RE_COMMENT_LINE = re.compile(r"^\s*--")

# Detecta descripción de clave compuesta ya existente: ADO + texto (para dedupe)
_RE_TRACE_COMMENT = re.compile(r"--\s*ADO-(\d+)\s*\|")


# ── Dataclasses ───────────────────────────────────────────────────────────────


@dataclass
class RidiomaEntry:
    """Resultado de una asignación de ID RIDIOMA."""

    idtexto: int
    ado_id: int
    textos: dict[str, str]
    contexto_uso: str
    sql_inserts: str
    code_const: str
    file_path: Optional[str] = None
    line_added: Optional[int] = None
    applied: bool = False
    already_existed: bool = False
    existing_idtexto: Optional[int] = None


# ── Helpers internos ──────────────────────────────────────────────────────────


def _read_master(master_path: str) -> str:
    if not os.path.exists(master_path):
        raise FileNotFoundError(
            f"Archivo maestro RIDIOMA no encontrado: {master_path}"
        )
    with open(master_path, encoding="utf-8", errors="replace") as fh:
        return fh.read()


def _extract_max_id(content: str) -> int:
    """Devuelve el máximo IDTEXTO encontrado en el archivo."""
    ids = [int(m.group(2)) for m in _RE_INSERT.finditer(content)]
    return max(ids) if ids else 0


def _check_duplicate(
    content: str,
    ado_id: int,
    textos: dict[str, str],
) -> Optional[int]:
    """
    Busca si ya existe una entrada con el mismo ado_id y texto ESP (o el primer
    idioma disponible). Devuelve el IDTEXTO existente o None.
    """
    first_text = textos.get("ESP") or next(iter(textos.values()), "")
    if not first_text:
        return None

    first_text_clean = first_text.strip().lower()

    for m in _RE_INSERT.finditer(content):
        descripcion_raw = m.group(3).strip()
        # Normalizar descripcion: puede ser 'texto' o 'parte' + char(N) + 'parte'
        desc_clean = _normalize_descripcion(descripcion_raw).lower()
        if desc_clean == first_text_clean:
            return int(m.group(2))
    return None


def _normalize_descripcion(raw: str) -> str:
    """
    Convierte una descripción que puede incluir `char(N)` a texto plano.
    Solo para comparación; no para escritura.
    """
    result = raw.strip("'")
    result = re.sub(r"'\s*\+\s*char\((\d+)\)\s*\+\s*'", lambda m: chr(int(m.group(1))), result)
    result = re.sub(r"char\((\d+)\)", lambda m: chr(int(m.group(1))), result)
    result = result.strip("'")
    return result


def _encode_descripcion(text: str) -> str:
    """
    Codifica el texto para la sentencia SQL de RIDIOMA.
    Usa `char(N)` para caracteres no-ASCII; el resto va entre comillas simples.
    """
    parts: list[str] = []
    current_ascii = ""
    for ch in text:
        if ord(ch) < 128:
            current_ascii += ch
        else:
            if current_ascii:
                parts.append(f"'{current_ascii}'")
                current_ascii = ""
            parts.append(f"char({ord(ch)})")
    if current_ascii:
        parts.append(f"'{current_ascii}'")
    if not parts:
        return "''"
    return " + ".join(parts)


def _build_insert_block(
    ado_id: int,
    fecha: str,
    idtexto: int,
    textos: dict[str, str],
    contexto_uso: str,
) -> str:
    """Construye el bloque SQL con trazabilidad para agregar al maestro."""
    lines: list[str] = []
    # Comentario de trazabilidad (R1 canónico)
    lines.append(f"-- ADO-{ado_id} | {fecha} | {contexto_uso}")
    # Preferir orden: ESP, ENG, POR + cualquier otro
    orden = ["ESP", "ENG", "POR"]
    ordered_keys = orden + [k for k in textos if k not in orden]
    for idioma in ordered_keys:
        if idioma not in textos:
            continue
        desc = _encode_descripcion(textos[idioma])
        lines.append(
            f"insert into RIDIOMA (IDIDIOMA, IDTEXTO, IDDESCRIPCION) values ('{idioma}',{idtexto},{desc});"
        )
    return "\n".join(lines)


def _build_code_const(idtexto: int) -> str:
    """Genera la constante C# sugerida para referenciar el ID."""
    return f"public const int m{idtexto} = {idtexto};"


# ── API pública ───────────────────────────────────────────────────────────────


def allocate(
    ado_id: int,
    fecha: str,
    textos: dict[str, str],
    contexto_uso: str,
    master_path: str,
    apply: bool = False,
) -> RidiomaEntry:
    """
    Asigna el próximo IDTEXTO libre en el archivo maestro RIDIOMA.

    Parámetros
    ----------
    ado_id:
        ID del work item ADO para trazabilidad.
    fecha:
        Fecha en formato YYYY-MM-DD.
    textos:
        Diccionario ``{idioma: texto}`` con al menos ESP. Ej:
        ``{"ESP": "Fecha inválida", "ENG": "Invalid date", "POR": "Data inválida"}``.
    contexto_uso:
        Descripción breve del contexto de uso (ej: "Validación en GuardarConvenio").
    master_path:
        Ruta absoluta al archivo maestro RIDIOMA.sql.
    apply:
        Si True, agrega el bloque al final del archivo (con lock advisory).
        Si False (dry-run), solo devuelve el SQL sin tocar el archivo.

    Devuelve
    --------
    RidiomaEntry con todos los campos populados.

    Excepciones
    -----------
    FileNotFoundError:
        Si master_path no existe.
    ValueError:
        Si ``textos`` está vacío o falta el idioma ESP.
    """
    if not textos:
        raise ValueError("textos no puede estar vacío")
    if "ESP" not in textos:
        raise ValueError("textos debe incluir al menos el idioma 'ESP'")

    if not apply:
        # Dry-run — sin lock
        content = _read_master(master_path)
        existing_id = _check_duplicate(content, ado_id, textos)
        if existing_id is not None:
            sql_block = _build_insert_block(ado_id, fecha, existing_id, textos, contexto_uso)
            return RidiomaEntry(
                idtexto=existing_id,
                ado_id=ado_id,
                textos=textos,
                contexto_uso=contexto_uso,
                sql_inserts=sql_block,
                code_const=_build_code_const(existing_id),
                file_path=master_path,
                applied=False,
                already_existed=True,
                existing_idtexto=existing_id,
            )
        next_id = _extract_max_id(content) + 1
        sql_block = _build_insert_block(ado_id, fecha, next_id, textos, contexto_uso)
        return RidiomaEntry(
            idtexto=next_id,
            ado_id=ado_id,
            textos=textos,
            contexto_uso=contexto_uso,
            sql_inserts=sql_block,
            code_const=_build_code_const(next_id),
            file_path=master_path,
            applied=False,
            already_existed=False,
        )

    # apply=True — con lock advisory para evitar race conditions
    lock_path = master_path + ".lock"
    with open(lock_path, "w", encoding="utf-8") as lock_fh:
        if _HAS_FCNTL:
            try:
                _fcntl.flock(lock_fh, _fcntl.LOCK_EX)
            except OSError:
                pass

        try:
            content = _read_master(master_path)
            existing_id = _check_duplicate(content, ado_id, textos)
            if existing_id is not None:
                sql_block = _build_insert_block(ado_id, fecha, existing_id, textos, contexto_uso)
                return RidiomaEntry(
                    idtexto=existing_id,
                    ado_id=ado_id,
                    textos=textos,
                    contexto_uso=contexto_uso,
                    sql_inserts=sql_block,
                    code_const=_build_code_const(existing_id),
                    file_path=master_path,
                    applied=False,
                    already_existed=True,
                    existing_idtexto=existing_id,
                )

            next_id = _extract_max_id(content) + 1
            sql_block = _build_insert_block(ado_id, fecha, next_id, textos, contexto_uso)

            # Append al final del archivo
            with open(master_path, "a", encoding="utf-8") as fh:
                fh.write("\n" + sql_block + "\n")

            # Calcular línea aproximada
            line_added = content.count("\n") + 2

            return RidiomaEntry(
                idtexto=next_id,
                ado_id=ado_id,
                textos=textos,
                contexto_uso=contexto_uso,
                sql_inserts=sql_block,
                code_const=_build_code_const(next_id),
                file_path=master_path,
                line_added=line_added,
                applied=True,
                already_existed=False,
            )
        finally:
            if _HAS_FCNTL:
                try:
                    _fcntl.flock(lock_fh, _fcntl.LOCK_UN)
                except OSError:
                    pass
