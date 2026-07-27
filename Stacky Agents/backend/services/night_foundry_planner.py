"""services/night_foundry_planner.py — Plan 202 E2/E3 (La Fragua Nocturna F0/TMV).

DERIVA la cola de trabajo del estado real del repo (no una lista fija) y la encola
en el ledger con dedup por fingerprint. Determinista, cero LLM, cero red.

Ademas de derivar, es el dueno de:
  * la resolucion del directorio de planes (`_docs_dir`) — el anclaje que hundio la
    v1 de este plan cuando apuntaba a `app_root()/"docs"`;
  * el veredicto de DISPONIBILIDAD de la Fragua (`foundry_availability`), que falla
    cerrado en un deploy congelado;
  * los helpers deterministas de parseo de doc (§E0), que tambien consumen
    `night_foundry_workers` y `night_foundry_orchestrator`.
"""
from __future__ import annotations

import hashlib
import logging
import re
import subprocess
from pathlib import Path

import runtime_paths
from services import night_foundry_ledger as L

logger = logging.getLogger(__name__)

MAX_V2_UNIMPLEMENTED = 8  # techo de WIP kanban del gate anti-deuda-de-papel (§E3)

# Ventana de lineas que se lee a partir de CADA encabezado/bullet "Orden de
# implementacion". [BUG REAL DEL PLAN 202] El §E0 fijaba 8 lineas desde la PRIMERA
# coincidencia: alcanza para la hoja de ruta 195 (su linea de orden cae 6 lineas
# debajo del encabezado) pero NO para la 197 (cae 8 abajo, justo fuera). Medido
# sobre los docs reales. Se leen TODAS las coincidencias con ventana de 12.
_ORDER_WINDOW = 12


# ── rutas y disponibilidad ───────────────────────────────────────────────────

def _repo_root() -> Path:
    """Raiz del repo git: <root>/Stacky Agents/backend -> <root>."""
    return runtime_paths.backend_root().parent.parent


def _docs_dir() -> Path:
    """Carpeta de los planes.

    VERIFICADO `runtime_paths.py:36-45`: en dev `app_root() == backend_root() ==
    Stacky Agents/backend`, asi que `app_root()/"docs"` apunta a
    `Stacky Agents/backend/docs`, que NO existe. Los planes viven en
    `Stacky Agents/docs`. La Fragua es una herramienta de REPO (opera planes y
    ramas del working tree), asi que se resuelve contra el arbol del repo.
    """
    return runtime_paths.backend_root().parent / "docs"


def _docs_dir_ok() -> bool:
    d = _docs_dir()
    return d.exists() and d.is_dir()


def _is_git_worktree() -> bool:
    return _git(["rev-parse", "--is-inside-work-tree"]).strip().lower() == "true"


def foundry_availability() -> dict:
    """Veredicto binario y VISIBLE de si la Fragua puede correr en este runtime.

    DECISION DE IMPLEMENTACION (riesgo que el doc dejaba abierto): la Fragua
    Nocturna **NO corre en un deploy congelado (PyInstaller)**, solo en el arbol de
    desarrollo. Razon medida, no supuesta: en congelado `backend_root()` es el
    directorio del `.exe`, con lo cual `backend_root().parent/"docs"` vuelve a
    colapsar exactamente sobre `app_root()/"docs"` — el path inexistente que hundio
    la v1 — y ademas no hay repo git, ni ramas, ni working tree que auditar: los
    cuatro carriles (critic/auditor/package/reconciler) quedarian sin insumo.

    El guard falla CERRADO (no deriva, no encola, no procesa) y VISIBLE: el
    `reason_code` viaja al panel (`GET /api/night-foundry/status`) y al digest. NUNCA
    degrada en silencio a "0 items" indistinguible de "noche tranquila".
    """
    if runtime_paths.is_frozen():
        return {
            "available": False,
            "reason_code": "frozen_deploy",
            "reason": ("La Fragua Nocturna solo corre en el arbol de desarrollo. En el "
                       "deploy congelado no hay repo git ni carpeta de planes que "
                       "trabajar, asi que no se ejecuta nada."),
            "docs_dir": None,
        }
    if not _docs_dir_ok():
        return {
            "available": False,
            "reason_code": "docs_dir_missing",
            "reason": f"No encuentro la carpeta de planes ({_docs_dir()}).",
            "docs_dir": str(_docs_dir()),
        }
    if not _is_git_worktree():
        return {
            "available": False,
            "reason_code": "not_a_git_repo",
            "reason": "Esto no es un working tree de git: no hay ramas ni historia que auditar.",
            "docs_dir": str(_docs_dir()),
        }
    return {"available": True, "reason_code": "", "reason": "", "docs_dir": str(_docs_dir())}


