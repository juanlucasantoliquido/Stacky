"""services/pipeline_inventory.py — Plan 246. Inventario vivo de pipelines multiproveedor.

F0 es PURO: sin red, sin LLM. Mismas entradas => mismas salidas.
READ-ONLY ABSOLUTO: este modulo no crea, no edita, no registra y no dispara nada.

NOTA DE IMPLEMENTACION (plan 246, contradiccion F0/F1 declarada): el test #17 de F0 exige
que el modulo no importe `urllib`, `requests`, `ado_client` ni `gitlab_client` a nivel de
modulo. F1 agrega el barrido del repositorio a ESTE MISMO archivo, que necesita `os` y
`yaml`. La lectura literal se conserva: no hay `from os import walk` ni ninguna dependencia
de red a nivel de modulo; los adapters de proveedor se importan siempre dentro de la funcion.
"""
from __future__ import annotations

import difflib
import os
import time
from datetime import datetime, timezone

import yaml

# ── Vocabularios CERRADOS (contrato congelado para 247..252) ──────────────────
CATEGORY_REGISTERED_WITH_FILE: str = "registrada+en_repo"
CATEGORY_REGISTERED_NO_FILE: str = "registrada_sin_archivo"
CATEGORY_FILE_NOT_REGISTERED: str = "en_repo_sin_registrar"
# [v2 - C2] CUARTA categoria: registrada, pero el barrido del repo NO es confiable, asi que
# el inventario NO PUEDE afirmar que el archivo falte. Tono neutro, nunca rojo.
CATEGORY_UNKNOWN_FILE_STATE: str = "registrada_estado_desconocido"
CATEGORIES: tuple[str, ...] = (
    CATEGORY_REGISTERED_WITH_FILE,
    CATEGORY_REGISTERED_NO_FILE,
    CATEGORY_FILE_NOT_REGISTERED,
    CATEGORY_UNKNOWN_FILE_STATE,
)

RUN_STATUSES: tuple[str, ...] = ("success", "failed", "never_ran", "unknown")

PROVIDERS: tuple[str, ...] = ("azure_devops", "gitlab")

SOURCE_ADO_DEFINITIONS: str = "ado_definitions"
SOURCE_GITLAB_PIPELINES: str = "gitlab_pipelines"
SOURCE_REPO_SCAN: str = "repo_scan"

# Rank de orden: mas accionable primero. [v2 - C2] el estado desconocido va ultimo.
_CATEGORY_RANK: dict[str, int] = {
    CATEGORY_REGISTERED_NO_FILE: 0,
    CATEGORY_FILE_NOT_REGISTERED: 1,
    CATEGORY_REGISTERED_WITH_FILE: 2,
    CATEGORY_UNKNOWN_FILE_STATE: 3,
}

# ── Caps (§3.3) ───────────────────────────────────────────────────────────────
_MAX_SCAN_FILES: int = 400
_MAX_SCAN_DEPTH: int = 4
_MAX_YAML_BYTES: int = 512_000
_MAX_BUILDS_SCAN: int = 100
_MAX_HYDRATE: int = 10
_CACHE_TTL_SEC: int = 300


# _map_status (ado_ci_provider.py:135) devuelve el vocabulario GitLab.
# Esta tabla lo lleva al vocabulario de 4 valores del inventario, sin perder el detalle.
RUN_STATUS_FROM_PROVIDER: dict[str, tuple[str, str]] = {
    "success":  ("success", "success"),
    "failed":   ("failed",  "failed"),
    "canceled": ("unknown", "canceled"),   # cancelada no es roja: no dice nada de la salud
    "running":  ("unknown", "running"),
    "pending":  ("unknown", "pending"),
    "created":  ("unknown", "created"),
    "skipped":  ("unknown", "skipped"),
    "manual":   ("unknown", "manual"),
}


def map_run_status(raw: str | None) -> tuple[str, str]:
    """[v2 - C4] UNICA forma permitida de consultar la tabla de estados.

    La tabla es CERRADA (8 filas) pero el vocabulario del proveedor es ABIERTO: la API
    de GitLab tambien emite `waiting_for_resource`, `preparing` y `scheduled`, que NO
    estan en la tabla. Un lookup directo lanzaria KeyError y, como build_inventory
    atrapa todo, un proyecto GitLab SANO apareceria con la fuente caida.
    """
    clean = (raw or "").strip().lower()
    return RUN_STATUS_FROM_PROVIDER.get(clean, ("unknown", clean or "sin_datos"))


def _default_last_run() -> dict:
    return {
        "status": "unknown",
        "status_detail": "sin_datos",
        "at": None,
        "web_url": None,
        "run_id": None,
        "source": None,
    }


