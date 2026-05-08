"""
scanner.py — Descubre y construye BatchProcess leyendo trunk/Batch/

Para cada carpeta de proceso:
  1. Localiza el .cs principal (el que contiene HayQueEjecSubProceso o el patrón Motor)
  2. Localiza el XML de configuración
  3. Parsea ambos y cruza la información
  4. Retorna lista de BatchProcess listos para el template engine

El descubrimiento es automático: si aparece una nueva carpeta de proceso
que siga los patrones conocidos, se detecta sin cambiar código.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from .cs_parser import parse_main_cs
from .model import BatchProcess, SubProcess
from .xml_parser import parse_xml_config

logger = logging.getLogger(__name__)

# Carpetas de trunk/Batch que NO son procesos batch (excluir)
_DEFAULT_EXCLUDES = {
    "Negocio",
    "Soluciones",
    "TestBD",
    "FlujosGMR",
    "FlujosGMRJ",
    "ProxDiaHabil",
    "RecBatch2014",
}

# Indicadores de que una carpeta es un proceso batch
_BATCH_INDICATORS = [
    "HayQueEjecSubProceso",
    "cGlobales.nEjecuta",
    "EjecutarMotor",
]


def _is_batch_process_folder(folder: Path) -> bool:
    """
    Heurística rápida: ¿es esta carpeta un proceso batch?
    Busca un .csproj + al menos un .cs con indicadores de proceso.
    """
    if not any(folder.glob("*.csproj")):
        return False
    for cs_file in folder.glob("*.cs"):
        if cs_file.name == "Program.cs":
            continue
        try:
            content = cs_file.read_text(encoding="utf-8", errors="replace")
            if any(ind in content for ind in _BATCH_INDICATORS):
                return True
        except OSError:
            continue
    return False


def _find_main_cs(folder: Path) -> Optional[Path]:
    """
    Localiza el .cs principal de un proceso batch.
    Criterio: el que contiene HayQueEjecSubProceso o cGlobales.nEjecuta.
    Excluye Program.cs (solo contiene el punto de entrada main).
    """
    candidates = []
    for cs_file in folder.glob("*.cs"):
        if cs_file.name == "Program.cs":
            continue
        try:
            content = cs_file.read_text(encoding="utf-8", errors="replace")
            if any(ind in content for ind in _BATCH_INDICATORS):
                candidates.append(cs_file)
        except OSError:
            continue

    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) > 1:
        # Prefiere el que tenga más ocurrencias de los indicadores
        return max(
            candidates,
            key=lambda p: sum(
                p.read_text(encoding="utf-8", errors="replace").count(ind)
                for ind in _BATCH_INDICATORS
            ),
        )
    return None


def _find_xml_config(folder: Path) -> Optional[Path]:
    """
    Busca el XML de configuración del proceso.
    Patrón: cualquier .xml en la misma carpeta (excluye App.config, *.csproj.user).
    """
    xml_files = [
        x for x in folder.glob("*.xml")
        if x.suffix.lower() == ".xml"
        and "app.config" not in x.name.lower()
    ]
    if len(xml_files) == 1:
        return xml_files[0]
    if xml_files:
        # Prioriza el que tenga el mismo nombre que la carpeta
        folder_name = folder.name.lower()
        for xf in xml_files:
            if xf.stem.lower() in (folder_name, folder_name.replace("rs", "")):
                return xf
        return xml_files[0]
    return None


def _cross_reference_xml(
    sub_processes: list[SubProcess],
    xml_sub_procs: dict[str, bool],
) -> None:
    """
    Cruza el estado habilitado/deshabilitado del XML con los sub-procesos
    detectados en el .cs. Matching case-insensitive.
    """
    xml_lower = {k.lower(): v for k, v in xml_sub_procs.items()}
    for sp in sub_processes:
        key = sp.name.lower()
        if key in xml_lower:
            sp.enabled_in_xml = xml_lower[key]
        else:
            # Intenta sin prefijos como "RS" o "RS_"
            stripped = key.lstrip("rs_").lstrip("rs")
            for xml_key, xml_val in xml_lower.items():
                if xml_key.lstrip("rs_").lstrip("rs") == stripped:
                    sp.enabled_in_xml = xml_val
                    break


def scan_batch_folder(
    batch_root: Path,
    negocio_root: Path,
    excluded: Optional[set[str]] = None,
) -> list[BatchProcess]:
    """
    Escanea batch_root y retorna la lista de BatchProcess descubiertos.

    Args:
        batch_root  : Ruta a trunk/Batch/
        negocio_root: Ruta a trunk/Batch/Negocio/
        excluded    : Nombres de carpetas a excluir (default: _DEFAULT_EXCLUDES)
    """
    if excluded is None:
        excluded = _DEFAULT_EXCLUDES

    processes: list[BatchProcess] = []

    if not batch_root.is_dir():
        logger.error("batch_root no existe: %s", batch_root)
        return processes

    for folder in sorted(batch_root.iterdir()):
        if not folder.is_dir():
            continue
        if folder.name in excluded:
            logger.debug("Excluida: %s", folder.name)
            continue
        if not _is_batch_process_folder(folder):
            logger.debug("No es proceso batch: %s", folder.name)
            continue

        logger.info("Procesando: %s", folder.name)

        main_cs = _find_main_cs(folder)
        if main_cs is None:
            logger.warning("%s: no se encontró .cs principal, omitiendo.", folder.name)
            continue

        xml_config = _find_xml_config(folder)

        # Parsear XML
        xml_sub_procs: dict[str, bool] = {}
        xml_parameters: dict[str, str] = {}
        all_warnings: list[str] = []

        if xml_config:
            xml_sub_procs, xml_parameters, xml_warns = parse_xml_config(xml_config)
            all_warnings.extend(xml_warns)
        else:
            all_warnings.append(f"XML de configuración no encontrado en {folder.name}/")

        # Parsear .cs
        cs_result = parse_main_cs(main_cs, negocio_root)
        all_warnings.extend(cs_result.warnings)

        # Cruzar datos XML ↔ CS
        _cross_reference_xml(cs_result.sub_processes, xml_sub_procs)

        batch = BatchProcess(
            name=folder.name,
            main_class=cs_result.main_class,
            main_cs_path=main_cs,
            xml_config_path=xml_config,
            negocio_root=negocio_root,
            sub_processes=cs_result.sub_processes,
            xml_parameters=xml_parameters,
            warnings=all_warnings,
        )
        processes.append(batch)
        logger.info(
            "  → %d sub-proceso(s) detectado(s): %s",
            len(batch.sub_processes),
            [sp.name for sp in batch.sub_processes],
        )

    return processes


def scan_single_process(
    process_name: str,
    batch_root: Path,
    negocio_root: Path,
) -> Optional[BatchProcess]:
    """
    Escanea un único proceso por nombre (nombre de carpeta).
    """
    folder = batch_root / process_name
    if not folder.is_dir():
        logger.error("Carpeta no encontrada: %s", folder)
        return None

    main_cs = _find_main_cs(folder)
    if main_cs is None:
        logger.warning("%s: no se encontró .cs principal.", process_name)
        return None

    xml_config = _find_xml_config(folder)
    xml_sub_procs, xml_parameters, xml_warns = (
        parse_xml_config(xml_config) if xml_config else ({}, {}, [])
    )

    cs_result = parse_main_cs(main_cs, negocio_root)
    _cross_reference_xml(cs_result.sub_processes, xml_sub_procs)

    all_warns = xml_warns + cs_result.warnings

    return BatchProcess(
        name=process_name,
        main_class=cs_result.main_class,
        main_cs_path=main_cs,
        xml_config_path=xml_config,
        negocio_root=negocio_root,
        sub_processes=cs_result.sub_processes,
        xml_parameters=xml_parameters,
        warnings=all_warns,
    )
