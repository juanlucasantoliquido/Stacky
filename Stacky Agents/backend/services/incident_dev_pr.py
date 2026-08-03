"""Plan 177 F2 — Diff del working tree + intent store en disco para el Auto-PR
del Dev Resolutor de Incidencias.

Dos responsabilidades:
1. Enumerar EXACTAMENTE qué archivos tocó el agente en el working tree del
   proyecto activo, vía snapshot ANTES del run + delta por HASH DESPUÉS (no barre
   los cambios dirty preexistentes del operador).
2. Persistir el "intent" del PR (consentimiento del checkbox + baseline + repo)
   keyeado por `execution_id` en disco — NO en `AgentExecution.metadata_json`, que
   el runner también escribe (evita la carrera de clobber, G9).

Todo local y read-only del working tree (ningún commit/stash/push acá). El git se
corre con el mismo endurecimiento no-interactivo de `pre_run_git._run_git`
(`credential.helper=` vacío, `GIT_TERMINAL_PROMPT=0`, `CREATE_NO_WINDOW` en Windows,
timeout) para que nunca cuelgue en un prompt.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import logging
import os
import stat
import subprocess
import time
from pathlib import Path

logger = logging.getLogger("stacky.services.incident_dev_pr")

_MAX_FILE_HASH_BYTES = 8_000_000  # cap defensivo al hashear (archivos enormes)

# Chars válidos del campo XY del porcelain (para distinguir "XY PATH" de un
# path "pelado" que aparece como segundo token en un rename con -z).
_STATUS_CHARS = set(" MADRCU?!T")


# ── Runner git no-interactivo (espejo de pre_run_git._run_git) ────────────────

def _git_ex(cwd: Path, args: list[str], *, timeout: int = 30) -> tuple[bool, str, str | None]:
    """Corre `git <args>` en `cwd`. Devuelve (ok, stdout, fallo).

    `fallo` distingue lo que `_git` aplasta en un solo False y que para el
    diagnóstico es TODO lo que importa:
      - None            → git corrió (ok dice si el comando tuvo éxito)
      - "no_disponible" → git no está instalado / no es ejecutable
      - "timeout"       → git no respondió (unidad de red colgada, lock)
      - "error"         → otro OSError del sistema
    Sin esta distinción, "no tengo git instalado" y "esta carpeta no es un repo"
    se reportan igual, y el operador sale a arreglar N repos sanos.
    """
    cmd = ["git", "-c", "credential.helper=", "-c", "core.longpaths=true", *args]
    env = os.environ.copy()
    env.update({
        "GIT_TERMINAL_PROMPT": "0",
        "GCM_INTERACTIVE": "Never",
        "GIT_ASKPASS": "",
        "SSH_ASKPASS": "",
    })
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            env=env,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
        )
        return proc.returncode == 0, (proc.stdout or ""), None
    except subprocess.TimeoutExpired as exc:
        logger.info("incident_dev_pr._git sin respuesta (%s): %s", args[:2], exc)
        return False, "", "timeout"
    except FileNotFoundError as exc:  # ANTES que OSError: es subclase suya
        logger.info("incident_dev_pr._git: git no disponible: %s", exc)
        return False, "", "no_disponible"
    except OSError as exc:
        logger.info("incident_dev_pr._git falló (%s): %s", args[:2], exc)
        return False, "", "error"


def _git(cwd: Path, args: list[str], *, timeout: int = 30) -> tuple[bool, str]:
    """Corre `git <args>` en `cwd`. Devuelve (ok, stdout). Nunca lanza ni cuelga."""
    ok, out, _fallo = _git_ex(cwd, args, timeout=timeout)
    return ok, out


# ── Resolución de repo + remoto ───────────────────────────────────────────────

def resolve_repo_root(workspace_root: str | None) -> str | None:
    """Toplevel del repo git que contiene `workspace_root` (que puede ser un
    SUBDIR del repo), o None si vacío / no existe / no es un repo git.

    Fachada delgada sobre `detect_repo`: cuando esto tenía su propia
    implementación había DOS detecciones de git conviviendo, que es una invitación
    a que divergan (una entiende los worktrees y la otra no, por ejemplo). Acá se
    pierde el motivo a propósito — quien lo necesite usa `detect_repo`.
    """
    return detect_repo(workspace_root).get("repo_root")


# ── Auto-detección de repositorio git (2026-08-02) ───────────────────────────
# Corre git CONTRA el workspace_root. Deliberadamente NO mira el nombre de la
# carpeta: una ruta que dice "SVN" puede contener un repo git impecable y una que
# dice "GIT" puede no serlo. Inferir por el nombre sería el mismo defecto que
# esto viene a arreglar, con otro disfraz.

DETECT_REASONS: tuple[str, ...] = (
    "sin_workspace", "ruta_inexistente", "ruta_no_es_carpeta", "ruta_inaccesible",
    "git_no_disponible", "git_sin_respuesta", "no_es_repo_git",
)

#: El memo NO se keyea por proyecto ni por mtime del config: se keyea por la RUTA
#: mirada. Si el operador cambia el `workspace_root` desde la UI, la clave cambia
#: sola y el resultado sale del disco nuevo — no hace falta acordarse de
#: invalidar. El TTL cubre el caso inverso: la ruta es la misma y lo que cambió
#: es el disco (un `git init` recién hecho).
_DETECT_TTL_S = 30.0
_detect_memo: dict[str, tuple[float, dict]] = {}

#: Otros sistemas de control de versiones, detectados por su carpeta EN DISCO
#: (evidencia), nunca por el nombre del directorio (heurística).
_OTROS_VCS = (
    (".svn", "Parece un working copy de Subversion (tiene una carpeta .svn)."),
    (".hg", "Parece un repositorio Mercurial (tiene una carpeta .hg)."),
    ("_svn", "Parece un working copy de Subversion (tiene una carpeta _svn)."),
)


def _pista_de_otro_vcs(ws: str) -> str | None:
    for carpeta, texto in _OTROS_VCS:
        try:
            if (Path(ws) / carpeta).exists():
                return texto
        except OSError:  # noqa: PERF203 — una ruta ilegible no invalida las demás
            continue
    return None


def _misma_ruta(a: str, b: str) -> bool:
    try:
        na = os.path.normcase(os.path.realpath(a))
        nb = os.path.normcase(os.path.realpath(b))
    except OSError:
        return False
    return na == nb


def _det(reason, *, repo_root=None, workspace_root=None, es_subdirectorio=False,
         pista=None) -> dict:
    return {
        "ok": reason is None,
        "reason": reason,
        "repo_root": repo_root,
        "workspace_root": workspace_root,
        "es_subdirectorio": bool(es_subdirectorio),
        "pista": pista,
    }


def _detect_repo_sin_memo(workspace_root) -> dict:
    if not workspace_root or not str(workspace_root).strip():
        return _det("sin_workspace")
    ws = str(workspace_root).strip()

    # os.stat y NO Path.exists(): `exists()` se traga el OSError de una unidad de
    # red caída y devuelve False, que es indistinguible de "no existe" — y ahí el
    # operador sale a convertir a git un repo que ya lo es.
    try:
        st = os.stat(ws)
    except FileNotFoundError:
        return _det("ruta_inexistente", workspace_root=ws)
    except OSError as exc:
        return _det("ruta_inaccesible", workspace_root=ws, pista=str(exc))
    if not stat.S_ISDIR(st.st_mode):
        return _det("ruta_no_es_carpeta", workspace_root=ws)

    # `rev-parse --show-toplevel` y NO mirar `.git`: en un git worktree `.git` es
    # un ARCHIVO, no un directorio, y cualquier chequeo por `is_dir()` daría
    # NO-git sobre un worktree perfectamente usable.
    ok, out, fallo = _git_ex(Path(ws), ["rev-parse", "--show-toplevel"], timeout=15)
    if fallo == "no_disponible":
        return _det("git_no_disponible", workspace_root=ws)
    if fallo == "timeout":
        return _det("git_sin_respuesta", workspace_root=ws)
    top = (out or "").strip()
    if not ok or not top:
        return _det("no_es_repo_git", workspace_root=ws, pista=_pista_de_otro_vcs(ws))

    return _det(None, repo_root=top, workspace_root=ws,
                es_subdirectorio=not _misma_ruta(top, ws))


def detect_repo(workspace_root) -> dict:
    """¿La carpeta de este proyecto está bajo git? Memoizado por RUTA, TTL corto.

    {'ok', 'reason', 'repo_root', 'workspace_root', 'es_subdirectorio', 'pista'}.
    Nunca lanza. `repo_root` es el TOPLEVEL, que puede ser un ancestro del
    `workspace_root` (ver `es_subdirectorio`).
    """
    clave = os.path.normcase(str(workspace_root or ""))
    ahora = time.monotonic()
    guardado = _detect_memo.get(clave)
    if guardado and (ahora - guardado[0]) < _DETECT_TTL_S:
        return dict(guardado[1])
    res = _detect_repo_sin_memo(workspace_root)
    _detect_memo[clave] = (ahora, res)
    return dict(res)


def invalidate_repo_detection(workspace_root=None) -> None:
    """Olvida lo memoizado (todo, o lo de una ruta): detección Y remoto. Para
    llamar cuando el operador cambia la config de un proyecto o hace `git init`."""
    if workspace_root is None:
        _detect_memo.clear()
        return
    norm = os.path.normcase(str(workspace_root or ""))
    _detect_memo.pop(norm, None)
    _detect_memo.pop("origin:" + norm, None)


def remote_origin_url(repo_root: str) -> str | None:
    """URL del remoto 'origin' del repo, o None (sin origin / no repo / vacío).
    [ADICIÓN ARQUITECTO] — insumo de la guardia de mapeo working-tree ↔ repo del
    tracker (F4) y de la anotación del origin en el PR.

    Memoizado con el MISMO TTL e invalidación que `detect_repo`: el preflight
    corre dos comandos git por proyecto, y memoizar sólo el primero dejaría la
    mitad del martillo en pie (N proyectos × cada consulta de la UI).
    """
    if not repo_root:
        return None
    clave = "origin:" + os.path.normcase(str(repo_root))
    ahora = time.monotonic()
    guardado = _detect_memo.get(clave)
    if guardado and (ahora - guardado[0]) < _DETECT_TTL_S:
        return guardado[1].get("url")
    ok, out = _git(Path(repo_root), ["remote", "get-url", "origin"], timeout=15)
    url = ((out or "").strip() or None) if ok else None
    _detect_memo[clave] = (ahora, {"url": url})
    return url


# ── Snapshot + delta del working tree ─────────────────────────────────────────

def _sha1_file(path: Path) -> str:
    h = hashlib.sha1()  # noqa: S324 — sólo para detectar cambios, no criptográfico
    try:
        with path.open("rb") as fh:
            read = 0
            while True:
                chunk = fh.read(65536)
                if not chunk:
                    break
                read += len(chunk)
                if read > _MAX_FILE_HASH_BYTES:
                    h.update(chunk)
                    h.update(b"__truncated__")
                    break
                h.update(chunk)
    except OSError:
        return "__unreadable__"
    return h.hexdigest()


def _parse_porcelain_z(raw: str) -> set[str]:
    """Extrae el conjunto de paths (repo-relativos, POSIX) de la salida de
    `git status --porcelain -z -uall`. Maneja el token 'pelado' del rename."""
    paths: set[str] = set()
    for tok in raw.split("\x00"):
        if not tok:
            continue
        if len(tok) >= 3 and tok[2] == " " and tok[0] in _STATUS_CHARS and tok[1] in _STATUS_CHARS:
            path = tok[3:]
        else:
            path = tok  # path pelado (2do token de un rename con -z)
        if path:
            paths.add(path)
    return paths


def snapshot_worktree(repo_root: str) -> dict:
    """{'head': <sha o ''>, 'entries': {rel_posix: sha1 | '__deleted__'}} de TODOS
    los archivos dirty+untracked del working tree. Read-only."""
    root = Path(repo_root)
    ok_head, head_out = _git(root, ["rev-parse", "HEAD"], timeout=15)
    head_sha = (head_out or "").strip() if ok_head else ""
    ok, out = _git(root, ["status", "--porcelain", "-z", "-uall"], timeout=60)
    entries: dict[str, str] = {}
    if ok and out:
        for rel in _parse_porcelain_z(out):
            full = root / rel
            entries[rel] = _sha1_file(full) if full.is_file() else "__deleted__"
    return {"head": head_sha, "entries": entries}


def compute_changed_files(baseline: dict, current: dict) -> dict:
    """Delta por HASH: qué tocó ESTE run. Excluye lo dirty preexistente intacto.
    → {'added_or_modified': [rel...], 'deleted': [rel...]} (ordenados)."""
    base_entries = (baseline or {}).get("entries", {}) or {}
    cur_entries = (current or {}).get("entries", {}) or {}
    added_or_modified: list[str] = []
    deleted: list[str] = []
    for path, sha in cur_entries.items():
        if sha == "__deleted__":
            if base_entries.get(path) != "__deleted__":
                deleted.append(path)
        elif base_entries.get(path) != sha:
            added_or_modified.append(path)
    return {"added_or_modified": sorted(added_or_modified), "deleted": sorted(deleted)}


# ── Clasificación código vs tests (cierra K2) ─────────────────────────────────

def _is_test_path(p: str) -> bool:
    pl = p.lower()
    base = pl.rsplit("/", 1)[-1]
    if base.startswith("test_") and base.endswith(".py"):
        return True
    if base.endswith("_test.py"):
        return True
    if ".test." in base or ".spec." in base:
        return True
    padded = "/" + pl
    return any(seg in padded for seg in ("/tests/", "/__tests__/", "/test/"))


def classify_changed_files(paths: list[str]) -> dict:
    """{'code': [...], 'tests': [...]} — los tests viajan explícitos en el PR (K2)."""
    code: list[str] = []
    tests: list[str] = []
    for p in paths:
        (tests if _is_test_path(p) else code).append(p)
    return {"code": sorted(code), "tests": sorted(tests)}


# ── Intent store en disco (keyeado por execution_id; espejo de incident_store) ─

def _intent_dir() -> Path:
    from runtime_paths import data_dir  # noqa: PLC0415
    d = data_dir() / "incident_dev_pr"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _intent_path(execution_id: int) -> Path:
    return _intent_dir() / f"{int(execution_id)}.json"


def record_intent(execution_id: int, intent: dict) -> None:
    """Escribe atómico (tmp + replace) el intent del PR keyeado por execution_id."""
    data = dict(intent or {})
    data.setdefault("created_at", datetime.datetime.now(datetime.timezone.utc).isoformat())
    path = _intent_path(execution_id)
    tmp = path.parent / (path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def get_intent(execution_id: int) -> dict | None:
    path = _intent_path(execution_id)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def mark_intent(execution_id: int, **fields) -> None:
    """Merge idempotente de campos de resultado (pr_id, pr_url, branch, status,
    error, files_committed, origin, ...) sobre el intent existente."""
    cur = get_intent(execution_id) or {}
    cur.update(fields)
    record_intent(execution_id, cur)


# ── Chequeo PREVIO de repo git (2026-08-02) ───────────────────────────────────
# El operador tildaba "Abrir PR" a ciegas: si el proyecto no tenia workspace_root,
# o el workspace no era un repo git, `run_incident_dev` no registraba el intent
# (api/agents.py:1330 `if open_pr and _pr_repo_root and _pr_baseline is not None`)
# y el post-hook cortaba en `get_intent() -> None` (incident_dev_autocommit.py:88)
# SIN comentar nada. Resultado: el operador tildaba, el agente corria, y el PR
# no aparecia nunca sin un solo mensaje. Esto corre ANTES del tilde y devuelve el
# motivo para mostrarlo en la UI.

_PREFLIGHT_MESSAGES = {
    "feature_disabled": (
        "El auto-PR esta apagado. Encende STACKY_INCIDENT_DEV_PR_ENABLED en el panel de flags."
    ),
    "sin_proyecto": (
        "No se pudo resolver el proyecto activo, asi que no hay repo donde abrir el PR."
    ),
    # — motivos de la AUTO-DETECCIÓN de git (uno por causa, nunca compartidos:
    #   cada uno manda al operador a un arreglo distinto) —
    "sin_workspace": (
        "El proyecto no tiene 'workspace_root' configurado: Stacky no sabe que carpeta mirar. "
        "Configuralo en la ficha del proyecto."
    ),
    "ruta_inexistente": (
        "La carpeta configurada en 'workspace_root' no existe. "
        "Puede que la hayan movido o renombrado."
    ),
    "ruta_no_es_carpeta": (
        "La ruta configurada en 'workspace_root' apunta a un archivo, no a una carpeta."
    ),
    "ruta_inaccesible": (
        "No se pudo leer la carpeta del proyecto (unidad de red caida o sin permisos). "
        "OJO: esto NO significa que el proyecto no tenga git, significa que no se pudo mirar."
    ),
    "git_no_disponible": (
        "No se pudo ejecutar git. Revisa que git este instalado y en el PATH: "
        "sin git, NINGUN proyecto se puede verificar."
    ),
    "git_sin_respuesta": (
        "git no respondio a tiempo sobre esta carpeta (unidad de red lenta o un lock del repo)."
    ),
    "no_es_repo_git": (
        "La carpeta del proyecto no esta bajo git (git rev-parse no encuentra ningun repositorio). "
        "Sin repo no hay nada que commitear ni PR que abrir."
    ),
    "tracker_sin_pr": (
        "El tracker del proyecto no puede abrir Pull/Merge Requests."
    ),
    "remoto_ajeno": (
        "El remoto 'origin' de la carpeta apunta a otro servidor que el tracker del "
        "proyecto: no se abre PR para no commitear en el repo equivocado."
    ),
}

_PREFLIGHT_WARNINGS = {
    "sin_origin": (
        "El repo no tiene remoto 'origin'. El PR igual se abre por la API del tracker, "
        "pero se pierde la verificacion de que la carpeta y el tracker son el mismo repo."
    ),
    "workspace_es_subdirectorio": (
        "La carpeta del proyecto es una SUBCARPETA del repositorio. El PR va a incluir "
        "todo lo que el agente cambie en el repo entero, no solo dentro de esa subcarpeta."
    ),
}


def _preflight(reason, *, repo_root=None, origin=None, workspace_root=None,
               tracker_type=None, project=None, warning=None, provider_label=None,
               detalle="") -> dict:
    """Constructor unico del contrato: TODAS las claves siempre presentes."""
    base = _PREFLIGHT_MESSAGES.get(reason, "") if reason else ""
    return {
        "ok": reason is None,
        "reason": reason,
        "message": f"{base} {detalle}".strip() if base else "",
        "warning": warning,
        "warning_message": _PREFLIGHT_WARNINGS.get(warning, "") if warning else "",
        "repo_root": repo_root,
        "origin": origin,
        "workspace_root": workspace_root,
        "tracker_type": tracker_type,
        "provider_label": provider_label,
        "project": project,
    }


def _puerto_de_pr(project):
    """(nombre_del_proveedor | None, detalle_del_fallo).

    La verdad de "¿este proyecto puede abrir PRs?" la tiene la FABRICA
    (merge_request_provider.py:78 -> repo_writer -> tracker_provider), no una
    lista de tracker_type copiada aca: una lista duplicada se desincroniza en
    silencio la proxima vez que se agregue un tracker, y el operador se entera
    recien cuando el post-hook explota. Sin red: los constructores no hacen
    requests (mismo supuesto que `incident_dev_autocommit._provider_host`).
    """
    try:
        from services.merge_request_provider import get_merge_request_provider  # noqa: PLC0415
        prov = get_merge_request_provider(project)
    except Exception as exc:  # noqa: BLE001 — cualquier fallo == no hay puerto usable
        return None, str(exc)
    return (getattr(prov, "name", None) or None), ""


def preflight_repo(project: str | None = None, *, ignorar_flag: bool = False) -> dict:
    """¿Puede el auto-PR del Dev Resolutor correr sobre ESTE proyecto? Sin RED.

    `project=None` = el proyecto activo (compatibilidad con los call sites que ya
    existen); con un nombre, se puede preguntar por CUALQUIER proyecto
    configurado sin cambiar el activo.

    Devuelve SIEMPRE el dict completo. `ok=False` viene con `reason` (codigo
    estable para la UI) y `message` (texto para el operador): la degradacion es
    VISIBLE, el tilde se deshabilita con el motivo a la vista y nunca desaparece
    sin explicacion.

    `ignorar_flag=True` saltea el corte por `STACKY_INCIDENT_DEV_PR_ENABLED`: lo
    usa la vista de conjunto, donde el operador quiere ver el estado de git de
    cada proyecto AUNQUE el auto-PR este apagado (son dos preguntas distintas).
    """
    from config import config as _cfg  # noqa: PLC0415
    if not ignorar_flag and not bool(getattr(_cfg, "STACKY_INCIDENT_DEV_PR_ENABLED", False)):
        return _preflight("feature_disabled", project=project)

    try:
        from services import project_context  # noqa: PLC0415
        ctx = project_context.resolve_project_context(project)
    except Exception:  # noqa: BLE001 — un proyecto mal configurado NO es un 500
        logger.info("preflight auto-PR: no se pudo resolver el proyecto %s", project, exc_info=True)
        ctx = None
    if ctx is None:
        return _preflight("sin_proyecto", project=project)

    project_name = getattr(ctx, "stacky_project_name", None) or project
    workspace_root = getattr(ctx, "workspace_root", None)
    # Se informa TAL CUAL lo declara el proyecto (puede venir vacío: quién le pone
    # el default es la fábrica, y a ella se le pregunta más abajo).
    _tt = getattr(ctx, "tracker_type", None)
    tracker_type = str(_tt).strip().lower() if isinstance(_tt, str) and _tt.strip() else None

    # AUTO-DETECCIÓN: se corre git contra la carpeta del proyecto. Cada causa
    # tiene su propio `reason` — "no tiene git", "la ruta no existe", "la unidad
    # está caída" y "git no está instalado" mandan al operador a arreglos
    # distintos, y aplastarlos en uno solo fue el defecto original.
    det = detect_repo(workspace_root)
    if not det["ok"]:
        return _preflight(det["reason"], workspace_root=workspace_root,
                          project=project_name, tracker_type=tracker_type,
                          detalle=det.get("pista") or "")
    repo_root = det["repo_root"]

    # Un tracker sin puerto MR explotaba recien en el post-hook, cuando ya es tarde.
    provider_label, detalle = _puerto_de_pr(project)
    if not provider_label:
        return _preflight("tracker_sin_pr", repo_root=repo_root, workspace_root=workspace_root,
                          project=project_name, tracker_type=tracker_type, detalle=detalle)

    origin = remote_origin_url(repo_root)

    # MISMA guardia que aborta el post-hook (incident_dev_autocommit.py:117),
    # adelantada al momento del tilde.
    try:
        from services import incident_dev_autocommit as _auto  # noqa: PLC0415
        ajeno = bool(_auto._worktree_maps_to_wrong_repo(origin, project_name))
    except Exception:  # noqa: BLE001 — ante la duda NO se bloquea (igual que la guardia)
        ajeno = False
    if ajeno:
        return _preflight("remoto_ajeno", repo_root=repo_root, origin=origin,
                          workspace_root=workspace_root, project=project_name,
                          tracker_type=tracker_type, provider_label=provider_label)

    # Avisos que NO bloquean. El del subdirectorio importa: el PR va a incluir
    # todo lo que el agente toque en el repo ENTERO, no sólo dentro de la
    # subcarpeta que el proyecto declara como workspace.
    if not origin:
        aviso = "sin_origin"
    elif det.get("es_subdirectorio"):
        aviso = "workspace_es_subdirectorio"
    else:
        aviso = None

    return _preflight(None, repo_root=repo_root, origin=origin,
                      workspace_root=workspace_root, project=project_name,
                      tracker_type=tracker_type, provider_label=provider_label,
                      warning=aviso)


def _listar_proyectos() -> list[str]:
    """Nombres de TODOS los proyectos configurados. Aislado en su propia función
    para poder sustituirlo en tests sin tocar la carpeta `projects/` real."""
    try:
        from project_manager import get_all_projects  # noqa: PLC0415
        nombres = [str((c or {}).get("name") or "").strip() for c in (get_all_projects() or [])]
        return sorted({n for n in nombres if n})
    except Exception:  # noqa: BLE001 — sin proyectos legibles, la vista sale vacía
        logger.info("preflight auto-PR: no se pudieron listar los proyectos", exc_info=True)
        return []


def preflight_all_projects() -> list[dict]:
    """Estado del auto-PR de CADA proyecto configurado, sin cambiar el activo.

    Un proyecto roto no puede tapar a los demás: cada fila se calcula por
    separado y un fallo se reporta EN esa fila. La flag global se ignora a
    propósito — "¿este proyecto tiene git?" y "¿el auto-PR está encendido?" son
    dos preguntas distintas y el operador necesita ver la primera igual.
    """
    filas = []
    for nombre in _listar_proyectos():
        try:
            filas.append(preflight_repo(nombre, ignorar_flag=True))
        except Exception as exc:  # noqa: BLE001
            logger.info("preflight auto-PR: proyecto %s falló", nombre, exc_info=True)
            filas.append(_preflight("sin_proyecto", project=nombre, detalle=str(exc)))
    return filas


# ── Resultado del auto-PR, para que la UI lo pueda mostrar ────────────────────
# Antes el resultado SOLO viajaba como comentario en la Issue del tracker
# (incident_dev_autocommit.py:107/112/120/157/176/181). Desde Stacky era invisible.

#: Claves del intent que se exponen. El `baseline` (un sha1 por archivo dirty del
#: working tree) queda AFUERA a proposito: son kilobytes por poll y filtra el
#: arbol entero del operador.
RESULT_FIELDS = ("pr_url", "pr_id", "branch", "error", "files_committed",
                 "secret_scan_files", "origin", "repo_root", "created_at")

#: Estados en los que ya no tiene sentido seguir consultando.
RESULT_TERMINAL = ("opened", "blocked_empty", "error", "skipped", "no_solicitado")


def result_for_execution(execution_id: int) -> dict:
    """Resultado del auto-PR de un run, con forma ESTABLE para la UI.

    - sin intent  -> status="no_solicitado" (el operador no tildo, o el chequeo
      previo fallo y el intent nunca se registro).
    - intent sin `status` -> "pendiente" (el run todavia no termino).
    """
    intent = get_intent(execution_id) or None
    if not intent:
        return {"ok": True, "found": False, "status": "no_solicitado",
                "terminal": True, "execution_id": int(execution_id)}
    status = (intent.get("status") or "").strip() or "pendiente"
    out = {"ok": True, "found": True, "status": status,
           "terminal": status in RESULT_TERMINAL,
           "execution_id": int(execution_id)}
    for k in RESULT_FIELDS:
        if intent.get(k) is not None:
            out[k] = intent[k]
    return out