def _default_trigger() -> dict:
    return {
        "kind": "unknown",
        "branches": [],
        "has_paths": False,
        "has_schedule": False,
        "has_pr": False,
        "source": None,
    }


def normalize_yaml_path(raw: str | None) -> str:
    """Normaliza una ruta de YAML a la forma canonica de la clave de identidad.

    Reglas, EN ESTE ORDEN:
      1. None/""            -> ""
      2. "\\" -> "/"
      3. strip() de espacios
      4. quitar TODOS los prefijos "./" repetidos (while, no strip)
      5. quitar "/" iniciales (lstrip("/"))
      6. lower()

    TRAMPA (test negativo obligatorio): NO usar lstrip("./") — eso borra el punto
    inicial de ".gitlab-ci.yml" y lo convierte en "gitlab-ci.yml", partiendo en dos
    la identidad de la unica pipeline que GitLab tiene por proyecto.
    """
    if not raw:
        return ""
    out = str(raw).replace("\\", "/").strip()
    while out.startswith("./"):
        out = out[2:]
    out = out.lstrip("/")
    return out.lower()


def identity_key(provider: str, yaml_path: str | None, definition_id: str | None = None) -> str:
    """Clave de identidad DETERMINISTA."""
    norm = normalize_yaml_path(yaml_path)
    if norm:
        return f"{provider}::{norm}"
    if definition_id:
        return f"{provider}::#def{definition_id}"
    return f"{provider}::#desconocida"


def make_entry(
    *,
    provider: str,
    name: str,
    yaml_path: str | None,
    default_branch: str | None,
    definition_id: str | None,
    category: str,
    category_reason: str = "",
    last_run: dict | None = None,
    trigger: dict | None = None,
    found_in: tuple[str, ...] = (),
    hints: list[str] | None = None,
) -> dict:
    """Construye una entrada del inventario con TODAS las claves siempre presentes.

    Shape CONGELADO (contrato que consumen 247..252) - 12 claves:
      key, provider, name, yaml_path, default_branch, definition_id,
      category, category_reason, last_run, trigger, found_in, hints
    `run_id` es SIEMPRE str | None (nunca int). [v2 - C7]
    """
    run = dict(_default_last_run())
    if last_run:
        run.update({k: v for k, v in last_run.items() if k in run})
    trig = dict(_default_trigger())
    if trigger:
        trig.update({k: v for k, v in trigger.items() if k in trig})
    return {
        "key": identity_key(provider, yaml_path, definition_id),
        "provider": provider,
        "name": name,
        "yaml_path": yaml_path,
        "default_branch": default_branch,
        "definition_id": definition_id,
        "category": category,
        "category_reason": category_reason,
        "last_run": run,
        "trigger": trig,
        "found_in": tuple(found_in),
        "hints": list(hints or []),
    }


def _source_of_registered(rec: dict) -> str:
    explicit = rec.get("source")
    if explicit:
        return str(explicit)
    provider = (rec.get("provider") or "").strip().lower()
    if provider == "gitlab":
        return SOURCE_GITLAB_PIPELINES
    return SOURCE_ADO_DEFINITIONS


def _source_of_file(rec: dict) -> str:
    return str(rec.get("source") or SOURCE_REPO_SCAN)


def _key_of(rec: dict) -> str:
    return identity_key(
        rec.get("provider") or "",
        rec.get("yaml_path"),
        rec.get("definition_id"),
    )


