"""Stacky Agents canonical resolver, materializer e invocation contract.

Este módulo concentra la lógica del plan
``plan-agentes-bundled-en-stacky-2026-05-29.md``:

- Resolución del directorio canónico ``<STACKY_HOME>/agents``.
- Materialización (copia) de los ``.agent.md`` conocidos hacia el canonical.
- Manifest versionado con ``mention`` (``@nombre``), ``checksum_sha256`` y
  ``source`` por agente.
- Helper único ``build_invocation_block`` para que cualquier runner
  (codex_cli, claude_code_cli, copilot bridge) inyecte el mismo contrato
  de invocación al prompt.

Mantiene compatibilidad temporal con ``VSCODE_PROMPTS_DIR`` legacy a través
de las fuentes externas; la meta es que producción use solo el canonical.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from runtime_paths import (
    app_root,
    backend_root,
    ensure_stacky_agents_dir,
    ensure_stacky_home,
    stacky_agents_dir,
    stacky_home,
)

logger = logging.getLogger(__name__)

_AGENT_GLOB = "*.agent.md"
_MANIFEST_NAME = "manifest.json"
_MANIFEST_SCHEMA_VERSION = 1

SOURCE_BUNDLED = "bundled"
SOURCE_LEGACY_VSCODE = "legacy_vscode"
SOURCE_IMPORTED = "imported"
SOURCE_CUSTOM = "custom"


@dataclass
class AgentEntry:
    """Una entrada materializada en ``<stacky_home>/agents``."""

    name: str
    mention: str
    filename: str
    path: Path
    relative_path: str
    description: str
    checksum_sha256: str
    source: str = SOURCE_CUSTOM

    def to_manifest_dict(self) -> dict:
        return {
            "name": self.name,
            "mention": self.mention,
            "filename": self.filename,
            "path": str(self.path).replace("\\", "/"),
            "relative_path": self.relative_path.replace("\\", "/"),
            "description": self.description,
            "checksum_sha256": self.checksum_sha256,
            "source": self.source,
        }


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def _sha256_file(path: Path) -> str:
    """Hashea el archivo tal cual está en disco.

    Esto coincide con lo que produce ``check_deploy_agents.py``
    (``hashlib.sha256(path.read_bytes())``) y evita discrepancias por
    line endings o BOM que aparecen si hasheamos el texto re-codificado.
    """
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _safe_agent_name(filename: str) -> str:
    for ext in (".agent.md", ".prompt.md", ".md"):
        if filename.endswith(ext):
            return filename[: -len(ext)]
    return filename


def _normalize_agent_filename(filename: str) -> str | None:
    if not filename:
        return None
    safe = Path(filename).name
    if not safe.endswith(".agent.md"):
        return None
    return safe


def _read_agent_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("no se pudo leer %s: %s", path, exc)
        return None


def _extract_description_from_text(text: str) -> str:
    """Mejor esfuerzo: lee `description` del frontmatter o la primera línea no-#."""
    try:
        import yaml  # type: ignore
    except Exception:  # noqa: BLE001
        yaml = None  # type: ignore

    if text.startswith("﻿"):
        text = text.lstrip("﻿")
    body = text
    if text.startswith("---"):
        rest = text[3:]
        if rest.startswith("\r\n"):
            rest = rest[2:]
        elif rest.startswith("\n"):
            rest = rest[1:]
        end = rest.find("\n---")
        if end >= 0:
            raw_fm = rest[:end]
            body = rest[end + len("\n---"):]
            if body.startswith("\r\n"):
                body = body[2:]
            elif body.startswith("\n"):
                body = body[1:]
            if yaml is not None:
                try:
                    fm = yaml.safe_load(raw_fm) or {}
                    desc = fm.get("description") if isinstance(fm, dict) else None
                    if isinstance(desc, str) and desc.strip():
                        return desc.strip()
                except Exception:  # noqa: BLE001
                    pass

    for line in body.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            return stripped[:240]
    return ""


