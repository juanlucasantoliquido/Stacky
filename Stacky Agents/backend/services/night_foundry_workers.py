"""services/night_foundry_workers.py — Plan 202 E4 (La Fragua Nocturna F0/TMV).

Workers DETERMINISTAS (cero LLM, cero red) de los tres carriles que no necesitan
modelo: auditor, constructor-de-paquetes y reconciliador. El carril `critic` NO
vive aca: lo dispatchea el orquestador Claude-nativo (E5/E7) via skill.

Dominios de salida DISJUNTOS bajo `data_dir()/night_foundry/`:
  auditor  -> audits/      package -> packages/      reconciler -> nada (devuelve dict)
Con la serializacion del orquestador (un item por iteracion) no hay dos escrituras
simultaneas ni siquiera dentro de un mismo carril.
"""
from __future__ import annotations

import json
import logging
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import runtime_paths
from services import night_foundry_planner as _planner
# Parsers PUROS de doc: se importan por nombre porque no tienen efectos ni
# dependencias que un test deba interceptar.
from services.night_foundry_planner import (
    _extract_files,
    _extract_gates,
    _extract_phases,
    _extract_tests,
    _match_gotchas,
    _repo_root,
)

# `_main_tree_files` se invoca SIEMPRE via `_planner.` a proposito: toca git, asi
# que los tests tienen que poder interceptarlo. Importado por nombre, el binding
# queda congelado en este modulo y un monkeypatch sobre el planner NO surte efecto:
# dos tests del reconciliador pasaban ejercitando el repo REAL en vez del mock
# (falso verde silencioso).

logger = logging.getLogger(__name__)

# UNICO seam de subproceso del modulo: todo lo que sale de aca es git read-only.
# Tenerlo centralizado es lo que hace verificable el limite AUDIT-ONLY (KPI-5).
_GIT_READONLY_VERBS = frozenset({"status", "diff", "rev-parse", "ls-tree", "cat-file",
                                 "for-each-ref", "merge-tree"})


def _run(args: list[str], **kw):
    """git read-only con cwd fijo en la raiz del repo. `args` NO incluye 'git'."""
    if args and args[0] not in _GIT_READONLY_VERBS:
        raise ValueError(f"verbo git no permitido en la Fragua: {args[0]}")
    return subprocess.run(["git", *args], capture_output=True, text=True, timeout=120,
                          cwd=str(_repo_root()), **kw)


def _nf_dir(sub: str) -> Path:
    d = Path(runtime_paths.data_dir()) / "night_foundry" / sub
    d.mkdir(parents=True, exist_ok=True)
    return d


def _hoy() -> str:
    return f"{datetime.now(timezone.utc):%Y-%m-%d}"


# ── carril auditor ───────────────────────────────────────────────────────────

def run_auditor(branch: str, base: str = "main") -> dict:
    """AUDIT-ONLY DURO: reporte read-only del delta rama-vs-base, GIT-ONLY.

    [C3] En F0 el auditor NO corre los tests de la rama: eso exige un checkout en un
    worktree propio y es trabajo del refutador (F3). Correr pytest en el worktree
    `nightly/` —que es un checkout de `main`— auditaria el codigo EQUIVOCADO y
    KPI-5 pasaria trivialmente.

    POST-CONDICION (KPI-5): `git status --porcelain` identico antes y despues. Si
    difiere, `readonly_ok` queda en False y el orquestador marca el item `failed`
    para que el digest denuncie la violacion.
    """
    antes = _run(["status", "--porcelain"]).stdout
    rng = f"{base}...{branch}"
    diffstat = _run(["diff", "--stat", rng]).stdout
    nombres = [n for n in _run(["diff", "--name-only", rng]).stdout.splitlines() if n.strip()]
    test_files = [n for n in nombres if re.search(r"(^|/)test_\w+\.py$", n)]
    changed_py = [n for n in nombres if n.endswith(".py")]
    despues = _run(["status", "--porcelain"]).stdout

    reporte = {
        "branch": branch, "base": base, "generated_at": datetime.now(timezone.utc).isoformat(),
        "diffstat": diffstat, "test_files": test_files, "changed_py": changed_py,
        # mapa fase->archivo determinista: en F0 es la lista de .py tocados, sin
        # ejecutar nada. El mapeo fino a fases es del refutador (F3).
        "phase_map": changed_py,
        "readonly_ok": (antes == despues),
    }
    out = _nf_dir("audits") / f"{branch.replace('/', '-')}-{_hoy()}.json"
    out.write_text(json.dumps(reporte, ensure_ascii=False, indent=2), encoding="utf-8")
    if not reporte["readonly_ok"]:
        logger.error("night_foundry: el auditor de %s violo la post-condicion read-only", branch)
    return {"output_ref": f"audits/{out.name}", "cost_tokens": 0,
            "readonly_ok": reporte["readonly_ok"]}


# ── carril constructor-de-paquetes ───────────────────────────────────────────

def build_package(plan_nn: str, doc_path: Path) -> dict:
    """Arma el "paquete listo-para-el-dia" de un plan, determinista.

    R1: los tests salen como TEXTO dentro del `.json` (`tests_to_write`), NUNCA como
    archivos ejecutables en el arbol de tests. La Fragua no escribe codigo de
    producto: solo papel revisable.
    """
    text = Path(doc_path).read_text(encoding="utf-8", errors="replace")
    pkg = {
        "plan": plan_nn,
        "doc": Path(doc_path).name,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "files_to_touch": _extract_files(text),
        "tests_to_write": _extract_tests(text),
        "phase_checklist": _extract_phases(text),
        "gotchas": _match_gotchas(text),
        "gates": _extract_gates(text),
    }
    out = _nf_dir("packages") / f"plan-{plan_nn}-{_hoy()}.json"
    out.write_text(json.dumps(pkg, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"output_ref": f"packages/{out.name}", "cost_tokens": 0}


# ── carril reconciliador ─────────────────────────────────────────────────────

def run_reconciler(plan_nn: str, doc_path: Path) -> dict:
    """Compara el estado DECLARADO del doc contra la realidad del codigo en `main`.

    No escribe archivo propio (su salida entra al digest). Cero LLM, cero mutacion.
    Si no se puede leer el arbol de `main`, devuelve `unknown: True` y CERO drift:
    falla cerrado, nunca denuncia un drift inventado.
    """
    text = Path(doc_path).read_text(encoding="utf-8", errors="replace")
    declared = "IMPLEMENTADO" if re.search(r"IMPLEMENTADO", text[:400]) else "otro"
    en_main = _planner._main_tree_files()
    if en_main is None:
        return {"plan": plan_nn, "declared": declared, "drift": [], "unknown": True,
                "cost_tokens": 0}
    drift = []
    if declared == "IMPLEMENTADO":
        for f in _extract_files(text)[:20]:
            if f not in en_main:
                drift.append({"file": f,
                              "issue": "el doc dice IMPLEMENTADO pero el archivo no esta en main"})
    return {"plan": plan_nn, "declared": declared, "drift": drift, "unknown": False,
            "cost_tokens": 0}