def _plan_docs() -> list[Path]:
    if not _docs_dir_ok():
        return []  # [C1] sin carpeta de planes: [] y no crash
    return sorted(_docs_dir().glob("[0-9]*_PLAN_*.md"))


def _status_line(text: str) -> str:
    for line in text.splitlines()[:12]:
        if "Estado:" in line or "Versión:" in line or "Version:" in line:
            return line
    return ""


def _git(args: list[str]) -> str:
    """git read-only con cwd fijo en la raiz del repo (el cwd del proceso no es
    confiable: el backend puede arrancar desde cualquier lado)."""
    try:
        return subprocess.run(["git", *args], capture_output=True, text=True, timeout=60,
                              cwd=str(_repo_root())).stdout.strip()
    except Exception:  # noqa: BLE001 — git ausente/timeout: degradar a vacio
        return ""


def _main_tree_files(base: str = "main") -> set[str] | None:
    """Set de rutas versionadas en `base`, de UNA sola llamada a git.

    [BUG REAL DEL PLAN 202] El §E0 hacia un `git cat-file -e main:<archivo>` por cada
    archivo citado por cada doc IMPLEMENTADO: con 211 docs x hasta 20 archivos son
    miles de spawns de proceso en Windows (minutos). Un unico `ls-tree -r` da la
    MISMA semantica de pertenencia. `None` = no se pudo leer `base` ⇒ no se deriva
    drift (fail-closed: mejor cero candidatos que candidatos inventados).
    """
    out = _git(["ls-tree", "-r", "--name-only", base])
    if not out:
        return None
    return set(out.splitlines())


# ── §E0 · helpers deterministas de parseo (los comparten workers/orquestador) ─

def _doc_for(nn: str) -> Path:
    for p in _plan_docs():
        if p.name.startswith(f"{nn}_"):
            return p
    raise FileNotFoundError(f"no hay doc para plan {nn}")


def _extract_files(text: str) -> list[str]:
    """Rutas del repo entre backticks (dedup preservando orden)."""
    seen: set[str] = set()
    out: list[str] = []
    for m in re.findall(r"`(Stacky Agents/[\w /.\-]+\.\w+)`", text):
        if m not in seen:
            seen.add(m)
            out.append(m)
    return out


def _extract_tests(text: str) -> list[str]:
    return sorted(set(re.findall(r"(test_[\w]+\.py)", text)))


def _extract_phases(text: str) -> list[str]:
    return re.findall(r"^#+\s*(E\d+|F\d+)\b[^\n]*", text, re.M)


def _extract_gates(text: str) -> list[str]:
    return [l.strip() for l in text.splitlines()
            if re.search(r"Criterio|gate|ratchet|KPI-\d", l)][:40]


def _match_gotchas(text: str) -> list[str]:
    """IN-REPO y portable: escanea el PROPIO doc. NO lee la memoria de `~/.claude`
    (es del operador, vive fuera del repo y no existe en Codex/Copilot ni en una
    instalacion fresca)."""
    keys = ("ratchet", "HARNESS_TEST_FILES", "_CURATED_DEFAULTS_ON", "POR ARCHIVO", ".venv",
            "gotcha", "_REQUIRES_MAP_FROZEN", "_FROZEN_BOUNDS", "doc_indexer", "config.config")
    low = text.lower()
    return sorted({k for k in keys if k.lower() in low})