def _relative_to(path: Path, base: Path) -> str:
    try:
        return str(path.relative_to(base))
    except ValueError:
        return path.name


def _build_entry(path: Path, *, source: str, base: Path) -> AgentEntry | None:
    filename = _normalize_agent_filename(path.name)
    if filename is None:
        return None
    text = _read_agent_text(path)
    if text is None:
        return None
    name = _safe_agent_name(filename)
    description = _extract_description_from_text(text)
    checksum = _sha256_file(path)
    return AgentEntry(
        name=name,
        mention=f"@{name}",
        filename=filename,
        path=path.resolve(),
        relative_path=_relative_to(path, base),
        description=description,
        checksum_sha256=checksum,
        source=source,
    )


def _legacy_vscode_prompts_dir() -> Path | None:
    if os.name == "nt":
        appdata = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        candidate = Path(appdata) / "Code" / "User" / "prompts"
    else:
        candidate = Path.home() / ".config" / "Code" / "User" / "prompts"
    return candidate if candidate.is_dir() else None


def _bundled_agents_dir() -> Path | None:
    """Bundle del deploy: ``<app_root>/github_copilot_agents`` (compat temporal)."""
    candidate = app_root() / "github_copilot_agents"
    return candidate if candidate.is_dir() else None


def _in_repo_agents_dir() -> Path | None:
    """Fuente in-repo durante el desarrollo (no-frozen)."""
    candidate = backend_root().parent / "DeployStackyAgents" / "github_copilot_agents"
    return candidate if candidate.is_dir() else None


def list_external_sources() -> list[tuple[Path, str]]:
    """Devuelve fuentes externas en orden de prioridad de materialización.

    El canonical (``stacky_agents_dir``) NO se lista acá: es el destino, no
    una fuente. Solo se devuelven los directorios que ya existen.
    """
    sources: list[tuple[Path, str]] = []
    bundled = _bundled_agents_dir()
    if bundled is not None:
        sources.append((bundled, SOURCE_BUNDLED))
    in_repo = _in_repo_agents_dir()
    if in_repo is not None and (bundled is None or in_repo.resolve() != bundled.resolve()):
        sources.append((in_repo, SOURCE_BUNDLED))
    legacy = _legacy_vscode_prompts_dir()
    if legacy is not None:
        sources.append((legacy, SOURCE_LEGACY_VSCODE))
    return sources


def _load_previous_sources() -> dict[str, str]:
    """``filename -> source`` desde el manifest actual, si existe."""
    manifest_file = stacky_agents_dir() / _MANIFEST_NAME
    if not manifest_file.is_file():
        return {}
    try:
        data = json.loads(manifest_file.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}
    if not isinstance(data, dict):
        return {}
    out: dict[str, str] = {}
    for agent in data.get("agents") or []:
        if not isinstance(agent, dict):
            continue
        fn = agent.get("filename")
        src = agent.get("source")
        if isinstance(fn, str) and isinstance(src, str):
            out[fn] = src
    return out


def write_manifest(entries: list[AgentEntry]) -> Path:
    """Escribe ``stacky_agents_dir()/manifest.json`` con `entries`."""
    canonical = ensure_stacky_agents_dir()
    manifest_file = canonical / _MANIFEST_NAME
    payload = {
        "schema_version": _MANIFEST_SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "stacky_home": str(stacky_home()).replace("\\", "/"),
        "agents_dir": str(canonical).replace("\\", "/"),
        "agents": [e.to_manifest_dict() for e in entries],
    }
    manifest_file.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return manifest_file