def reconcile(
    registered: list[dict], files: list[dict], *, scan_reliable: bool = True
) -> list[dict]:
    """Une definiciones registradas y archivos del repo en UN registro. PURO.

    [v2 - C2] `scan_reliable` es OBLIGATORIO de pasar desde build_inventory. Si es False,
    el barrido NO PUEDE desmentir al proveedor: una definicion sin archivo NO es "rota",
    es "estado desconocido".
    """
    index_reg: dict[str, dict] = {}
    for rec in registered or []:
        index_reg[_key_of(rec)] = rec
    index_file: dict[str, dict] = {}
    for rec in files or []:
        index_file[_key_of(rec)] = rec

    matched = set(index_reg) & set(index_file)

    # [v2 - C5] PASADA 2: solo sobre los residuos, por ruta normalizada SIN provider.
    residual_reg: dict[str, list] = {}
    for key, rec in index_reg.items():
        if key in matched:
            continue
        norm = normalize_yaml_path(rec.get("yaml_path"))
        if norm:
            residual_reg.setdefault(norm, []).append((key, rec))
    residual_file: dict[str, list] = {}
    for key, rec in index_file.items():
        if key in matched:
            continue
        norm = normalize_yaml_path(rec.get("yaml_path"))
        if norm:
            residual_file.setdefault(norm, []).append((key, rec))

    cross: dict[str, tuple[str, dict]] = {}
    absorbed_files: set[str] = set()
    for norm in sorted(residual_reg):
        candidates = residual_file.get(norm)
        if not candidates:
            continue
        for (reg_key, _reg), (file_key, file_rec) in zip(
            sorted(residual_reg[norm]), sorted(candidates)
        ):
            cross[reg_key] = (file_key, file_rec)
            absorbed_files.add(file_key)

    entries: list[dict] = []
    for key in sorted(set(index_reg) | set(index_file)):
        reg = index_reg.get(key)
        file_rec = index_file.get(key)
        reason = ""

        if reg is not None and file_rec is None and key in cross:
            _fk, file_rec = cross[key]
            reason = "match_por_ruta_cross_provider"

        if reg is None and file_rec is not None and key in absorbed_files:
            continue  # absorbido por la pasada 2 dentro de su definicion registrada

        if reg is not None and file_rec is not None:
            entries.append(
                make_entry(
                    provider=reg.get("provider") or "",
                    name=reg.get("name") or file_rec.get("name") or "",
                    yaml_path=file_rec.get("yaml_path"),
                    default_branch=reg.get("default_branch"),
                    definition_id=reg.get("definition_id"),
                    category=CATEGORY_REGISTERED_WITH_FILE,
                    category_reason=reason,
                    last_run=reg.get("last_run"),
                    trigger=file_rec.get("trigger"),
                    found_in=(_source_of_registered(reg), _source_of_file(file_rec)),
                )
            )
            continue

        if reg is not None:
            if scan_reliable:
                category = CATEGORY_REGISTERED_NO_FILE
                if reg.get("yaml_path"):
                    reason = "archivo_ausente_en_repo"
                else:
                    reason = "sin_yaml_declarado"
            else:
                category = CATEGORY_UNKNOWN_FILE_STATE
                reason = "barrido_no_confiable"
            entries.append(
                make_entry(
                    provider=reg.get("provider") or "",
                    name=reg.get("name") or "",
                    yaml_path=reg.get("yaml_path"),
                    default_branch=reg.get("default_branch"),
                    definition_id=reg.get("definition_id"),
                    category=category,
                    category_reason=reason,
                    last_run=reg.get("last_run"),
                    trigger=None,
                    found_in=(_source_of_registered(reg),),
                )
            )
            continue

        entries.append(
            make_entry(
                provider=file_rec.get("provider") or "",
                name=file_rec.get("name") or "",
                yaml_path=file_rec.get("yaml_path"),
                default_branch=file_rec.get("default_branch"),
                definition_id=file_rec.get("definition_id"),
                category=CATEGORY_FILE_NOT_REGISTERED,
                category_reason="huerfana",
                last_run={"status": "never_ran", "status_detail": "no_registrada"},
                trigger=file_rec.get("trigger"),
                found_in=(_source_of_file(file_rec),),
            )
        )

    entries.sort(key=sort_key)
    return entries


def sort_key(entry: dict) -> tuple:
    """Orden CANONICO, mas accionable primero:
    (rank_categoria, provider, name.lower(), key)
    """
    return (
        _CATEGORY_RANK.get(entry.get("category") or "", 99),
        entry.get("provider") or "",
        (entry.get("name") or "").lower(),
        entry.get("key") or "",
    )


def counts(entries: list[dict]) -> dict:
    """{"total": n} + UNA clave por cada valor de CATEGORIES (las 4)."""
    out: dict = {"total": len(entries or [])}
    for category in CATEGORIES:
        out[category] = 0
    for entry in entries or []:
        category = entry.get("category")
        if category in out:
            out[category] += 1
    return out


def nearest_repo_paths(
    target_path: str | None, candidates: list[str], *, limit: int = 3
) -> list[str]:
    """[ADICION ARQUITECTO v2] Rutas del repo mas parecidas a `target_path`.

    stdlib pura, DETERMINISTA, sin red, sin LLM, sin disco. NO decide ni edita nada:
    solo le da al operador la pista de por que la pipeline no reconcilio.
    """
    target = normalize_yaml_path(target_path)
    if not target:
        return []
    pool = [normalize_yaml_path(c) for c in (candidates or [])]
    pool = [p for p in pool if p and p != target]
    if not pool:
        return []
    return list(difflib.get_close_matches(target, pool, n=limit, cutoff=0.6))


