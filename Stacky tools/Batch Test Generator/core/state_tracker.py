"""
state_tracker.py — Snapshot del estado escaneado de trunk/Batch.

Persiste en btg-state.json el último scan para comparar contra la realidad actual.
Permite detectar:
  - Nuevos procesos batch (carpeta nueva)
  - Procesos eliminados
  - Nuevos sub-procesos dentro de un proceso existente
  - Sub-procesos eliminados
  - Cambios en métodos de negocio (firma diferente)
  - Cambios en los archivos fuente (.cs, .xml) por mtime/hash
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

from .model import BatchProcess, BizMethod, SubProcess

logger = logging.getLogger(__name__)

_STATE_FILE = "btg-state.json"
_STATE_VERSION = 2


# ─── MODELOS DE ESTADO ────────────────────────────────────────────────────────

@dataclass
class MethodSnapshot:
    name: str
    return_type: str
    params: list[str]


@dataclass
class SubProcSnapshot:
    name: str
    constant_value: int
    subproc_type: str
    biz_namespace: str
    biz_class: str
    dalc_class: Optional[str]
    methods: list[MethodSnapshot]


@dataclass
class ProcessSnapshot:
    name: str
    main_class: str
    cs_hash: str          # sha256 del .cs principal
    xml_hash: str         # sha256 del .xml de config (o "")
    sub_processes: list[SubProcSnapshot]


@dataclass
class StateFile:
    version: int
    batch_root: str
    processes: dict[str, ProcessSnapshot] = field(default_factory=dict)


# ─── SERIALIZACIÓN ────────────────────────────────────────────────────────────


def _method_to_snap(m: BizMethod) -> MethodSnapshot:
    return MethodSnapshot(name=m.name, return_type=m.return_type, params=list(m.params))


def _subproc_to_snap(sp: SubProcess) -> SubProcSnapshot:
    return SubProcSnapshot(
        name=sp.name,
        constant_value=sp.constant_value,
        subproc_type=sp.subproc_type.value,
        biz_namespace=sp.biz_namespace,
        biz_class=sp.biz_class,
        dalc_class=sp.dalc_class,
        methods=[_method_to_snap(m) for m in sp.biz_methods],
    )


def _process_to_snap(bp: BatchProcess) -> ProcessSnapshot:
    cs_hash = _file_hash(bp.main_cs_path)
    xml_hash = _file_hash(bp.xml_config_path) if bp.xml_config_path else ""
    return ProcessSnapshot(
        name=bp.name,
        main_class=bp.main_class,
        cs_hash=cs_hash,
        xml_hash=xml_hash,
        sub_processes=[_subproc_to_snap(sp) for sp in bp.sub_processes],
    )


def _file_hash(path: Optional[Path]) -> str:
    if path is None or not path.is_file():
        return ""
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()[:16]
    except OSError:
        return ""


def _to_dict(obj) -> dict:
    """Serializa dataclass recursivamente."""
    if isinstance(obj, (MethodSnapshot, SubProcSnapshot, ProcessSnapshot, StateFile)):
        return {k: _to_dict(v) for k, v in asdict(obj).items()}
    if isinstance(obj, list):
        return [_to_dict(i) for i in obj]
    if isinstance(obj, dict):
        return {k: _to_dict(v) for k, v in obj.items()}
    return obj


def _from_dict_process(d: dict) -> ProcessSnapshot:
    sps = [
        SubProcSnapshot(
            name=s["name"],
            constant_value=s["constant_value"],
            subproc_type=s["subproc_type"],
            biz_namespace=s["biz_namespace"],
            biz_class=s["biz_class"],
            dalc_class=s.get("dalc_class"),
            methods=[
                MethodSnapshot(m["name"], m["return_type"], m.get("params", []))
                for m in s.get("methods", [])
            ],
        )
        for s in d.get("sub_processes", [])
    ]
    return ProcessSnapshot(
        name=d["name"],
        main_class=d.get("main_class", ""),
        cs_hash=d.get("cs_hash", ""),
        xml_hash=d.get("xml_hash", ""),
        sub_processes=sps,
    )


# ─── CARGA / GUARDADO ─────────────────────────────────────────────────────────


def load_state(tool_dir: Path) -> Optional[StateFile]:
    """Carga btg-state.json. Retorna None si no existe o está corrupto."""
    state_path = tool_dir / _STATE_FILE
    if not state_path.is_file():
        return None
    try:
        raw = json.loads(state_path.read_text(encoding="utf-8"))
        if raw.get("version") != _STATE_VERSION:
            logger.info("State version mismatch, discarding.")
            return None
        procs = {k: _from_dict_process(v) for k, v in raw.get("processes", {}).items()}
        return StateFile(
            version=raw["version"],
            batch_root=raw.get("batch_root", ""),
            processes=procs,
        )
    except Exception as exc:
        logger.warning("No se pudo leer btg-state.json: %s", exc)
        return None


def save_state(tool_dir: Path, processes: list[BatchProcess], batch_root: Path) -> None:
    """Guarda el estado actual en btg-state.json."""
    state = StateFile(
        version=_STATE_VERSION,
        batch_root=str(batch_root),
        processes={bp.name: _process_to_snap(bp) for bp in processes},
    )
    state_path = tool_dir / _STATE_FILE
    state_path.write_text(
        json.dumps(_to_dict(state), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.debug("State guardado: %d procesos", len(processes))


# ─── DIFF ─────────────────────────────────────────────────────────────────────

@dataclass
class DiffResult:
    new_processes: list[str] = field(default_factory=list)
    removed_processes: list[str] = field(default_factory=list)
    new_subprocs: dict[str, list[str]] = field(default_factory=dict)      # proceso → [subproc]
    removed_subprocs: dict[str, list[str]] = field(default_factory=dict)
    changed_methods: dict[str, list[str]] = field(default_factory=dict)   # proceso.subproc → [metodo]
    changed_source: list[str] = field(default_factory=list)               # procesos con hash distinto

    @property
    def has_changes(self) -> bool:
        return bool(
            self.new_processes
            or self.removed_processes
            or self.new_subprocs
            or self.removed_subprocs
            or self.changed_methods
            or self.changed_source
        )

    def summary_lines(self) -> list[str]:
        lines = []
        if self.new_processes:
            lines.append(f"  + Nuevos procesos ({len(self.new_processes)}): {', '.join(self.new_processes)}")
        if self.removed_processes:
            lines.append(f"  - Procesos eliminados: {', '.join(self.removed_processes)}")
        for proc, sps in self.new_subprocs.items():
            lines.append(f"  + {proc}: nuevos sub-procesos: {', '.join(sps)}")
        for proc, sps in self.removed_subprocs.items():
            lines.append(f"  - {proc}: sub-procesos eliminados: {', '.join(sps)}")
        for key, methods in self.changed_methods.items():
            lines.append(f"  ~ {key}: metodos cambiados: {', '.join(methods)}")
        if self.changed_source:
            lines.append(f"  ~ Fuentes modificadas: {', '.join(self.changed_source)}")
        return lines


def compute_diff(
    old_state: Optional[StateFile],
    current_processes: list[BatchProcess],
) -> DiffResult:
    """
    Compara el estado anterior con el escaneo actual.
    Retorna DiffResult con todo lo que cambió.
    """
    diff = DiffResult()

    if old_state is None:
        # Primera vez: todo es nuevo
        diff.new_processes = [bp.name for bp in current_processes]
        return diff

    old_names = set(old_state.processes.keys())
    cur_names = {bp.name for bp in current_processes}
    cur_map = {bp.name: bp for bp in current_processes}

    diff.new_processes = sorted(cur_names - old_names)
    diff.removed_processes = sorted(old_names - cur_names)

    # Procesos existentes en ambos → comparar en detalle
    for name in sorted(old_names & cur_names):
        old_proc = old_state.processes[name]
        cur_proc = cur_map[name]

        # Hash del .cs o .xml cambió
        cur_cs_hash = _file_hash(cur_proc.main_cs_path)
        cur_xml_hash = _file_hash(cur_proc.xml_config_path) if cur_proc.xml_config_path else ""
        if cur_cs_hash != old_proc.cs_hash or cur_xml_hash != old_proc.xml_hash:
            diff.changed_source.append(name)

        # Sub-procesos
        old_sp_names = {sp.name for sp in old_proc.sub_processes}
        cur_sp_names = {sp.name for sp in cur_proc.sub_processes}
        new_sps = sorted(cur_sp_names - old_sp_names)
        rem_sps = sorted(old_sp_names - cur_sp_names)
        if new_sps:
            diff.new_subprocs[name] = new_sps
        if rem_sps:
            diff.removed_subprocs[name] = rem_sps

        # Métodos dentro de sub-procesos comunes
        old_sp_map = {sp.name: sp for sp in old_proc.sub_processes}
        for sp in cur_proc.sub_processes:
            if sp.name not in old_sp_map:
                continue
            old_sp = old_sp_map[sp.name]
            old_method_sigs = {
                m.name: (m.return_type, tuple(m.params))
                for m in old_sp.methods
            }
            cur_method_sigs = {
                m.name: (m.return_type, tuple(m.params))
                for m in sp.biz_methods
            }
            changed = [
                m for m, sig in cur_method_sigs.items()
                if old_method_sigs.get(m) != sig
            ]
            changed += [m for m in old_method_sigs if m not in cur_method_sigs]
            if changed:
                diff.changed_methods[f"{name}.{sp.name}"] = sorted(changed)

    return diff