def read_manifest() -> dict | None:
    manifest_file = stacky_agents_dir() / _MANIFEST_NAME
    if not manifest_file.is_file():
        return None
    try:
        data = json.loads(manifest_file.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None
    return data if isinstance(data, dict) else None


def list_canonical_agents() -> list[AgentEntry]:
    """Lista los `.agent.md` actualmente presentes en `stacky_agents_dir()`."""
    base = stacky_agents_dir()
    if not base.is_dir():
        return []
    previous = _load_previous_sources()
    entries: list[AgentEntry] = []
    for path in sorted(base.glob(_AGENT_GLOB)):
        if not path.is_file():
            continue
        prev_source = previous.get(path.name, SOURCE_CUSTOM)
        entry = _build_entry(path, source=prev_source, base=base)
        if entry is not None:
            entries.append(entry)
    return entries


def get_canonical_agent(filename: str) -> AgentEntry | None:
    safe = _normalize_agent_filename(filename)
    if safe is None:
        return None
    base = stacky_agents_dir()
    candidate = base / safe
    if not candidate.is_file():
        return None
    previous = _load_previous_sources()
    return _build_entry(candidate, source=previous.get(safe, SOURCE_CUSTOM), base=base)


def build_entry_from_path(
    path: Path,
    *,
    source: str = SOURCE_CUSTOM,
) -> AgentEntry | None:
    """Construye un ``AgentEntry`` desde un ``.agent.md`` arbitrario.

    Útil para los runners que tienen un path resuelto pero no necesariamente
    dentro del canonical (por ejemplo, deploys aún apuntando a la carpeta
    legacy ``github_copilot_agents``).
    """
    if not path.is_file():
        return None
    return _build_entry(path, source=source, base=path.parent)


def materialize_agents(
    *,
    sources: Iterable[Path] | None = None,
    force: bool = False,
    regenerate_manifest: bool = True,
) -> list[AgentEntry]:
    """Copia ``.agent.md`` desde fuentes externas hacia `stacky_agents_dir()`.

    Política:
    - Si un archivo ya existe en el canonical NO se sobrescribe a menos que
      ``force=True``: preservamos ediciones del operador en el deploy.
    - Si la misma `filename` aparece en varias fuentes, gana la primera (orden
      de prioridad). Estricto: nunca duplicamos por path traversal.
    - El manifest se regenera al final con ``write_manifest()``.

    ``sources`` default = ``list_external_sources()``.
    """
    ensure_stacky_home()
    canonical = ensure_stacky_agents_dir()

    provenance_by_src: dict[Path, str] = {
        src.resolve(): prov for src, prov in list_external_sources()
    }

    if sources is None:
        sources_list = [src for src, _ in list_external_sources()]
    else:
        sources_list = list(sources)

    previous = _load_previous_sources()
    seen: set[str] = set()
    materialized: list[AgentEntry] = []

    for src_dir in sources_list:
        if not src_dir.is_dir():
            continue
        provenance = provenance_by_src.get(src_dir.resolve(), SOURCE_CUSTOM)
        for src_file in sorted(src_dir.glob(_AGENT_GLOB)):
            if not src_file.is_file():
                continue
            filename = _normalize_agent_filename(src_file.name)
            if filename is None or filename in seen:
                continue
            target = canonical / filename
            target_existed = target.exists()
            if force or not target_existed:
                try:
                    target.write_text(
                        src_file.read_text(encoding="utf-8"),
                        encoding="utf-8",
                    )
                    logger.info(
                        "stacky_agents: materializado %s ← %s (source=%s)",
                        filename, src_file, provenance,
                    )
                except OSError as exc:
                    logger.warning("no se pudo materializar %s: %s", src_file, exc)
                    continue
            entry_source = provenance if not target_existed or force else previous.get(filename, provenance)
            entry = _build_entry(target, source=entry_source, base=canonical)
            if entry is not None:
                materialized.append(entry)
                seen.add(filename)

    for path in sorted(canonical.glob(_AGENT_GLOB)):
        filename = _normalize_agent_filename(path.name)
        if filename is None or filename in seen:
            continue
        entry = _build_entry(path, source=previous.get(filename, SOURCE_IMPORTED), base=canonical)
        if entry is not None:
            materialized.append(entry)
            seen.add(filename)

    if regenerate_manifest:
        write_manifest(materialized)
    return materialized


def import_agent_from_path(
    source_file: Path,
    *,
    overwrite: bool = False,
    source: str = SOURCE_IMPORTED,
) -> AgentEntry:
    """Copia un ``.agent.md`` arbitrario al canonical y regenera el manifest.

    Lanza ``FileNotFoundError`` si la fuente no existe y ``FileExistsError`` si
    ``overwrite=False`` y el archivo ya está en el canonical.
    """
    if not source_file.is_file():
        raise FileNotFoundError(f"no existe: {source_file}")
    filename = _normalize_agent_filename(source_file.name)
    if filename is None:
        raise ValueError(f"nombre inválido (no es *.agent.md): {source_file.name}")
    canonical = ensure_stacky_agents_dir()
    target = canonical / filename
    if target.exists() and not overwrite:
        raise FileExistsError(f"ya existe en canonical: {target}")
    target.write_text(source_file.read_text(encoding="utf-8"), encoding="utf-8")
    entries = list_canonical_agents()
    previous = _load_previous_sources()
    for i, entry in enumerate(entries):
        if entry.filename == filename:
            entries[i] = AgentEntry(
                name=entry.name,
                mention=entry.mention,
                filename=entry.filename,
                path=entry.path,
                relative_path=entry.relative_path,
                description=entry.description,
                checksum_sha256=entry.checksum_sha256,
                source=source,
            )
            break
    else:
        new = _build_entry(target, source=source, base=canonical)
        if new is not None:
            entries.append(new)
    # preservar source previo de los que no se acaban de importar
    for i, entry in enumerate(entries):
        if entry.filename != filename and entry.filename in previous:
            entries[i] = AgentEntry(
                name=entry.name,
                mention=entry.mention,
                filename=entry.filename,
                path=entry.path,
                relative_path=entry.relative_path,
                description=entry.description,
                checksum_sha256=entry.checksum_sha256,
                source=previous[entry.filename],
            )
    write_manifest(entries)
    out = get_canonical_agent(filename)
    if out is None:
        raise RuntimeError(f"no se pudo leer el agente recién importado: {target}")
    return out


def build_invocation_block(
    *,
    entry: AgentEntry,
    workspace_root: str | Path | None,
) -> str:
    """Bloque normalizado de invocación que todos los runners deben incluir.

    Contiene `@nombre`, ruta de trabajo, archivo `.agent.md` exacto y carpeta
    canónica. Plan: §2.3 — Contrato de invocación.
    """
    ws = ""
    if workspace_root:
        ws = str(workspace_root)
    home = str(stacky_home())
    agents_dir = str(entry.path.parent)
    return (
        "## Agente Stacky seleccionado\n"
        "\n"
        f"- Mention: {entry.mention}\n"
        f"- Nombre: {entry.name}\n"
        f"- Archivo agent.md: {entry.filename}\n"
        f"- Ruta agent.md: {entry.path}\n"
        f"- Carpeta de agentes configurada: {agents_dir}\n"
        f"- STACKY_HOME: {home}\n"
        f"- Workspace de trabajo: {ws or '(no resuelto)'}\n"
        "\n"
        f"Regla: usá el agente `{entry.mention}` y tomá como prompt/persona\n"
        f"únicamente el archivo `{entry.path}`.\n"
        "No uses otro `.agent.md` aunque exista en rutas externas. Si el archivo\n"
        "no existe, detené la ejecución y reportá el bloqueo.\n"
    )


def invocation_metadata(
    *,
    entry: AgentEntry,
    workspace_root: str | Path | None,
) -> dict:
    """Metadata estructurada para persistir en `AgentExecution.metadata_dict`.

    Mismas claves declaradas en el plan §4 — Fase 4. Usar junto con
    `build_invocation_block()` para mantener parity entre prompt y log.
    """
    return {
        "agent_mention": entry.mention,
        "agent_name": entry.name,
        "agent_filename": entry.filename,
        "agent_path": str(entry.path),
        "agent_checksum_sha256": entry.checksum_sha256,
        "agent_source": entry.source,
        "agents_dir": str(entry.path.parent),
        "stacky_home": str(stacky_home()),
        "workspace_root": str(workspace_root) if workspace_root else None,
    }