def source_ok(source_id: str, count: int, **extra) -> dict:
    """Bloque de fuente disponible."""
    return {
        "id": source_id,
        "available": True,
        "count": int(count),
        "capability": "",
        "provider": "",
        "reason": "",
        "workaround": "",
        **extra,
    }


def source_unavailable(
    source_id: str, *, capability: str, provider: str, reason: str, workaround: str
) -> dict:
    """MISMO shape que source_ok pero available=False y count=0.

    Las claves capability/provider/reason/workaround son EXACTAMENTE las de
    CapabilityUnavailable.to_payload() (services/tracker_provider.py:69-72).
    """
    return {
        "id": source_id,
        "available": False,
        "count": 0,
        "capability": str(capability),
        "provider": str(provider),
        "reason": str(reason),
        "workaround": str(workaround),
    }


# ═════════════════════════════════════════════════════════════════════════════
# F1 — Fuente C: barrido del repositorio (huerfanas + trigger declarado)
# ═════════════════════════════════════════════════════════════════════════════

_IGNORED_DIRS: frozenset[str] = frozenset(
    # Las 7 primeras son LITERALMENTE las de pipeline_stack_detector.py (reuso).
    {"node_modules", ".git", "venv", ".venv", "bin", "obj", "__pycache__",
     # extras propias del 246, declaradas:
     "dist", "build", "packages", ".vs", ".idea", "TestResults"}
)

_PIPELINE_DIR_HINTS: frozenset[str] = frozenset(
    {"pipelines", ".azuredevops", ".pipelines", "azure-pipelines", "ci", ".ci"}
)

_ABSENT = object()


def pipeline_name_from_path(path: str) -> str:
    """Nombre visible = basename sin extension. '.gitlab-ci.yml' -> '.gitlab-ci'."""
    base = os.path.basename(str(path or "").replace("\\", "/"))
    for ext in (".yaml", ".yml"):
        if base.lower().endswith(ext):
            return base[: -len(ext)]
    return base


def classify_pipeline_doc(basename: str, doc: object) -> str | None:
    """Clasifica un YAML ya parseado como 'azure_devops' | 'gitlab' | None.

    REGLAS CERRADAS, EVALUADAS EN ESTE ORDEN (primera que matchea gana).
    DISCIPLINA C20 (Plan 243): el documento SIEMPRE llega parseado por yaml.safe_load.
    PROHIBIDO clasificar por grep/regex sobre el texto: el corpus real tiene referencias
    a tareas DENTRO DE COMENTARIOS y un regex las levanta.
    """
    name = (basename or "").lower()
    if name in (".gitlab-ci.yml", ".gitlab-ci.yaml"):  # R1
        return "gitlab"
    if not isinstance(doc, dict):  # R2
        return None

    stages = doc.get("stages")
    if isinstance(stages, list) and stages and all(isinstance(s, str) for s in stages):  # R3
        return "gitlab"
    if isinstance(stages, list) and any(
        isinstance(s, dict) and ("stage" in s or "template" in s) for s in stages
    ):  # R4
        return "azure_devops"
    if "pool" in doc or "steps" in doc or "jobs" in doc:  # R5
        return "azure_devops"
    if "trigger" in doc:  # R6 — en GitLab `trigger:` es clave de JOB, nunca top-level
        trig = doc.get("trigger")
        if isinstance(trig, (list, dict)) or trig == "none":
            return "azure_devops"
    if "workflow" in doc or "include" in doc:  # R7
        return "gitlab"
    for value in doc.values():  # R8
        if isinstance(value, dict) and "script" in value:
            return "gitlab"
    return None  # R9


def extract_trigger(doc: object, provider: str) -> dict:
    """Extrae SOLO el bloque de disparo. Estructura, nunca texto crudo."""
    out = dict(_default_trigger())
    out["source"] = "yaml"
    if not isinstance(doc, dict):
        return out

    if provider == "azure_devops":
        trig = doc.get("trigger", _ABSENT)
        if trig is _ABSENT:
            out["kind"] = "default"
        elif trig == "none" or trig is None:
            out["kind"] = "none"
        elif isinstance(trig, list):
            out["kind"] = "ci"
            out["branches"] = [str(b) for b in trig]
        elif isinstance(trig, dict) and "branches" in trig:
            out["kind"] = "ci"
            branches = trig.get("branches")
            include = branches.get("include") if isinstance(branches, dict) else None
            out["branches"] = [str(b) for b in include] if isinstance(include, list) else []
            out["has_paths"] = bool(trig.get("paths"))
        else:
            out["kind"] = "unknown"
        out["has_schedule"] = "schedules" in doc
        pr = doc.get("pr", _ABSENT)
        out["has_pr"] = pr is not _ABSENT and pr not in ("none", None)
        return out

    # GitLab — LIMITACIONES DECLARADAS (branches y schedules no viven en el YAML).
    has_job = any(isinstance(v, dict) and "script" in v for v in doc.values())
    out["kind"] = "ci" if ("workflow" in doc or has_job) else "unknown"
    out["branches"] = []
    out["has_paths"] = False
    out["has_schedule"] = False
    workflow = doc.get("workflow")
    rules = workflow.get("rules") if isinstance(workflow, dict) else None
    if isinstance(rules, list):
        for rule in rules:
            cond = rule.get("if") if isinstance(rule, dict) else None
            if isinstance(cond, str) and "merge_request_event" in cond:
                out["has_pr"] = True
                break
    return out


