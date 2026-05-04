"""
xml_parser.py — Parsea el XML de configuración de un proceso Batch.

Lee etiquetas <Procesos> y <Parametros> del XML de inicialización
(ej: RSProcIN.xml, RSProcOUT.xml) y extrae:
  - Sub-procesos habilitados/deshabilitados
  - Parámetros de configuración del proceso
"""
from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def parse_xml_config(xml_path: Path) -> tuple[dict[str, bool], dict[str, str], list[str]]:
    """
    Parsea el XML de configuración de un proceso batch.

    Returns:
        sub_procs : dict nombre→bool  (True = habilitado, valor "1")
        parameters: dict nombre→valor (strings de <Parametros>)
        warnings  : lista de mensajes no fatales
    """
    sub_procs: dict[str, bool] = {}
    parameters: dict[str, str] = {}
    warnings: list[str] = []

    if not xml_path or not xml_path.is_file():
        warnings.append(f"XML de config no encontrado: {xml_path}")
        return sub_procs, parameters, warnings

    try:
        tree = ET.parse(str(xml_path))
    except ET.ParseError as exc:
        warnings.append(f"Error al parsear XML {xml_path.name}: {exc}")
        # Intento de recuperación: limpiar declaraciones mal formadas
        try:
            raw = xml_path.read_text(encoding="utf-8", errors="replace")
            # Elimina doctype inline si existe
            raw = re.sub(r"<!DOCTYPE[^>]*>", "", raw)
            root = ET.fromstring(raw)
            tree_root = root
        except Exception:
            return sub_procs, parameters, warnings
    else:
        tree_root = tree.getroot()

    # ── <Procesos> ──────────────────────────────────────────────────────────
    procesos_node = tree_root.find("Procesos")
    if procesos_node is not None:
        for child in procesos_node:
            tag = child.tag.strip()
            val = (child.text or "").strip()
            # "1" = habilitado, cualquier otra cosa = deshabilitado
            sub_procs[tag] = (val == "1")
    else:
        warnings.append(f"Nodo <Procesos> no encontrado en {xml_path.name}")

    # ── <Parametros> ────────────────────────────────────────────────────────
    params_node = tree_root.find("Parametros")
    if params_node is not None:
        for child in params_node:
            tag = child.tag.strip()
            val = (child.text or "").strip()
            if tag and val:
                parameters[tag] = val

    logger.debug(
        "XML %s: sub_procs=%s params=%s",
        xml_path.name,
        list(sub_procs.keys()),
        list(parameters.keys()),
    )
    return sub_procs, parameters, warnings
