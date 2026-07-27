"""Plan 215 F1 — descubrimiento de perfiles de publish (.pubxml) + plan determinista.

Modulo PURO: sin Flask, sin red, sin LLM. Ninguna funcion lanza jamas (OSError
degrada). Es lo que hace que `mode:"auto"` funcione sin que el operador configure
nada (G1) y lo que decide, determinsticamente e igual en los 3 runtimes, como se
publica cada solucion.
"""
from __future__ import annotations

import os
import re

_PUBXML_SUBDIR = os.path.join("Properties", "PublishProfiles")
_PUBXML_HEAD_BYTES = 32768
_METHOD_RE = re.compile(r"<webpublishmethod[^>]*>([^<]+)</webpublishmethod", re.I)
_PUBURL_RE = re.compile(r"<publishurl[^>]*>([^<]+)</publishurl", re.I)
_SDK_ATTR_RE = re.compile(r"<project\s[^>]*\bsdk\s*=", re.I)
# C10 — canonicalizacion case-insensitive del metodo del .pubxml.
_METHOD_CANON = {
    "filesystem": "FileSystem",
    "msdeploy": "MSDeploy",
    "package": "Package",
    "ftp": "FTP",
}


def scan_publish_profiles(projects: list) -> dict:
    """{csproj_path: [{name, path, method, publish_url}]} — solo proyectos con perfiles."""
    out: dict = {}
    for p in projects or []:
        csproj = (p or {}).get("csproj_path") or ""
        if not csproj:
            continue
        prof_dir = os.path.join(os.path.dirname(csproj), _PUBXML_SUBDIR)
        entries = []
        try:
            names = sorted(os.listdir(prof_dir))
        except (OSError, ValueError):
            # ValueError: rutas con byte nulo (open/listdir no lanzan OSError ahi).
            names = []
        for fname in names:
            if not fname.lower().endswith(".pubxml"):
                continue
            path = os.path.join(prof_dir, fname)
            try:
                with open(path, "rb") as fh:
                    head = fh.read(_PUBXML_HEAD_BYTES).decode("utf-8", errors="replace")
            except (OSError, ValueError):
                continue
            m = _METHOD_RE.search(head)
            method_raw = (m.group(1).strip() if m else "")
            method = _METHOD_CANON.get(method_raw.lower(), method_raw or "unknown")
            u = _PUBURL_RE.search(head)
            entries.append({
                "name": os.path.splitext(fname)[0],
                "path": path,
                "method": method,
                "publish_url": (u.group(1).strip() if u else ""),
            })
        if entries:
            out[csproj] = entries
    return out


def detect_sdk_style(csproj_path: str) -> bool:
    """True si el .csproj es SDK-style (`<Project Sdk="...">`) ⇒ dotnet publish."""
    if not csproj_path:
        return False
    try:
        with open(csproj_path, "rb") as fh:
            head = fh.read(_PUBXML_HEAD_BYTES).decode("utf-8", errors="replace")
    except (OSError, ValueError):
        return False
    return bool(_SDK_ATTR_RE.search(head))


def _plan_build_only(solution: dict, cfg: dict, toolchain: dict) -> dict:
    return {
        "mode_effective": "build_only",
        "supported": bool(toolchain.get("available", False)),
        "reason": "" if toolchain.get("available") else "toolchain_missing",
        "target": (solution or {}).get("sln_path") or "",
        "argv_tail": [],
    }


def resolve_publish_plan(solution: dict, cfg: dict, toolchain: dict) -> dict:
    """Plan de publish EFECTIVO. Orden de reglas CONGELADO (§F1 del plan 215)."""
    solution = solution or {}
    cfg = cfg or {}
    toolchain = toolchain or {}

    # 1) proyecto objetivo
    target_csproj = cfg.get("project_csproj")
    projects = solution.get("projects") or []
    if not target_csproj:
        target_csproj = (
            next((p.get("csproj_path") for p in projects if p.get("type") == "web"), None)
            or next(
                (p.get("csproj_path") for p in projects
                 if p.get("type") in ("console", "service")),
                None,
            )
        )
    mode = cfg.get("mode") or "auto"
    profiles = scan_publish_profiles(projects)

    # 2) modo explicito / auto
    if mode == "build_only" or (mode == "auto" and target_csproj is None):
        return _plan_build_only(solution, cfg, toolchain)

    if mode == "dotnet_publish" or (mode == "auto" and detect_sdk_style(target_csproj)):
        # C5 — la condicion es SOLO dotnet_path: un toolchain con builder=="dotnet"
        # pero sin dotnet_path es contradictorio y debe degradar aca (si pasara,
        # F4 armaria argv[0]=None).
        if not toolchain.get("dotnet_path"):
            return {"mode_effective": "dotnet_publish", "supported": False,
                    "reason": "requiere_dotnet_sdk", "target": target_csproj,
                    "argv_tail": []}
        return {"mode_effective": "dotnet_publish", "supported": True, "reason": "",
                "target": target_csproj,
                "argv_tail": ["publish", target_csproj, "-c",
                              cfg.get("configuration") or "Release", "--nologo"]}

    # 3) clasico (.NET Framework): pubxml FileSystem o degradar
    profs = profiles.get(target_csproj, [])
    chosen = None
    if cfg.get("publish_profile"):
        chosen = next((e for e in profs if e["name"] == cfg["publish_profile"]), None)
        if chosen is None:
            return {"mode_effective": "msbuild_pubxml", "supported": False,
                    "reason": "pubxml_no_encontrado", "target": target_csproj,
                    "argv_tail": []}
    else:
        chosen = next((e for e in profs if e["method"] == "FileSystem"), None)

    if mode == "msbuild_pubxml" or (mode == "auto" and chosen is not None):
        if chosen is None:
            return {"mode_effective": "msbuild_pubxml", "supported": False,
                    "reason": "sin_pubxml_filesystem", "target": target_csproj,
                    "argv_tail": []}
        if chosen["method"] != "FileSystem":
            return {"mode_effective": "msbuild_pubxml", "supported": False,
                    "reason": "pubxml_remoto_no_soportado", "target": target_csproj,
                    "argv_tail": []}
        if not toolchain.get("msbuild_path"):
            return {"mode_effective": "msbuild_pubxml", "supported": False,
                    "reason": "requiere_msbuild", "target": target_csproj,
                    "argv_tail": []}
        return {"mode_effective": "msbuild_pubxml", "supported": True, "reason": "",
                "target": target_csproj,
                "argv_tail": [target_csproj, "/p:DeployOnBuild=true",
                              "/p:PublishProfile=" + chosen["name"],
                              "/p:Configuration=" + (cfg.get("configuration") or "Release"),
                              "/nologo"]}

    # 4) auto sin pubxml y no-SDK -> build_only
    return _plan_build_only(solution, cfg, toolchain)