def _roadmap_docs() -> list[Path]:
    return [p for p in _plan_docs() if re.match(r"(195|197|184)_", p.name)]


def _order_block_numbers(roadmap: Path) -> list[str]:
    """Numeros de plan citados bajo CUALQUIER 'Orden de implementaci...' del doc,
    en orden de aparicion. Ver `_ORDER_WINDOW` para por que no es una sola ventana."""
    try:
        lines = roadmap.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:  # noqa: BLE001
        return []
    bloque: list[str] = []
    for i, l in enumerate(lines):
        if re.search(r"Orden de implementaci", l, re.I):
            bloque.extend(lines[i:i + _ORDER_WINDOW])
    return re.findall(r"\b(\d{2,3})\b", "\n".join(bloque))


def _derive_package_candidates() -> list[tuple[str, str, str]]:
    """Primer plan NO-IMPLEMENTADO del orden canonico de cada hoja de ruta."""
    out: list[tuple[str, str, str]] = []
    docs = _plan_docs()
    for rd in _roadmap_docs():
        try:
            for pos, nn in enumerate(_order_block_numbers(rd)):
                doc = next((p for p in docs if p.name.startswith(f"{nn}_")), None)
                if doc is None:
                    continue
                st = _status_line(doc.read_text(encoding="utf-8", errors="replace"))
                if re.search(r"IMPLEMENTADO|IMPL\b", st):
                    continue
                sig = hashlib.sha256(doc.read_bytes()).hexdigest()
                out.append(("package", f"plan:{nn}", f"{sig}#{pos}"))
                break  # 1 candidato por hoja de ruta
        except Exception:  # noqa: BLE001 — hoja de ruta que no parsea: log + skip
            logger.warning("night_foundry: hoja de ruta %s no parsea; se saltea", rd.name)
            continue
    return out


def _derive_drift_candidates() -> list[tuple[str, str, str]]:
    """Plan marcado IMPLEMENTADO cuyos archivos citados NO estan en `main`."""
    out: list[tuple[str, str, str]] = []
    en_main = _main_tree_files()
    if en_main is None:
        logger.warning("night_foundry: no pude leer el arbol de main; no derivo drift")
        return out
    tip = _git(["rev-parse", "HEAD"])
    for doc in _plan_docs():
        m = re.match(r"(\d+)_", doc.name)
        if not m:
            continue
        nn = m.group(1)
        text = doc.read_text(encoding="utf-8", errors="replace")
        st = _status_line(text)
        if not re.search(r"IMPLEMENTADO|IMPL\b", st):
            continue
        named = _extract_files(text)[:20]
        if not named:
            continue
        missing = [f for f in named if f not in en_main]
        if not missing:
            continue
        flags = ",".join("miss" if f in missing else "main" for f in named)
        sig = hashlib.sha256(f"{st}|{tip}|{flags}".encode()).hexdigest()
        out.append(("reconciler", f"plan:{nn}", sig))
    return out


# ── derivacion y encolado ────────────────────────────────────────────────────

def derive_candidates() -> list[tuple[str, str, str]]:
    """(lane, target, input_signature) derivados del estado real del repo."""
    if not foundry_availability()["available"]:
        return []
    cands: list[tuple[str, str, str]] = []
    for doc in _plan_docs():
        m = re.match(r"(\d+)_", doc.name)
        if not m:
            continue
        nn = m.group(1)
        raw = doc.read_bytes()
        text = raw.decode("utf-8", "replace")
        status = _status_line(text)
        # [C2] el negativo se evalua sobre la STATUS LINE, no sobre todo el texto: un
        # v1 genuino puede mencionar "CRITICADO v2" en su prosa y seria falso-negativo.
        if re.search(r"PROPUESTO v1", status) and not re.search(r"v2|CRITICADO", status):
            cands.append(("critic", f"plan:{nn}", hashlib.sha256(raw).hexdigest()))
    for line in _git(["for-each-ref", "--format=%(refname:short) %(objectname)",
                      "refs/heads/impl"]).splitlines():
        parts = line.split()
        if len(parts) == 2:
            cands.append(("auditor", f"branch:{parts[0]}", parts[1]))
    cands += _derive_package_candidates()
    cands += _derive_drift_candidates()
    return cands