def scan_repo_pipelines(root: str | None) -> tuple[list[dict], dict]:
    """Barre `root` buscando archivos de pipeline. Devuelve (entradas, meta).

    NUNCA lanza: cualquier OSError/UnicodeError/yaml.YAMLError se traduce a que ese
    archivo se salta (y se cuenta en meta).
    """
    meta: dict = {
        "available": False,
        "reason": "sin_workspace_activo",
        "scanned_files": 0,
        "matched": 0,
        "truncated": False,
        "skipped_too_big": 0,
        "skipped_unparseable": 0,
        "root": str(root or ""),
    }
    if not root:
        return [], meta
    try:
        base = os.path.normpath(str(root))
        if not os.path.isdir(base):
            return [], meta
    except Exception:
        return [], meta

    meta["available"] = True
    meta["reason"] = ""
    meta["root"] = base
    entries: list[dict] = []
    scanned = 0
    truncated = False

    try:
        for dirpath, dirnames, filenames in os.walk(base):
            rel_dir = os.path.relpath(dirpath, base)
            depth = 0 if rel_dir == "." else len(rel_dir.replace("\\", "/").split("/"))
            dirnames[:] = sorted(d for d in dirnames if d not in _IGNORED_DIRS)
            if depth >= _MAX_SCAN_DEPTH:
                dirnames[:] = []
            for filename in sorted(filenames):
                low = filename.lower()
                if not (low.endswith(".yml") or low.endswith(".yaml")):
                    continue
                if scanned >= _MAX_SCAN_FILES:
                    truncated = True
                    break
                scanned += 1
                full = os.path.join(dirpath, filename)
                try:
                    if os.path.getsize(full) > _MAX_YAML_BYTES:
                        meta["skipped_too_big"] += 1
                        continue
                except OSError:
                    meta["skipped_unparseable"] += 1
                    continue
                try:
                    with open(full, "r", encoding="utf-8", errors="replace") as fh:
                        doc = yaml.safe_load(fh)
                except Exception:
                    meta["skipped_unparseable"] += 1
                    continue
                provider = classify_pipeline_doc(filename, doc)
                if provider is None:
                    continue
                rel = os.path.relpath(full, base).replace("\\", "/")
                entries.append(
                    {
                        "provider": provider,
                        "name": pipeline_name_from_path(rel),
                        "yaml_path": rel,
                        "default_branch": None,
                        "definition_id": None,
                        "trigger": extract_trigger(doc, provider),
                        "source": SOURCE_REPO_SCAN,
                    }
                )
            if truncated:
                break
    except Exception as exc:  # defensivo: el barrido NUNCA propaga
        meta["reason"] = str(exc)[:200]

    meta["scanned_files"] = scanned
    meta["matched"] = len(entries)
    meta["truncated"] = truncated
    return entries, meta


# ═════════════════════════════════════════════════════════════════════════════
# F3 — Ensamblado de las 2 fuentes con degradacion honesta
# ═════════════════════════════════════════════════════════════════════════════

_CACHE: dict[str, tuple[float, dict]] = {}   # {project_key: (expires_at_monotonic, payload)}

_SOURCE_ID_BY_PROVIDER: dict[str, str] = {
    "azure_devops": SOURCE_ADO_DEFINITIONS,
    "gitlab": SOURCE_GITLAB_PIPELINES,
}
_SOURCE_ID_FALLBACK: str = "provider_definitions"


def clear_cache() -> None:
    """Vacia _CACHE. Existe para los tests y para el ?refresh=1 del endpoint."""
    _CACHE.clear()


def _scan_reliable(meta_scan: dict) -> bool:
    """[v2 - C2 / R15] El barrido no puede DESMENTIR al proveedor: si no vio, no afirma."""
    if not meta_scan.get("available"):
        return False
    if meta_scan.get("truncated"):
        return False
    if int(meta_scan.get("matched") or 0) == 0 and int(meta_scan.get("scanned_files") or 0) > 0:
        return False
    return True


