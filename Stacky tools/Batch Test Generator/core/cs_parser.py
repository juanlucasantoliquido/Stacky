"""
cs_parser.py — Extrae metadata estructural de archivos C# de procesos Batch.

Cubre las 3 variantes detectadas en RSPacifico:

  Variante A — const int + HayQueEjecSubProceso(NOMBRE)
    RSProcIN, RSNovMasivas, RSHistoSIC, etc.

  Variante B — enum Subproceso + HayQueEjecSubProceso(Subproceso.NOMBRE)
    RSProcOUT, RSComi, etc.

  Variante C — cGlobales.nEjecutaXxx == 1
    Motor, MotorJ (sin HayQueEjecSubProceso)

Para cada sub-proceso detectado extrae:
  - Nombre de la constante/enum member
  - Valor numérico
  - Clase de negocio instanciada (namespace.Clase)
  - Método/s llamados sobre esa clase
  - Bloque if completo (raw) para contexto futuro
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .model import BizMethod, SubProcess, SubprocType

logger = logging.getLogger(__name__)

# ─── PATRONES REGEX ──────────────────────────────────────────────────────────

# Variante A: private const int NOMBRE = N;
_RE_CONST_INT = re.compile(
    r"private\s+const\s+int\s+(\w+)\s*=\s*(\d+)\s*;",
    re.MULTILINE,
)

# Variante B: enum Subproceso { NOMBRE = N, NOMBRE2, ... }
_RE_ENUM_BLOCK = re.compile(
    r"private\s+enum\s+\w+\s*\{([^}]+)\}",
    re.MULTILINE | re.DOTALL,
)
# Un miembro del enum: NOMBRE [= N] [,]
_RE_ENUM_MEMBER = re.compile(
    r"(\w+)\s*(?:=\s*(\d+))?",
)

# Variante C: if (cGlobales.nEjecutaXxx == 1)
_RE_GLOBAL_FLAG = re.compile(
    r"if\s*\(\s*cGlobales\.(\w+)\s*==\s*1\s*\)",
    re.MULTILINE,
)

# HayQueEjecSubProceso — ambas variantes A y B
_RE_HAYQUE_A = re.compile(
    r"HayQueEjecSubProceso\(\s*(\w+)\s*\)",   # NOMBRE
)
_RE_HAYQUE_B = re.compile(
    r"HayQueEjecSubProceso\(\s*\w+\.(\w+)\s*\)",   # Subproceso.NOMBRE
)

# Instanciación de clase de negocio: new Namespace.Clase(conn)
_RE_BIZ_NEW = re.compile(
    r"new\s+([\w]+)\.([\w]+)\s*\(\s*conn\s*\)",
)

# Llamada a método sobre variable: vNombre.Metodo(
_RE_METHOD_CALL = re.compile(
    r"\b\w+\.([\w]+)\s*\(",
)

# Declaración de método público en clase de negocio
_RE_PUBLIC_METHOD = re.compile(
    r"public\s+([\w<>\[\]]+)\s+(\w+)\s*\(([^)]*)\)\s*(?:throws\s+\w+\s*)?\{",
    re.MULTILINE,
)

# ─── UTILIDADES DE EXTRACCIÓN DE BLOQUES ─────────────────────────────────────


def _extract_if_block(source: str, if_start: int) -> str:
    """
    Extrae el bloque completo de un if{...} a partir de la posición de 'if'.
    Maneja llaves anidadas.
    """
    # Encuentra la primera llave abierta después del if
    brace_start = source.find("{", if_start)
    if brace_start == -1:
        return source[if_start : if_start + 300]

    depth = 0
    pos = brace_start
    while pos < len(source):
        ch = source[pos]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return source[if_start : pos + 1]
        pos += 1
    return source[if_start:]


def _find_if_block_for_subproc(source: str, subproc_name: str) -> Optional[str]:
    """
    Localiza el bloque if completo que contiene una llamada a
    HayQueEjecSubProceso con el nombre de sub-proceso dado.
    Cubre variantes A (NOMBRE) y B (Subproceso.NOMBRE).
    """
    patterns = [
        re.compile(rf"HayQueEjecSubProceso\(\s*{re.escape(subproc_name)}\s*\)"),
        re.compile(rf"HayQueEjecSubProceso\(\s*\w+\.{re.escape(subproc_name)}\s*\)"),
    ]
    for pat in patterns:
        m = pat.search(source)
        if m:
            # Retrocedemos hasta el 'if' que precede la llamada
            if_pos = source.rfind("if", 0, m.start())
            if if_pos != -1:
                return _extract_if_block(source, if_pos)
    return None


def _find_if_block_for_global(source: str, flag_name: str) -> Optional[str]:
    pat = re.compile(rf"if\s*\(\s*cGlobales\.{re.escape(flag_name)}\s*==\s*1\s*\)")
    m = pat.search(source)
    if m:
        return _extract_if_block(source, m.start())
    return None


# ─── PARSER DE CLASE DE NEGOCIO ──────────────────────────────────────────────


def parse_biz_class(
    biz_class_name: str,
    biz_namespace: str,
    negocio_root: Path,
) -> list[BizMethod]:
    """
    Busca la clase de negocio en negocio_root/BusXxx/Xxx.cs y extrae
    sus métodos públicos con tipo de retorno.
    """
    methods: list[BizMethod] = []

    # Estrategia de búsqueda de la carpeta: BusNamespace → BusClassName
    biz_folder = negocio_root / biz_namespace
    candidates = [
        biz_folder / f"{biz_class_name}.cs",
        biz_folder / f"{biz_class_name}s.cs",  # pluralización común
        *((list(biz_folder.glob("*.cs"))) if biz_folder.is_dir() else []),
    ]

    # Búsqueda ampliada si la carpeta exacta no existe
    if not biz_folder.is_dir():
        # Busca carpetas que empiecen con el mismo prefijo
        for folder in negocio_root.iterdir():
            if folder.is_dir() and folder.name.lower().startswith(biz_namespace.lower()[:4]):
                candidates += list(folder.glob("*.cs"))

    source = None
    for path in candidates:
        if isinstance(path, Path) and path.is_file():
            try:
                raw = path.read_text(encoding="utf-8", errors="replace")
                # Verificar que la clase buscada está definida en este archivo (no sólo incluida)
                if re.search(rf"\bclass\s+{re.escape(biz_class_name)}\b", raw):
                    source = raw
                    logger.debug("Clase de negocio encontrada: %s", path)
                    break
            except OSError:
                continue

    if source is None:
        logger.warning("No se encontró la clase %s en %s", biz_class_name, negocio_root)
        return methods

    # Eliminar comentarios de bloque /* ... */ para no parsear código comentado
    source_clean = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    # Eliminar comentarios de línea // ... (solo hasta fin de línea)
    source_clean = re.sub(r"//[^\n]*", "", source_clean)

    for m in _RE_PUBLIC_METHOD.finditer(source_clean):
        ret_type = m.group(1).strip()
        method_name = m.group(2).strip()
        params_raw = m.group(3).strip()

        # Filtra constructores y métodos de infraestructura genérica
        if method_name in (biz_class_name, "Dispose", "ToString", "GetHashCode", "Equals"):
            continue

        params = []
        param_types = []
        if params_raw:
            for p in params_raw.split(","):
                p = p.strip()
                # Elimina modificadores: ref, out, params
                p = re.sub(r"^\s*(ref|out|params)\s+", "", p).strip()
                parts = p.rsplit(None, 1)
                if len(parts) == 2:
                    param_types.append(parts[0].strip())
                    params.append(parts[1].strip())
                else:
                    param_types.append("object")
                    params.append(p)

        methods.append(BizMethod(name=method_name, return_type=ret_type, params=params, param_types=param_types))

    return methods


# ─── PARSER PRINCIPAL DEL .cs DE PROCESO ─────────────────────────────────────


@dataclass
class CsParseResult:
    sub_processes: list[SubProcess] = field(default_factory=list)
    main_class: str = ""
    warnings: list[str] = field(default_factory=list)


def parse_main_cs(cs_path: Path, negocio_root: Path) -> CsParseResult:
    """
    Parsea el .cs principal de un proceso Batch (ProcIn.cs, NovMasivas.cs, etc.)
    y extrae todos los sub-procesos con su metadata.
    """
    result = CsParseResult()

    if not cs_path.is_file():
        result.warnings.append(f"Archivo .cs no encontrado: {cs_path}")
        return result

    source = cs_path.read_text(encoding="utf-8", errors="replace")

    # ── Nombre de la clase principal ─────────────────────────────────────────
    m_class = re.search(r"class\s+(\w+)\s*(?::\s*\w+)?", source)
    if m_class:
        result.main_class = m_class.group(1)

    # ── Determinar variante ───────────────────────────────────────────────────
    has_hayque = bool(_RE_HAYQUE_A.search(source) or _RE_HAYQUE_B.search(source))
    has_enum = bool(_RE_ENUM_BLOCK.search(source))
    has_global = bool(_RE_GLOBAL_FLAG.search(source))

    if has_enum:
        result.sub_processes += _parse_variant_enum(source, negocio_root, result.warnings)
    elif has_hayque:
        result.sub_processes += _parse_variant_const(source, negocio_root, result.warnings)

    if has_global:
        result.sub_processes += _parse_variant_global(source, negocio_root, result.warnings)

    if not result.sub_processes:
        result.warnings.append(
            f"No se detectaron sub-procesos en {cs_path.name}. "
            "Puede ser un proceso sin sub-procesos o con un patrón no cubierto."
        )

    return result


# ─── VARIANTE A: const int ────────────────────────────────────────────────────


def _parse_variant_const(
    source: str, negocio_root: Path, warnings: list[str]
) -> list[SubProcess]:
    """Variante A: private const int NOMBRE = N + HayQueEjecSubProceso(NOMBRE)."""
    sub_procs: list[SubProcess] = []

    # Construye mapa nombre → valor
    const_map: dict[str, int] = {}
    for m in _RE_CONST_INT.finditer(source):
        const_map[m.group(1)] = int(m.group(2))

    # Encuentra todos los HayQueEjecSubProceso(NOMBRE) — deduplicar por nombre
    seen: set[str] = set()
    for m in _RE_HAYQUE_A.finditer(source):
        name = m.group(1)
        if name in seen:
            continue
        seen.add(name)
        if name not in const_map:
            warnings.append(f"Constante no encontrada para sub-proceso '{name}'")
            const_val = 0
        else:
            const_val = const_map[name]

        block = _find_if_block_for_subproc(source, name) or ""
        biz_ns, biz_cls, biz_methods = _extract_biz_info(block, negocio_root, warnings)

        sub_procs.append(
            SubProcess(
                name=name,
                constant_value=const_val,
                enabled_in_xml=None,
                subproc_type=SubprocType.CONST_INT,
                biz_namespace=biz_ns,
                biz_class=biz_cls,
                biz_methods=biz_methods,
                dalc_class=_guess_dalc(biz_cls, block),
                raw_block=block,
            )
        )

    return sub_procs


# ─── VARIANTE B: enum ─────────────────────────────────────────────────────────


def _parse_variant_enum(
    source: str, negocio_root: Path, warnings: list[str]
) -> list[SubProcess]:
    """Variante B: enum Subproceso { NOMBRE = N } + HayQueEjecSubProceso(Subproceso.NOMBRE)."""
    sub_procs: list[SubProcess] = []

    # Extrae el bloque del enum
    m_enum = _RE_ENUM_BLOCK.search(source)
    if not m_enum:
        return sub_procs

    enum_body = m_enum.group(1)
    enum_map: dict[str, int] = {}
    current_val = 1
    for m in _RE_ENUM_MEMBER.finditer(enum_body):
        member_name = m.group(1)
        if member_name in ("", "//"):
            continue
        if m.group(2):
            current_val = int(m.group(2))
        enum_map[member_name] = current_val
        current_val += 1

    # Encuentra HayQueEjecSubProceso(Subproceso.NOMBRE) — deduplicar por nombre
    seen: set[str] = set()
    for m in _RE_HAYQUE_B.finditer(source):
        name = m.group(1)
        if name in seen:
            continue
        seen.add(name)

        const_val = enum_map.get(name, 0)
        if const_val == 0:
            warnings.append(f"Enum member no encontrado para sub-proceso '{name}'")

        block = _find_if_block_for_subproc(source, name) or ""
        biz_ns, biz_cls, biz_methods = _extract_biz_info(block, negocio_root, warnings)

        sub_procs.append(
            SubProcess(
                name=name,
                constant_value=const_val,
                enabled_in_xml=None,
                subproc_type=SubprocType.ENUM,
                biz_namespace=biz_ns,
                biz_class=biz_cls,
                biz_methods=biz_methods,
                dalc_class=_guess_dalc(biz_cls, block),
                raw_block=block,
            )
        )

    return sub_procs


# ─── VARIANTE C: cGlobales.nEjecutaXxx ───────────────────────────────────────


def _parse_variant_global(
    source: str, negocio_root: Path, warnings: list[str]
) -> list[SubProcess]:
    """Variante C: if (cGlobales.nEjecutaXxx == 1)."""
    sub_procs: list[SubProcess] = []

    seen: set[str] = set()
    for m in _RE_GLOBAL_FLAG.finditer(source):
        flag_name = m.group(1)
        if flag_name in seen:
            continue
        seen.add(flag_name)

        block = _find_if_block_for_global(source, flag_name) or ""
        biz_ns, biz_cls, biz_methods = _extract_biz_info(block, negocio_root, warnings)

        sub_procs.append(
            SubProcess(
                name=flag_name,
                constant_value=1,
                enabled_in_xml=None,
                subproc_type=SubprocType.GLOBAL_FLAG,
                biz_namespace=biz_ns,
                biz_class=biz_cls,
                biz_methods=biz_methods,
                dalc_class=_guess_dalc(biz_cls, block),
                raw_block=block,
            )
        )

    return sub_procs


# ─── HELPERS ─────────────────────────────────────────────────────────────────


def _extract_biz_info(
    block: str, negocio_root: Path, warnings: list[str]
) -> tuple[str, str, list[BizMethod]]:
    """Extrae namespace, clase y métodos de un bloque if."""
    biz_ns = ""
    biz_cls = ""
    biz_methods: list[BizMethod] = []

    m_new = _RE_BIZ_NEW.search(block)
    if m_new:
        biz_ns = m_new.group(1)
        biz_cls = m_new.group(2)
        biz_methods = parse_biz_class(biz_cls, biz_ns, negocio_root)
    else:
        warnings.append("No se encontró instanciación de clase de negocio en el bloque.")

    return biz_ns, biz_cls, biz_methods


def _guess_dalc(biz_class: str, block: str) -> Optional[str]:
    """
    Intenta inferir la clase DALC buscando 'XxxDalc' en el bloque.
    Si el archivo de negocio existe se confirmaría, aquí usamos heurística.
    """
    m = re.search(rf"\b(\w*{re.escape(biz_class)}Dalc)\b", block)
    if m:
        return m.group(1)
    # Heurística: ClaseDalc
    dalc_candidate = f"{biz_class}Dalc"
    return dalc_candidate
