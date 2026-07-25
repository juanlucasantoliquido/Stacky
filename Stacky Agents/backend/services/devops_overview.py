"""Plan 239 F1 — agregación read-only del panel DevOps.

REGLA DURA: este módulo NO abre red, NO ejecuta comandos remotos y NO invoca LLM.
Lee únicamente: services.deploy_store (bitácora local), services.ci_run_ledger
(bitácora local), el snapshot en memoria del doctor de conexiones y
services.server_registry. El drift (api/devops_deployments.py) queda EXCLUIDO
a propósito: ejecuta un comando en el servidor remoto y sería una acción, no una lectura.

Todo lo de acá abajo es puro salvo `build_overview`, que es el ÚNICO punto con
efectos de lectura. Cada fuente va en su propio try/except: una fuente rota degrada
su bloque y el resto del payload sigue vivo (el endpoint es siempre 200).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

CFR_DANGER = 0.30
CFR_MIN_SAMPLE = 3
MTTR_WARN_MINUTES = 240
DEPLOY_STALE_DAYS = 21
CI_FAILURES_WARN = 2
CI_STUCK_MINUTES = 120
SERIES_DAYS = 14
RECENT_LIMIT = 12
CI_READ_LIMIT = 200
LEDGER_READ_LIMIT = 500

ALLOWED_WINDOW_DAYS = (7, 14, 30)   # cualquier otro valor ⇒ SERIES_DAYS (14)
_FILTER_MAX_CHARS = 200

_CI_FAILED = {"failed", "failure", "canceled", "cancelled", "error"}
_CI_RUNNING = {"running", "inprogress", "in_progress", "pending", "queued"}

_TONE_RANK = {"danger": 0, "warning": 1, "info": 2}


# ── helpers de tiempo ────────────────────────────────────────────────────────

def parse_iso(value) -> datetime | None:
    """Tolerante: None/""/basura/tipo equivocado ⇒ None. Sufijo "Z" ⇒ UTC.
    Naive ⇒ se asume UTC (mismo criterio que services/harness/telemetry.py)."""
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except (ValueError, TypeError):
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def day_key(dt: datetime) -> str:
    """"YYYY-MM-DD" en UTC."""
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d")


def build_day_axis(now_utc: datetime, days: int = SERIES_DAYS) -> list[str]:
    """Exactamente `days` claves, viejo→nuevo, terminando en day_key(now_utc)."""
    if days < 1:
        days = SERIES_DAYS
    return [day_key(now_utc - timedelta(days=offset)) for offset in range(days - 1, -1, -1)]


def bucket_by_day(timestamps: list[str], axis: list[str]) -> list[int]:
    """Cuenta por día; lo que cae fuera del eje se descarta."""
    index = {key: pos for pos, key in enumerate(axis)}
    out = [0] * len(axis)
    for raw in timestamps or []:
        parsed = parse_iso(raw)
        if parsed is None:
            continue
        pos = index.get(day_key(parsed))
        if pos is not None:
            out[pos] += 1
    return out


# ── agregación de despliegues ────────────────────────────────────────────────

def _terminated_deploys(entries: list[dict]) -> list[dict]:
    """Solo los `action == "deploy"` YA TERMINADOS, del más nuevo al más viejo."""
    rows = [
        e for e in (entries or [])
        if isinstance(e, dict) and e.get("action") == "deploy" and e.get("finished_at")
    ]
    return sorted(rows, key=lambda e: str(e.get("finished_at") or ""), reverse=True)


def last_failed_terminated_by_target(entries_by_app: dict[str, list[dict]]) -> dict:
    """(app, target) → último deploy TERMINADO, solo si terminó en fallo.

    Los entries en curso (`finished_at: null`) y los `action` distintos de `deploy`
    (p. ej. `rollback`) se ignoran: avisar "el último deploy falló" porque hay uno
    corriendo —o porque hubo un rollback— sería mentir.
    """
    from services import deploy_planner

    vistos: dict = {}
    for app_id, entries in (entries_by_app or {}).items():
        for row in _terminated_deploys(entries):
            clave = (app_id, row.get("target"))
            if clave in vistos:
                continue
            vistos[clave] = row
    return {
        clave: row for clave, row in vistos.items()
        if row.get("status") in deploy_planner.FAILED_STATUSES
    }


def aggregate_deploy_metrics(entries_by_app: dict[str, list[dict]], now_utc) -> dict:
    """DOS llamadas a deploy_planner.dora_metrics; CERO cálculo DORA propio.

    (A) UNA llamada sobre la CONCATENACIÓN de todas las apps ⇒ deploys_7d,
        deploys_30d, change_failure_rate_30d y cfr_sample_30d. Sobre el total el
        CFR ya es fallos/(fallos+éxitos) global: sin promediar promedios.
    (B) UNA llamada POR APP para los dos valores que la concatenación falsearía:
        - mttr_minutes_30d: promedio simple de los no-None (None si ninguna app tiene).
          En la concatenación, un fallo de la app X se "recuperaría" con un éxito de
          la app Y ⇒ MTTR inventado.
        - last_deploy_at: MÁXIMO de los last_deploy_at por app (ISO comparable).
    """
    from services import deploy_planner

    entries_by_app = entries_by_app or {}
    todos = [e for lst in entries_by_app.values() for e in (lst or [])]
    consolidado = deploy_planner.dora_metrics(todos, now_utc)

    mttrs: list[float] = []
    last_deploys: list[str] = []
    for entries in entries_by_app.values():
        por_app = deploy_planner.dora_metrics(entries or [], now_utc)
        if por_app.get("mttr_minutes_30d") is not None:
            mttrs.append(float(por_app["mttr_minutes_30d"]))
        if por_app.get("last_deploy_at"):
            last_deploys.append(str(por_app["last_deploy_at"]))

    return {
        "deploys_7d": consolidado["deploys_7d"],
        "deploys_30d": consolidado["deploys_30d"],
        "change_failure_rate_30d": consolidado["change_failure_rate_30d"],
        "cfr_sample_30d": consolidado.get("cfr_sample_30d", 0),
        "mttr_minutes_30d": (sum(mttrs) / len(mttrs)) if mttrs else None,
        "last_deploy_at": max(last_deploys) if last_deploys else None,
        "last_failed_by_target": last_failed_terminated_by_target(entries_by_app),
    }


# ── agregación de CI ─────────────────────────────────────────────────────────

def _ci_status(run: dict) -> str:
    return str(run.get("last_status") or "").strip().lower()


def _ci_started(run: dict) -> str | None:
    """La bitácora del plan 191 guarda `triggered_at`; se acepta `started_at` por si
    una fuente futura lo trae con el otro nombre."""
    return run.get("triggered_at") or run.get("started_at")


def aggregate_ci(runs: list[dict], now_utc) -> dict:
    runs = [r for r in (runs or []) if isinstance(r, dict)]
    en_7d = []
    for run in runs:
        cuando = parse_iso(_ci_started(run))
        if cuando is not None and (now_utc - cuando) <= timedelta(days=7):
            en_7d.append(run)
    fallidas = [r for r in en_7d if _ci_status(r) in _CI_FAILED]
    fallidas.sort(key=lambda r: str(_ci_started(r) or ""), reverse=True)
    return {
        "ci_runs_7d": len(en_7d),
        "ci_failures_7d": len(fallidas),
        "ci_running_now": sum(1 for r in runs if _ci_status(r) in _CI_RUNNING),
        "last_failure": fallidas[0] if fallidas else None,
    }


def _ci_stuck(runs: list[dict], now_utc) -> dict | None:
    for run in runs or []:
        if _ci_status(run) not in _CI_RUNNING:
            continue
        cuando = parse_iso(_ci_started(run))
        if cuando is not None and (now_utc - cuando) > timedelta(minutes=CI_STUCK_MINUTES):
            return run
    return None


# ── alertas (tabla congelada F1.2) ───────────────────────────────────────────

def _alert(aid, tone, title, detail, section) -> dict:
    return {"id": aid, "tone": tone, "title": title, "detail": detail, "section": section}


def derive_alerts(kpis: dict, ctx: dict, now_utc) -> list[dict]:
    """Aplica la tabla F1.2. Se ordena por tono (danger → warning → info) con orden
    estable, así el primero SIEMPRE es el más grave sin perder el orden de la tabla."""
    alerts: list[dict] = []
    ctx = ctx or {}
    deploy_ok = ctx.get("deploy_available", True)
    ci_ok = ctx.get("ci_available", True)
    conns_ok = ctx.get("connections_available", True)
    servers_ok = ctx.get("servers_available", True)

    # ── despliegues ──
    if deploy_ok:
        last_failed = ctx.get("last_failed_by_target") or {}
        if last_failed:
            destinos = ", ".join(f"{app}/{target}" for app, target in sorted(last_failed))
            alerts.append(_alert(
                "deploy_last_failed", "danger",
                f"El último despliegue terminado falló en {len(last_failed)} destino(s)",
                f"Destinos afectados: {destinos}.", "despliegues"))

        cfr = kpis.get("change_failure_rate_30d")
        muestra = kpis.get("cfr_sample_30d") or 0
        if cfr is not None and cfr >= CFR_DANGER and muestra >= CFR_MIN_SAMPLE:
            alerts.append(_alert(
                "deploy_failure_rate", "danger",
                f"{round(cfr * 100)}% de los despliegues de los últimos 30 días falló",
                f"Calculado sobre {muestra} despliegues terminados.", "despliegues"))

        bloqueados = ctx.get("locked_targets") or []
        if bloqueados:
            alerts.append(_alert(
                "deploy_locked", "warning",
                f"{len(bloqueados)} destino(s) con un despliegue en curso",
                "Mientras dure el bloqueo no se puede lanzar otro despliegue al mismo destino.",
                "despliegues"))

        mttr = kpis.get("mttr_minutes_30d")
        if mttr is not None and mttr >= MTTR_WARN_MINUTES:
            alerts.append(_alert(
                "mttr_high", "warning",
                f"Recuperarse de un despliegue fallido está tomando {round(mttr)} minutos",
                f"El umbral de aviso son {MTTR_WARN_MINUTES} minutos.", "despliegues"))

        ultimo = parse_iso(kpis.get("last_deploy_at"))
        if (kpis.get("apps_total") or 0) >= 1 and ultimo is not None:
            dias = (now_utc - ultimo).days
            if dias > DEPLOY_STALE_DAYS:
                alerts.append(_alert(
                    "deploy_stale", "warning",
                    f"Hace {dias} días que no se despliega nada",
                    f"El último despliegue registrado es del {day_key(ultimo)}.", "despliegues"))

        if (kpis.get("targets_configured") or 0) >= 1 and not kpis.get("last_deploy_at"):
            alerts.append(_alert(
                "deploy_never", "info",
                "Hay destinos configurados pero todavía no se desplegó nunca",
                "La bitácora de despliegues está vacía.", "despliegues"))

    # ── CI ──
    if ci_ok:
        fallos = kpis.get("ci_failures_7d") or 0
        if fallos >= CI_FAILURES_WARN:
            ultima = ctx.get("ci_last_failure") or {}
            detalle = "Sin detalle de la más reciente."
            if ultima:
                detalle = (f"La más reciente: proyecto {ultima.get('project') or 'n/d'}, "
                           f"pipeline {ultima.get('pipeline_id') or 'n/d'}.")
            alerts.append(_alert(
                "ci_failures", "warning",
                f"{fallos} corridas de CI fallaron en los últimos 7 días",
                detalle, "pipelines"))

        trabada = _ci_stuck(ctx.get("ci_runs") or [], now_utc)
        if trabada is not None:
            alerts.append(_alert(
                "ci_stuck", "warning",
                "Hay una corrida de CI que lleva demasiado tiempo en curso",
                f"Proyecto {trabada.get('project') or 'n/d'}, pipeline "
                f"{trabada.get('pipeline_id') or 'n/d'} (más de {CI_STUCK_MINUTES} minutos).",
                "pipelines"))

    # ── conexiones ──
    if conns_ok:
        snapshot = ctx.get("snapshot")
        if snapshot is None:
            alerts.append(_alert(
                "connections_never", "info",
                "Todavía no se corrió el chequeo de conexiones",
                "El chequeo lo dispara el operador desde Servidores; nada corre solo.",
                "servidores"))
        else:
            resultados = snapshot.get("results") or []
            malos = [r for r in resultados if str(r.get("status") or "").lower() not in ("ok", "skip")]
            if malos:
                alerts.append(_alert(
                    "connections_down", "danger",
                    f"{len(malos)} chequeo(s) de conexión no están en verde",
                    "Abrí Servidores para ver el detalle y la remediación sugerida.",
                    "servidores"))
            if ctx.get("connections_stale"):
                alerts.append(_alert(
                    "connections_stale", "info",
                    "El chequeo de conexiones está viejo",
                    "Volvé a correrlo desde Servidores para ver el estado de ahora.",
                    "servidores"))

    # ── servidores ──
    if servers_ok and (kpis.get("servers_total") or 0) == 0:
        alerts.append(_alert(
            "no_servers", "info",
            "No hay servidores registrados",
            "Agregá uno en Servidores para poder desplegar y usar la consola remota.",
            "servidores"))

    alerts.sort(key=lambda a: _TONE_RANK.get(a["tone"], 3))
    return alerts


def derive_status(alerts: list[dict], blocks: dict) -> str:
    """danger > warning > ok, y `ok` SOLO si hay al menos un bloque con datos.
    Prohibido devolver `ok` sin datos (guardarraíl 6)."""
    tonos = {a.get("tone") for a in (alerts or [])}
    if "danger" in tonos:
        return "danger"
    if "warning" in tonos:
        return "warning"
    con_datos = any(
        b.get("available") and b.get("reason") is None
        for b in (blocks or {}).values()
    )
    return "ok" if con_datos else "unknown"


# ── actividad reciente ───────────────────────────────────────────────────────

def _deploy_tone(status: str) -> str:
    from services import deploy_planner
    if status == "success":
        return "success"
    if status in deploy_planner.FAILED_STATUSES:
        return "danger"
    return "neutral"


def _ci_tone(status: str) -> str:
    if status in _CI_FAILED:
        return "danger"
    if status in _CI_RUNNING:
        return "info"
    if status in ("success", "succeeded", "passed"):
        return "success"
    return "neutral"


def build_recent(deploy_entries: list[dict], ci_runs: list[dict],
                 limit: int = RECENT_LIMIT) -> list[dict]:
    eventos: list[dict] = []
    for row in deploy_entries or []:
        cuando = row.get("finished_at") or row.get("started_at")
        if not cuando:
            continue
        status = str(row.get("status") or "").strip().lower()
        accion = str(row.get("action") or "deploy")
        eventos.append({
            "at": cuando,
            "kind": "deploy",
            "tone": _deploy_tone(status),
            "title": f"{accion.capitalize()} {row.get('app_id') or 'n/d'} → {row.get('target') or 'n/d'}",
            "status": status or "n/d",
            "section": "despliegues",
            "app_id": row.get("app_id"),
            "project": None,
        })
    for run in ci_runs or []:
        cuando = _ci_started(run)
        if not cuando:
            continue
        status = _ci_status(run)
        eventos.append({
            "at": cuando,
            "kind": "ci",
            "tone": _ci_tone(status),
            "title": f"CI {run.get('project') or 'n/d'} · pipeline {run.get('pipeline_id') or 'n/d'}",
            "status": status or "n/d",
            "section": "pipelines",
            "app_id": None,
            "project": run.get("project"),
        })
    eventos.sort(key=lambda e: str(e["at"]), reverse=True)
    return eventos[:limit]


# ── filtros (F1.2b) ──────────────────────────────────────────────────────────

def _clean_filter(value) -> str | None:
    if not isinstance(value, str):
        return None
    recortado = value.strip()
    if not recortado or len(recortado) > _FILTER_MAX_CHARS:
        return None
    return recortado


def normalize_filters(app_id, project, window_days,
                      valid_apps=None, valid_projects=None) -> dict:
    """Saneamiento ESTRICTO (nunca confía en el query string).

    `valid_apps`/`valid_projects` son el universo SIN filtrar (options): un valor que
    no esté ahí se DESCARTA a None — no se filtra por algo inexistente y el eco
    `filters` dice None, así el operador ve qué se aplicó de verdad. Si vienen en
    None no se chequea pertenencia (uso en tests unitarios del saneamiento).
    """
    limpio_app = _clean_filter(app_id)
    if limpio_app is not None and valid_apps is not None and limpio_app not in valid_apps:
        limpio_app = None
    limpio_proj = _clean_filter(project)
    if limpio_proj is not None and valid_projects is not None and limpio_proj not in valid_projects:
        limpio_proj = None

    ventana = SERIES_DAYS
    if isinstance(window_days, bool):
        ventana = SERIES_DAYS
    elif isinstance(window_days, int) and window_days in ALLOWED_WINDOW_DAYS:
        ventana = window_days
    return {"app_id": limpio_app, "project": limpio_proj, "window_days": ventana}


# ── orquestador (ÚNICO punto con lectura) ────────────────────────────────────

def _flag(name: str) -> bool:
    import config as _config
    return bool(getattr(_config.config, name, False))


def build_overview(now_utc: datetime | None = None, app_id: str | None = None,
                   project: str | None = None, window_days: int = SERIES_DAYS) -> dict:
    now_utc = now_utc or datetime.now(timezone.utc)
    blocks = {
        "deployments": {"available": False, "reason": "flag_off"},
        "ci": {"available": False, "reason": "flag_off"},
        "connections": {"available": False, "reason": "flag_off"},
        "servers": {"available": False, "reason": "flag_off"},
    }

    # ── deployments ──
    apps: list[dict] = []
    entries_by_app: dict[str, list[dict]] = {}
    locked_targets: list[tuple] = []
    if _flag("STACKY_DEPLOYMENTS_ENABLED"):
        try:
            from services import deploy_store
            apps = list(deploy_store.list_apps() or [])
            for app in apps:
                aid = app.get("id")
                if not aid:
                    continue
                entries_by_app[aid] = list(
                    deploy_store.read_ledger(app_id=aid, limit=LEDGER_READ_LIMIT) or [])
                for target in (app.get("targets") or {}):
                    try:
                        if deploy_store.is_locked(aid, target):
                            locked_targets.append((aid, target))
                    except Exception:  # noqa: BLE001 — un lock ilegible no rompe el resumen
                        pass
            tiene_datos = any(entries_by_app.values())
            blocks["deployments"] = {
                "available": True,
                "reason": None if tiene_datos else "sin_datos",
            }
        except Exception:  # noqa: BLE001 — degradar el bloque, jamás propagar
            apps, entries_by_app, locked_targets = [], {}, []
            blocks["deployments"] = {"available": False, "reason": "error_lectura"}

    # ── ci ──
    ci_runs: list[dict] = []
    if _flag("STACKY_CI_RUN_LEDGER_ENABLED"):
        try:
            from services import ci_run_ledger
            ci_runs = list(ci_run_ledger.list_runs(project=None, limit=CI_READ_LIMIT) or [])
            blocks["ci"] = {"available": True, "reason": None if ci_runs else "sin_datos"}
        except Exception:  # noqa: BLE001
            ci_runs = []
            blocks["ci"] = {"available": False, "reason": "error_lectura"}

    # ── connections (SOLO lectura del snapshot: correrlo es un POST del operador) ──
    snapshot = None
    connections_stale = False
    if _flag("STACKY_DEVOPS_CONNECTION_DOCTOR_ENABLED"):
        try:
            import api.devops_connections as _conns
            snapshot = _conns.get_snapshot()
            if snapshot is not None:
                try:
                    connections_stale = bool(_conns._is_stale(snapshot))
                except Exception:  # noqa: BLE001
                    connections_stale = False
            blocks["connections"] = {
                "available": True,
                "reason": None if snapshot is not None else "sin_datos",
            }
        except Exception:  # noqa: BLE001
            snapshot = None
            blocks["connections"] = {"available": False, "reason": "error_lectura"}

    # ── servers ──
    servers: list[dict] = []
    if _flag("STACKY_DEVOPS_SERVERS_ENABLED"):
        try:
            from services import server_registry
            servers = list(server_registry.list_servers() or [])
            blocks["servers"] = {"available": True, "reason": None if servers else "sin_datos"}
        except Exception:  # noqa: BLE001
            servers = []
            blocks["servers"] = {"available": False, "reason": "error_lectura"}

    # ── options: SIEMPRE sobre el universo SIN filtrar ──
    options = {
        "apps": [{"id": a.get("id"), "name": a.get("name") or a.get("id")}
                 for a in apps if a.get("id")],
        "projects": sorted({str(r.get("project")) for r in ci_runs if r.get("project")}),
    }
    filters = normalize_filters(
        app_id, project, window_days,
        valid_apps={a["id"] for a in options["apps"]},
        valid_projects=set(options["projects"]),
    )

    # ── el filtro se aplica ANTES de derivar nada ──
    if filters["app_id"]:
        entries_by_app = {k: v for k, v in entries_by_app.items() if k == filters["app_id"]}
        locked_targets = [t for t in locked_targets if t[0] == filters["app_id"]]
        apps_en_alcance = [a for a in apps if a.get("id") == filters["app_id"]]
    else:
        apps_en_alcance = apps
    if filters["project"]:
        ci_runs = [r for r in ci_runs if r.get("project") == filters["project"]]

    deploy_agg = aggregate_deploy_metrics(entries_by_app, now_utc)
    ci_agg = aggregate_ci(ci_runs, now_utc)
    snap_summary = (snapshot or {}).get("summary") or {}
    resultados = (snapshot or {}).get("results") or []
    targets_configured = sum(len(a.get("targets") or {}) for a in apps_en_alcance)

    kpis = {
        "deploys_7d": deploy_agg["deploys_7d"],
        "deploys_30d": deploy_agg["deploys_30d"],
        "change_failure_rate_30d": deploy_agg["change_failure_rate_30d"],
        "cfr_sample_30d": deploy_agg["cfr_sample_30d"],
        "mttr_minutes_30d": deploy_agg["mttr_minutes_30d"],
        "last_deploy_at": deploy_agg["last_deploy_at"],
        "ci_runs_7d": ci_agg["ci_runs_7d"],
        "ci_failures_7d": ci_agg["ci_failures_7d"],
        "ci_running_now": ci_agg["ci_running_now"],
        "connections_ok": int(snap_summary.get("ok", 0)) if snapshot is not None else None,
        "connections_total": len(resultados) if snapshot is not None else None,
        "servers_total": len(servers),
        "apps_total": len(apps_en_alcance),
        "targets_configured": targets_configured,
        "targets_locked": len(locked_targets),
    }

    axis = build_day_axis(now_utc, filters["window_days"])
    deploys_planos = [e for lst in entries_by_app.values() for e in _terminated_deploys(lst)]
    from services import deploy_planner
    series = {
        "days": axis,
        "deploys_by_day": bucket_by_day([e["finished_at"] for e in deploys_planos], axis),
        "deploy_failures_by_day": bucket_by_day(
            [e["finished_at"] for e in deploys_planos
             if e.get("status") in deploy_planner.FAILED_STATUSES], axis),
        "ci_runs_by_day": bucket_by_day(
            [_ci_started(r) for r in ci_runs if _ci_started(r)], axis),
        "ci_failures_by_day": bucket_by_day(
            [_ci_started(r) for r in ci_runs
             if _ci_status(r) in _CI_FAILED and _ci_started(r)], axis),
    }

    ctx = {
        "locked_targets": locked_targets,
        "last_failed_by_target": deploy_agg["last_failed_by_target"],
        "ci_runs": ci_runs,
        "ci_last_failure": ci_agg["last_failure"],
        "snapshot": snapshot,
        "connections_stale": connections_stale,
        "deploy_available": blocks["deployments"]["available"],
        "ci_available": blocks["ci"]["available"],
        "connections_available": blocks["connections"]["available"],
        "servers_available": blocks["servers"]["available"],
    }
    alerts = derive_alerts(kpis, ctx, now_utc)

    # `recent` de despliegues: todos los entries del alcance (incluidos rollbacks).
    recent_deploys = [e for lst in entries_by_app.values() for e in (lst or [])]
    return {
        "generated_at": now_utc.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": derive_status(alerts, blocks),
        "filters": filters,
        "options": options,
        "kpis": kpis,
        "series": series,
        "alerts": alerts,
        "recent": build_recent(recent_deploys, ci_runs),
        "blocks": blocks,
    }