def build_inventory(project: str | None = None, *, refresh: bool = False,
                    describe: bool = False) -> dict:
    """Arma el inventario COMPLETO. NUNCA LANZA. Devuelve siempre un dict valido.

    Plan 294 F10 — `describe` es ADITIVO: sin el parametro la salida es
    byte-identica a la de siempre (R10). Con el, cada entrada pasa por
    `describe_pipeline` y suma sus 6 claves de ficha; las 12 originales quedan
    intactas.

    LA CLAVE DEL CACHE INCLUYE `describe` A PROPOSITO: si no, un pedido SIN
    ficha envenena durante los 5 minutos del TTL al pedido CON ficha, y el bug
    reaparece con otra cara.
    """
    cache_key = f"{project or ''}|{int(bool(describe))}"
    if not refresh:
        cached = _CACHE.get(cache_key)
        if cached and time.monotonic() < cached[0]:
            payload = dict(cached[1])
            age = max(0, int(_CACHE_TTL_SEC - (cached[0] - time.monotonic())))
            payload["cached"] = True
            payload["cache_age_sec"] = age
            return payload

    registered: list[dict] = []
    src_prov: dict | None = None
    provider = None
    try:
        from services.ci_provider import get_ci_provider  # noqa: PLC0415

        provider = get_ci_provider(project)
    except Exception as exc:
        src_prov = source_unavailable(
            _SOURCE_ID_FALLBACK,
            capability="list_pipeline_definitions",
            provider="desconocido",
            reason=str(exc)[:200],
            workaround="Configura el tracker del proyecto en Configuracion -> Proyectos.",
        )

    if provider is not None:
        # INVARIANTE: nada de lo de abajo puede propagar. Incluso leer `.name` puede
        # explotar en un adapter roto, y eso NO puede tumbar el inventario entero.
        try:
            provider_name = str(getattr(provider, "name", "") or "desconocido")
        except Exception:
            provider_name = "desconocido"
        source_id = _SOURCE_ID_BY_PROVIDER.get(provider_name, _SOURCE_ID_FALLBACK)
        try:
            lister = getattr(provider, "list_pipeline_definitions", None)
        except Exception:
            lister = None
        if not callable(lister):
            src_prov = source_unavailable(
                source_id,
                capability="list_pipeline_definitions",
                provider=provider_name,
                reason="El adapter de CI de este proveedor todavia no expone el inventario.",
                workaround=(
                    "Actualiza Stacky o usa el barrido del repositorio, "
                    "que ya esta listado abajo."
                ),
            )
        else:
            try:
                registered, meta_prov = lister()
                meta_prov = meta_prov or {}
                if meta_prov.get("available"):
                    src_prov = source_ok(
                        source_id,
                        len(registered),
                        **{
                            k: meta_prov[k]
                            for k in ("capped", "hydrated", "truncated_hydration", "calls")
                            if k in meta_prov
                        },
                    )
                else:
                    registered = []
                    src_prov = source_unavailable(
                        source_id,
                        capability="list_pipeline_definitions",
                        provider=provider_name,
                        reason=str(meta_prov.get("reason") or "fuente no disponible")[:200],
                        workaround=(
                            "Revisa las credenciales del proveedor en "
                            "Configuracion -> Proyectos."
                        ),
                    )
            except Exception as exc:
                registered = []
                src_prov = source_unavailable(
                    source_id,
                    capability="list_pipeline_definitions",
                    provider=provider_name,
                    reason=str(exc)[:200],
                    workaround="Revisa las credenciales del proveedor.",
                )

    files: list[dict] = []
    meta_scan: dict = {"available": False, "reason": "sin_workspace_activo"}
    try:
        from runtime_paths import _active_workspace_root  # noqa: PLC0415

        root = _active_workspace_root()
        files, meta_scan = scan_repo_pipelines(str(root) if root else "")
    except Exception as exc:
        files = []
        meta_scan = {"available": False, "reason": str(exc)[:200]}

    if meta_scan.get("available"):
        src_scan = source_ok(
            SOURCE_REPO_SCAN,
            len(files),
            **{
                k: meta_scan[k]
                for k in ("truncated", "skipped_too_big", "skipped_unparseable", "scanned_files")
                if k in meta_scan
            },
        )
    else:
        src_scan = source_unavailable(
            SOURCE_REPO_SCAN,
            capability="scan_repo_pipelines",
            provider="local",
            reason=str(meta_scan.get("reason") or "sin_workspace_activo")[:200],
            workaround="Abri el repositorio del proyecto como espacio de trabajo activo.",
        )

    entries = reconcile(registered, files, scan_reliable=_scan_reliable(meta_scan))

    file_paths = [f.get("yaml_path") or "" for f in files]
    reg_paths = [r.get("yaml_path") or "" for r in registered]
    for entry in entries:
        if entry["category"] == CATEGORY_REGISTERED_NO_FILE:
            entry["hints"] = nearest_repo_paths(entry.get("yaml_path"), file_paths)
        elif entry["category"] == CATEGORY_FILE_NOT_REGISTERED:
            entry["hints"] = nearest_repo_paths(entry.get("yaml_path"), reg_paths)

    salida = entries
    if describe:
        # Plan 294 F10 — la ficha se calcula DESPUES de reconciliar, sobre las
        # entradas ya armadas: no toca `reconcile` ni el shape de `make_entry`.
        salida = []
        for entry in entries:
            texto = None
            try:
                texto, _ = get_pipeline_yaml(entry.get("key") or "")
            except Exception:      # noqa: BLE001 — sin archivo legible: sin ficha
                texto = None
            salida.append(describe_pipeline(entry, texto))

    payload = {
        "ok": True,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "cached": False,
        "cache_age_sec": 0,
        "project": project or "",
        "counts": counts(entries),
        "sources": [src_prov, src_scan],   # SIEMPRE 2, nunca 3  [v2 - C3]
        "pipelines": salida,
    }
    _CACHE[cache_key] = (time.monotonic() + _CACHE_TTL_SEC, payload)
    return payload


