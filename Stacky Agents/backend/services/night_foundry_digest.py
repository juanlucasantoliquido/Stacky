"""services/night_foundry_digest.py — Plan 202 E6 (La Fragua Nocturna F0/TMV).

Convierte el ledger de la noche en una COLA DE DECISIONES rankeada, deduplicada y
con veredicto de mergeabilidad (contrato congelado §5.2). El operador ve QUE hacer,
no un volcado de logs. Todo inerte: el digest no mergea, no publica y no implementa.
"""
from __future__ import annotations

import json
import logging
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import runtime_paths
from services import night_foundry_ledger as L
from services.night_foundry_planner import _repo_root

logger = logging.getLogger(__name__)

# Orden de valor para el operador (menor = mas prioritario).
_KIND_RANK = {"merge": 0, "implement": 1, "review": 2, "reconcile": 3}


def _run(args: list[str], **kw):
    """git read-only con cwd fijo en la raiz del repo. `args` NO incluye 'git'."""
    return subprocess.run(["git", *args], capture_output=True, text=True, timeout=120,
                          cwd=str(_repo_root()), **kw)


def _digests_dir() -> Path:
    d = Path(runtime_paths.data_dir()) / "night_foundry" / "digests"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _parse_conflict_paths(stdout: str) -> list[str]:
    """Rutas en conflicto del stdout de `merge-tree`.

    [BUG REAL DEL PLAN 202] El §E0 usaba `\\S+` para capturar la ruta. En ESTE repo
    TODAS las rutas versionadas empiezan con "Stacky Agents/", o sea que contienen
    un espacio: la forma `both modified:` no matcheaba NUNCA (el `$` quedaba fuera
    de alcance) y la forma `CONFLICT (...)` devolvia la ruta TRUNCADA
    ("Agents/backend/app.py"). Le mentia al operador sobre que archivos chocan.
    Se captura hasta fin de linea.

    Si ninguna forma matchea se devuelve [] a proposito: el veredicto sigue siendo
    `conflict`; lo que no se sabe es CUALES son los archivos.
    """
    a = set(re.findall(r"^\s*CONFLICT \([^)]*\):[^\n]*?\bin (.+?)\s*$", stdout, re.M))
    b = set(re.findall(
        r"^\s*(?:both modified:|both added:|added by us:|added by them:|deleted by us:"
        r"|deleted by them:|changed in both)\s+(.+?)\s*$", stdout, re.M))
    return sorted(a | b)


def mergeability(branch: str, base: str = "main") -> dict:
    """Veredicto read-only via `git merge-tree --write-tree`.

    rc 0 -> clean. rc 1 -> conflicto real. rc>1 (o excepcion/timeout) -> ERROR de
    git (ref inexistente, etc.) -> `unknown`: NO se confunde un error con un
    conflicto, porque "no mergeable" es una afirmacion fuerte que el operador usa
    para decidir. No toca working tree ni refs (escribe objetos sueltos inalcanzables
    que el GC recolecta).
    """
    try:
        p = _run(["merge-tree", "--write-tree", base, branch])
    except Exception:  # noqa: BLE001
        return {"verdict": "unknown", "mergeable": None, "conflict_paths": []}
    if p.returncode == 0:
        return {"verdict": "clean", "mergeable": True, "conflict_paths": []}
    if p.returncode == 1:
        return {"verdict": "conflict", "mergeable": False,
                "conflict_paths": _parse_conflict_paths(p.stdout)}
    return {"verdict": "unknown", "mergeable": None, "conflict_paths": []}


def _dedup_by_key(decisions: list[dict]) -> list[dict]:
    """1 decision por `dedup_key`, conservando la de MEJOR kind (menor _KIND_RANK)."""
    best: dict[str, dict] = {}
    for d in decisions:
        k = d["dedup_key"]
        if k not in best or _KIND_RANK.get(d["kind"], 9) < _KIND_RANK.get(best[k]["kind"], 9):
            best[k] = d
    return list(best.values())


def _decision(kind: str, title: str, item: dict, **extra) -> dict:
    base = {"kind": kind, "title": title, "target": item.get("target"),
            "verdict": None, "mergeable": None, "conflict_paths": [], "package_ref": None,
            "cost_tokens": int(item.get("cost_tokens", 0) or 0),
            "dedup_key": item.get("target")}
    base.update(extra)
    return base


def build_digest(night: str, *, budget: int, stopped_reason: str) -> dict:
    items = L.list_items(night=night)
    decisions: list[dict] = []
    for it in items:
        if it.get("state") != "done":
            continue
        lane = it.get("lane")
        target = it.get("target") or ""
        if lane == "auditor":
            rama = target.split("branch:", 1)[-1]
            m = mergeability(rama)
            decisions.append(_decision(
                "merge", f"Rama {rama}: {m['verdict']}", it,
                verdict=m["verdict"], mergeable=m["mergeable"],
                conflict_paths=m["conflict_paths"]))
        elif lane == "package":
            decisions.append(_decision(
                "implement", f"Paquete listo para implementar: {target}", it,
                package_ref=it.get("output_ref")))
        elif lane == "critic":
            decisions.append(_decision(
                "review", f"Critica v2 lista para revisar: {target}", it,
                package_ref=it.get("output_ref")))
        elif lane == "reconciler":
            decisions.append(_decision(
                "reconcile", f"Drift doc-vs-codigo: {target}", it))

    decisions = _dedup_by_key(decisions)
    decisions.sort(key=lambda d: (_KIND_RANK.get(d["kind"], 9), d["target"] or ""))
    for i, d in enumerate(decisions, 1):
        d["rank"] = i

    counts = {k: sum(1 for it in items if it.get("lane") == k and it.get("state") == "done")
              for k in ("critic", "auditor", "package", "reconciler")}
    counts["failed"] = sum(1 for it in items if it.get("state") == "failed")

    digest = {
        "night": night,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "budget_tokens": budget,
        "spent_tokens": L.spent_tokens(night),
        "budget_exhausted": stopped_reason == "budget",
        # [EXTENSION ADITIVA del contrato §5.2] al enum congelado se le suma
        # "unavailable": una noche que NO corrio (deploy congelado, sin repo git,
        # sin carpeta de planes) no se puede leer como "noche tranquila".
        "stopped_reason": stopped_reason,
        "counts": counts,
        "decisions": decisions,
    }
    out = _digests_dir() / f"digest-{night}.json"
    out.write_text(json.dumps(digest, ensure_ascii=False, indent=2), encoding="utf-8")
    return digest


def latest_digest() -> dict:
    """El digest mas reciente por nombre de archivo (los nombres son fechas ISO,
    asi que el orden lexicografico ES el cronologico). `{}` si no hay ninguno."""
    try:
        archivos = sorted(_digests_dir().glob("digest-*.json"))
    except Exception:  # noqa: BLE001
        return {}
    for p in reversed(archivos):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except Exception:  # noqa: BLE001 — digest corrupto: probar el anterior
            logger.warning("night_foundry: digest ilegible %s", p.name)
            continue
    return {}