_EMPTY_ENQ = {"critic": 0, "auditor": 0, "package": 0, "reconciler": 0, "proposer": 0,
              "skipped_dedup": 0}


def plan_night(night: str) -> dict:
    """Encola en el ledger todos los candidatos derivados (dedup por input_hash)
    EXCEPTO el carril proposer, que pasa por el gate anti-deuda-de-papel (§E3)."""
    disp = foundry_availability()
    if not disp["available"]:
        return {"enqueued": dict(_EMPTY_ENQ), "gate": foundry_backlog_gate(night),
                "availability": disp}
    cands = derive_candidates()
    enq = dict(_EMPTY_ENQ)
    # snapshot UNICO de los fingerprints ya resueltos: leer el ledger entero por
    # candidato era O(n^2) sobre cientos de candidatos.
    ya_done = {r.get("input_hash") for r in L.list_items() if r.get("state") == "done"}
    for lane, target, sig in cands:
        ih = L.compute_input_hash(lane, target, sig)
        L.upsert_item(lane, target, ih, night=night)
        if ih in ya_done:
            enq["skipped_dedup"] += 1
        else:
            enq[lane] += 1
    gate = foundry_backlog_gate(night)
    if gate["proposer_allowed"]:
        # F0: la derivacion del carril proposer esta RESERVADA y no se implementa.
        # El gate ya devuelve False de facto mientras haya deuda de papel (KPI-6).
        logger.info("night_foundry: gate permite proposer pero el carril esta reservado en F0")
    return {"enqueued": enq, "gate": gate, "availability": disp}


# ── E3 · gate anti-deuda-de-papel (la tesis rectora, cableada) ───────────────

def _count_backlog() -> dict:
    v1_uncriticized = v2_unimplemented = 0
    for doc in _plan_docs():
        status = _status_line(doc.read_text(encoding="utf-8", errors="replace"))
        if re.search(r"PROPUESTO v1", status) and not re.search(r"v2|CRITICADO", status):
            v1_uncriticized += 1
        if (re.search(r"CRITICADO v2|APROBADO-CON-CAMBIOS", status)
                and not re.search(r"IMPLEMENTADO|IMPL\b", status)):
            v2_unimplemented += 1
    return {"v1_uncriticized": v1_uncriticized, "v2_unimplemented": v2_unimplemented}


def foundry_backlog_gate(night: str | None = None) -> dict:
    """La tesis "des-atascar, no fabricar papel" como gate verificable.

    Bloquea el carril proposer si: hay v1 sin criticar, O hay mas de
    MAX_V2_UNIMPLEMENTED v2 sin implementar, O el ratio generar:consumir de la noche
    superaria 1:3. En F0 el proposer esta reservado ⇒ ratio 0:N garantizado.
    """
    b = _count_backlog()
    consume = 0
    if night is not None:
        consume = sum(1 for r in L.list_items(night=night)
                      if r.get("lane") in ("critic", "auditor", "package", "reconciler"))
    proposer_ceiling = consume // 3
    blocked_reason = ""
    if b["v1_uncriticized"] > 0:
        blocked_reason = "hay planes v1 sin criticar (critica antes de proponer)"
    elif b["v2_unimplemented"] > MAX_V2_UNIMPLEMENTED:
        blocked_reason = (f"{b['v2_unimplemented']} planes v2 sin implementar "
                          f"(> {MAX_V2_UNIMPLEMENTED})")
    elif proposer_ceiling < 1:
        blocked_reason = "ratio generar:consumir 1:3 no alcanzado esta noche"
    return {"proposer_allowed": blocked_reason == "", "reason": blocked_reason,
            "proposer_ceiling": proposer_ceiling, "metrics": b}