# ═════════════════════════════════════════════════════════════════════════════
# Plan 294 F2 — El inventario habla castellano (y se cierra el bug vivo GAP-6)
#
# NADA DE ACA REESCRIBE LO DE ARRIBA. Son DOS funciones ADITIVAS:
#   · get_pipeline_yaml  — la funcion que api/pipeline_profiler.py:32 YA importa
#                          y que nunca existio (por eso el perfil por pipeline_id
#                          devolvia 501 SIEMPRE).
#   · describe_pipeline  — enriquece UNA entrada con la ficha en castellano que
#                          services/pipeline_profiler.py ya sabe generar, sin
#                          gastar un token. AGREGA claves; jamas toca las 12.
# ═════════════════════════════════════════════════════════════════════════════

#: Tabla CERRADA de traduccion del disparador. Se consulta SIEMPRE con .get():
#: el vocabulario del proveedor es ABIERTO y un lookup con [] lanzaria KeyError.
#: Como describe_pipeline atrapa todo, un proyecto sano apareceria SIN ficha.
_WHEN_ES: dict[str, str] = {
    "ci": "cuando alguien sube algo a {ramas}",
    "default": "cuando alguien sube algo a la rama principal",
    "none": "solo cuando lo pedis a mano",
    "unknown": "no se pudo determinar cuando se ejecuta",
}


def _frase_de_trigger(trigger: dict | None) -> str:
    """Traduce el bloque `trigger` del inventario a castellano. NUNCA lanza."""
    trig = trigger if isinstance(trigger, dict) else {}
    kind = str(trig.get("kind") or "unknown").strip().lower()
    plantilla = _WHEN_ES.get(kind)
    if plantilla is None:
        return _WHEN_ES["unknown"]
    if "{ramas}" not in plantilla:
        return plantilla
    ramas = [str(r) for r in (trig.get("branches") or []) if str(r).strip()]
    if not ramas:
        return _WHEN_ES["default"]
    return plantilla.format(ramas=", ".join(ramas))


def get_pipeline_yaml(pipeline_key: str, project: str | None = None) -> tuple[str, str]:
    """Devuelve (yaml_text, source_path) para una `key` del inventario.

    Cierra GAP-6: es la funcion que api/pipeline_profiler.py ya importaba y que
    no existia. SOLO lee del WORKSPACE local (nunca de red). Si la key no
    resuelve a un archivo legible dentro del workspace, lanza KeyError (el
    endpoint lo mapea a 404).

    `project` se acepta para que la firma sea la del contrato publicado; hoy el
    workspace activo ya esta resuelto por runtime_paths y no se usa para elegir
    otra raiz. Se ignora a proposito en vez de fingir un ruteo que no existe.
    """
    from pathlib import Path                              # noqa: PLC0415
    from runtime_paths import _active_workspace_root      # noqa: PLC0415

    _ = project  # ver docstring: parte del contrato, sin efecto hoy
    root = _active_workspace_root()
    if not root:
        raise KeyError("sin_workspace_activo")
    raiz = Path(str(root)).resolve()

    # la key es "<provider>::<ruta normalizada>"  (identity_key)
    if "::" not in (pipeline_key or ""):
        raise KeyError("clave_invalida")
    _prov, _, rel = pipeline_key.partition("::")
    if not rel or rel.startswith("#"):   # "#def123" / "#desconocida": no hay archivo
        raise KeyError("sin_archivo_en_repo")

    ruta = (raiz / rel).resolve()
    # ANTI PATH TRAVERSAL — el archivo tiene que colgar de la raiz del workspace.
    if raiz != ruta and raiz not in ruta.parents:
        raise KeyError("fuera_del_workspace")
    if not ruta.is_file():
        raise KeyError("archivo_inexistente")
    if ruta.stat().st_size > _MAX_YAML_BYTES:   # reusa el cap que YA existe arriba
        raise KeyError("archivo_demasiado_grande")
    return ruta.read_text(encoding="utf-8", errors="replace"), rel


def _fases_es(perfil) -> list[str]:
    """Etapas afirmadas por el perfilador, en castellano y EN ORDEN. Solo las
    que el perfil declara `True`: una fase ausente no se inventa."""
    from services.pipeline_profiler import PHASE_IDS, _PHASE_VERBS  # noqa: PLC0415

    fases = perfil.phases or {}
    out: list[str] = []
    for pid in PHASE_IDS:
        campo = fases.get(pid)
        if campo is not None and campo.value is True:
            out.append(str(_PHASE_VERBS.get(pid, pid)))
    return out


def _artefactos_es(perfil) -> list[str]:
    valores = perfil.artifacts_published.value or ()
    return [str(a) for a in valores]


def _entornos_es(perfil) -> list[str]:
    """[ADICION ARQUITECTO 3] Lista de ambientes a los que la pipeline despliega.

    Lista VACIA con purpose_source == "plantilla" es una AFIRMACION ("no
    despliega"). purpose_source == "sin_datos" es IGNORANCIA ("no se pudo
    determinar"). La UI NUNCA debe confundir esos dos casos: afirmar "no
    despliega" sobre una pipeline que despliega a produccion es el peor error
    posible antes de encolar una corrida real.
    """
    refs = perfil.environments.value or ()
    out: list[str] = []
    for ref in refs:
        nombre = getattr(ref, "name", "")
        if getattr(ref, "resolved", True):
            out.append(str(nombre))
        else:
            out.append("(no se pudo resolver el nombre del ambiente)")
    return out


def describe_pipeline(entry: dict, yaml_text: str | None) -> dict:
    """Enriquece UNA entrada del inventario con la ficha en castellano.

    AGREGA 6 claves; NUNCA quita ni renombra las 12 de make_entry (R10):
      purpose, purpose_source, stages_es, when_es, artifacts_es, environments_es.
    Si `yaml_text` es None o no parsea: purpose_source == "sin_datos" y el resto
    vacio. NUNCA LANZA: la ficha degrada, el inventario no se rompe.
    """
    out = dict(entry if isinstance(entry, dict) else {})
    out["purpose"] = ""
    out["purpose_source"] = "sin_datos"
    out["stages_es"] = []
    out["artifacts_es"] = []
    out["environments_es"] = []
    out["when_es"] = _frase_de_trigger(out.get("trigger"))
    if not yaml_text:
        return out
    # La LISTA del inventario esta gateada por su propia flag; la FICHA depende
    # del perfilador, que tiene la suya. Que falte la segunda degrada la ficha a
    # "no se pudo determinar", nunca la lista. Nunca al reves.
    try:
        import config as _config                            # noqa: PLC0415

        if not getattr(_config.config, "STACKY_PIPELINE_PROFILER_ENABLED", False):
            return out
    except Exception:            # noqa: BLE001 — sin config legible, se degrada igual
        return out
    try:
        from services.pipeline_profiler import (            # noqa: PLC0415
            build_purpose_template,
            profile_pipeline,
        )

        perfil = profile_pipeline(yaml_text, source_path=out.get("yaml_path") or "")
        if perfil.parse_error:
            # el YAML no se pudo leer: es IGNORANCIA, no una afirmacion.
            return out
        out["purpose"] = build_purpose_template(perfil)  # determinista, <=200, SIN modelo
        out["purpose_source"] = "plantilla"
        out["stages_es"] = _fases_es(perfil)
        out["artifacts_es"] = _artefactos_es(perfil)
        out["environments_es"] = _entornos_es(perfil)
    except Exception:            # noqa: BLE001 — la ficha degrada, el inventario nunca rompe
        out["purpose"] = ""
        out["purpose_source"] = "sin_datos"
        out["stages_es"] = []
        out["artifacts_es"] = []
        out["environments_es"] = []
    return out
