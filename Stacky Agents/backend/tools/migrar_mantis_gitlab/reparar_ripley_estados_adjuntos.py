"""tools/migrar_mantis_gitlab/reparar_ripley_estados_adjuntos.py

Reparación puntual e IDEMPOTENTE de una migración Mantis -> GitLab ya
ejecutada. Nace de la corrida de Ripley del 2026-07-29, que dejó dos
agujeros:

  1. ADJUNTOS: no se migró ninguno (salvo 2, de un solo issue). Causa raíz
     en `migrator_mg_executor._apply_upload_attachment`: `migrate_attachment_mg`
     nunca propaga una excepción — devuelve `{"skipped": False,
     "verified": False, "error": ...}` — y el executor sólo miraba `skipped`,
     así que contaba como APLICADO un adjunto que había fallado. El reporte
     dio verde con cero adjuntos migrados. Ya corregido en el executor; este
     módulo repara los datos que quedaron mal.

  2. ESTADOS: en GitLab sólo se distinguía Open/Closed y el label de estado
     estaba en inglés. Se reemplaza por el label en español de
     `field_mapping.status`, garantizando EXCLUSIVIDAD a mano: los scoped
     labels (`status::…`) sólo son mutuamente excluyentes en GitLab Premium,
     y esta instancia es CE, así que hay que sacar el label viejo
     explícitamente (`remove_labels`) en la misma llamada que agrega el nuevo.

Por qué NO se resuelve re-corriendo `execute`: `plan_migration` re-planifica
los 1000+ issues y sus ~2900 notas, y `execute` además re-aplica estados y
relaciones. Para una reparación quirúrgica sobre un destino que ya está
poblado, eso es mucho más riesgoso que tocar sólo lo que falta. Este módulo
reusa las MISMAS piezas del tool (adapter de origen, `DestinationWriter`,
`migrate_attachment_mg`, `map_status`), así que ejercita los mismos caminos
de código ya corregidos.

Uso:
    python -m tools.migrar_mantis_gitlab.reparar_ripley_estados_adjuntos \
        --config ../deployment/migration_config_ripley.json \
        --fase labels --dry-run
    ... --fase labels --confirmed
    ... --fase adjuntos --dry-run --limit 3
    ... --fase adjuntos --confirmed
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

from .config_loader import load_config
from .destination_writer import GitLabDestinationWriter, assert_target_matches
from .mapping.status_map import map_status
from .migrator_mg_attachments import migrate_attachment_mg

_MARKER_ISSUE_RE = re.compile(r"<!--\s*stacky-migrated:mantis:(\d+):(\d+)\s*-->")
_ATTACH_MARKER = "<!-- stacky-migrated:mantis-file:{project_id}:{issue_id}:{file_id} -->"

# Colores por estado (hex GitLab). Sólo se usan al CREAR el label.
_COLORES = {
    "nuevas": "#428BCA",
    "se necesitan más datos": "#AD4363",
    "aceptadas": "#5CB85C",
    "confirmadas": "#0033CC",
    "asignadas": "#F0AD4E",
    "resueltas": "#69D100",
    "cerradas": "#666666",
    "sin_mapear": "#CC0033",
}


def _client(writer):
    return writer._provider._client


def _proj(writer):
    return writer._provider._client._project_path()


def _api(writer, method, path, **kw):
    body, headers = _client(writer)._request(method, path, **kw)
    return body, headers


# ── Lecturas ────────────────────────────────────────────────────────────


def gitlab_issues(writer) -> list[dict]:
    """Todos los issues del proyecto destino (abiertos y cerrados)."""
    out: list[dict] = []
    page = 1
    while True:
        body, _ = _api(
            writer, "GET", f"/projects/{_proj(writer)}/issues",
            params={"per_page": 100, "page": page, "scope": "all"},
        )
        if not isinstance(body, list) or not body:
            break
        out.extend(body)
        page += 1
        if page > 100:
            break
    return out


def indice_por_issue_mantis(issues: list[dict], mantis_project_id: str) -> dict[str, dict]:
    """`{mantis_issue_id: issue_gitlab}` leyendo el marker de la descripción.

    Se usa el MARKER y no el SQLite de la corrida a propósito: el marker vive
    en el destino, así que la reparación funciona aunque el `run_state` local
    se haya perdido o pertenezca a otra máquina (mismo criterio que
    `hydrate_map_from_destination_mg`)."""
    idx: dict[str, dict] = {}
    for issue in issues:
        for match in _MARKER_ISSUE_RE.finditer(issue.get("description") or ""):
            if match.group(1) == str(mantis_project_id):
                idx[match.group(2)] = issue
    return idx


# ── Fase 1: labels de estado ────────────────────────────────────────────


def asegurar_labels(writer, labels: set[str], *, dry_run: bool) -> list[str]:
    """Crea los labels que falten. GitLab los auto-crearía al asignarlos,
    pero con un color aleatorio: crearlos acá les fija color y descripción."""
    body, _ = _api(writer, "GET", f"/projects/{_proj(writer)}/labels",
                   params={"per_page": 100})
    existentes = {l["name"] for l in body} if isinstance(body, list) else set()
    creados = []
    for nombre in sorted(labels - existentes):
        sufijo = nombre.split("::", 1)[1] if "::" in nombre else nombre
        if dry_run:
            creados.append(nombre)
            continue
        try:
            _api(writer, "POST", f"/projects/{_proj(writer)}/labels",
                 json_body={"name": nombre,
                            "color": _COLORES.get(sufijo, "#888888"),
                            "description": f"Estado en Mantis: {sufijo}"})
            creados.append(nombre)
        except Exception as exc:
            if "already exists" not in str(exc).lower():
                raise
    return creados


def reparar_labels(writer, cfg, estados_mantis: dict[str, str], *,
                   dry_run: bool, limit: Optional[int] = None,
                   workers: int = 8) -> dict:
    mantis_project_id = str(cfg.origin.project_ids[0])
    # Se reusa el conversor del CLI (no se reimplementa el shape del config):
    # `field_mapping.status` es un `StatusMapping` tipado, y `map_status`
    # espera el dict CRUDO con `_unmapped_fallback` incluido.
    from .__main__ import _field_mapping_to_dict

    fm_status = _field_mapping_to_dict(cfg.field_mapping)["status"]

    issues = gitlab_issues(writer)
    idx = indice_por_issue_mantis(issues, mantis_project_id)
    print(f"[labels] issues en GitLab: {len(issues)} | con marker Mantis: {len(idx)}")

    deseados = {v["label"] for k, v in fm_status.items() if not k.startswith("_")}
    creados = asegurar_labels(writer, deseados, dry_run=dry_run)
    print(f"[labels] labels creados: {creados or 'ninguno (ya existían)'}")

    res = {"revisados": 0, "cambiados": 0, "ya_ok": 0, "sin_estado_origen": 0,
           "errores": [], "detalle": []}
    lock = threading.Lock()

    # 1ra pasada SIN red: decidir qué hay que tocar. Así el trabajo paralelo
    # es sólo el PUT, y el conteo no depende del orden de los hilos.
    pendientes = []
    procesados = 0
    for mantis_id, issue in sorted(idx.items(), key=lambda kv: int(kv[0])):
        if limit is not None and procesados >= limit:
            break
        estado = estados_mantis.get(mantis_id)
        if estado is None:
            res["sin_estado_origen"] += 1
            continue
        procesados += 1
        res["revisados"] += 1

        _, label_deseado, _ = map_status(estado, fm_status)
        actuales = [l for l in (issue.get("labels") or []) if l.startswith("status::")]
        a_sacar = [l for l in actuales if l != label_deseado]
        ya_tiene = label_deseado in actuales

        if ya_tiene and not a_sacar:
            res["ya_ok"] += 1
            continue

        res["detalle"].append({"mantis": mantis_id, "iid": issue["iid"],
                               "de": actuales, "a": label_deseado})
        pendientes.append((mantis_id, issue, label_deseado, a_sacar, ya_tiene))

    if dry_run:
        res["cambiados"] = len(pendientes)
        return res

    def _aplicar(item):
        mantis_id, issue, label_deseado, a_sacar, ya_tiene = item
        payload = {}
        if not ya_tiene:
            payload["add_labels"] = label_deseado
        if a_sacar:
            payload["remove_labels"] = ",".join(a_sacar)
        try:
            _api(writer, "PUT",
                 f"/projects/{_proj(writer)}/issues/{issue['iid']}", json_body=payload)
            with lock:
                res["cambiados"] += 1
                if res["cambiados"] % 100 == 0:
                    print(f"  ... {res['cambiados']}/{len(pendientes)} relabeleados",
                          flush=True)
        except Exception as exc:
            with lock:
                res["errores"].append({"mantis": mantis_id, "iid": issue["iid"],
                                       "error": str(exc)})

    # Paralelo entre issues: cada PUT toca un issue DISTINTO, así que no hay
    # read-modify-write compartido (a diferencia de los adjuntos, que sí
    # reescriben la descripción y por eso van serializados por issue).
    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(_aplicar, pendientes))
    return res


# ── Fase 2: adjuntos ────────────────────────────────────────────────────


def reparar_adjuntos(writer, cfg, origin_adapter, *, dry_run: bool,
                     limit: Optional[int] = None,
                     solo_issues: "set[str] | None" = None,
                     workers: int = 6,
                     censo: "dict[str, list] | None" = None) -> dict:
    mantis_project_id = str(cfg.origin.project_ids[0])
    issues = gitlab_issues(writer)
    idx = indice_por_issue_mantis(issues, mantis_project_id)
    print(f"[adjuntos] issues en GitLab con marker: {len(idx)}")

    opciones = cfg.options.attachments
    res = {"issues_con_adjuntos": 0, "adjuntos_vistos": 0, "subidos": 0,
           "ya_estaban": 0, "saltados_tamano": 0, "errores": [],
           "sin_issue_destino": []}
    lock = threading.Lock()

    # Qué issues tienen adjuntos: del censo pre-cargado si se pasa (evita
    # re-scrapear 1010 `view.php`), si no leyendo Mantis.
    trabajo: list[tuple[str, dict, list]] = []
    if censo is not None:
        fuente = [(mid, adjs) for mid, adjs in censo.items() if adjs]
    else:
        fuente = []
        for issue_origen in origin_adapter.fetch_all_issues():
            mid = str(issue_origen.get("id"))
            try:
                adjs = origin_adapter.fetch_attachments(issue_origen.get("id"))
            except Exception as exc:
                res["errores"].append({"mantis": mid, "error": f"fetch_attachments: {exc}"})
                continue
            if adjs:
                fuente.append((mid, adjs))

    for mantis_id, adjuntos in sorted(fuente, key=lambda kv: int(kv[0])):
        if solo_issues is not None and mantis_id not in solo_issues:
            continue
        res["issues_con_adjuntos"] += 1
        destino = idx.get(mantis_id)
        if destino is None:
            res["sin_issue_destino"].append(mantis_id)
            continue
        if limit is not None and len(trabajo) >= limit:
            break
        trabajo.append((mantis_id, destino, adjuntos))

    print(f"[adjuntos] issues a procesar: {len(trabajo)} | "
          f"adjuntos declarados: {sum(len(a) for _, _, a in trabajo)}")
    t0 = time.time()

    def _procesar_issue(item):
        mantis_id, destino, adjuntos = item
        # Los adjuntos de UN issue van SERIALIZADOS: `link_attachment` hace
        # read-modify-write de la descripción (`gitlab_provider.py:369-385`),
        # así que dos hilos sobre el mismo issue se pisarían el markdown.
        for adj in adjuntos:
            with lock:
                res["adjuntos_vistos"] += 1
            marker = _ATTACH_MARKER.format(project_id=mantis_project_id,
                                           issue_id=mantis_id,
                                           file_id=adj.get("id"))
            try:
                if writer.attachment_exists(str(destino["iid"]), marker, adj.get("name", "")):
                    with lock:
                        res["ya_estaban"] += 1
                    continue
            except Exception as exc:
                with lock:
                    res["errores"].append({"mantis": mantis_id, "iid": destino["iid"],
                                           "adjunto": adj.get("name"),
                                           "error": f"attachment_exists: {exc}"})
                continue
            if dry_run:
                print(f"  [DRY] mantis {mantis_id} -> iid {destino['iid']}: "
                      f"subiría {adj.get('name')!r} ({adj.get('size')} bytes)")
                continue
            outcome = migrate_attachment_mg(
                adj, writer, origin_adapter,
                dest_iid=str(destino["iid"]),
                max_size_mb=opciones.max_size_mb,
                skip_if_over_limit=opciones.skip_if_over_limit,
                marker=marker,
            )
            with lock:
                if outcome.get("skipped"):
                    res["saltados_tamano"] += 1
                elif outcome.get("error") or not outcome.get("verified"):
                    res["errores"].append({"mantis": mantis_id, "iid": destino["iid"],
                                           "adjunto": adj.get("name"),
                                           "error": outcome.get("error", "no verificado")})
                else:
                    res["subidos"] += 1

    hechos = 0
    with ThreadPoolExecutor(max_workers=1 if dry_run else workers) as pool:
        futuros = [pool.submit(_procesar_issue, it) for it in trabajo]
        for _ in as_completed(futuros):
            hechos += 1
            if hechos % 25 == 0:
                print(f"  ... {hechos}/{len(trabajo)} issues | subidos={res['subidos']} "
                      f"ya_estaban={res['ya_estaban']} err={len(res['errores'])} "
                      f"{time.time()-t0:.0f}s", flush=True)
    return res


def limpiar_links_de_adjuntos(writer, cfg, *, dry_run: bool) -> dict:
    """Saca de la descripción los links a adjuntos VACÍOS (0 bytes).

    La corrida del 2026-07-29 subió adjuntos de 0 bytes (descarga rota, ver
    `scraping_adapter.download_attachment_binary`) y los linkeó. Esos links
    apuntan a un archivo que existe pero está vacío: peor que no tenerlo,
    porque parece migrado. Se limpian para que la pasada de adjuntos los
    vuelva a subir bien (el chequeo de idempotencia los saltearía si no).

    Sólo toca issues cuya descripción tenga links `/uploads/`, y sólo borra
    esas líneas y las de marker de adjunto: el resto de la descripción
    (cuerpo del ticket, bloque de autoría, marker del issue) no se toca.
    """
    mantis_project_id = str(cfg.origin.project_ids[0])
    issues = gitlab_issues(writer)
    idx = indice_por_issue_mantis(issues, mantis_project_id)

    res = {"issues_tocados": 0, "links_removidos": 0, "detalle": []}
    for mantis_id, issue in sorted(idx.items(), key=lambda kv: int(kv[0])):
        desc = issue.get("description") or ""
        if "/uploads/" not in desc:
            continue
        lineas = desc.splitlines()
        quedan = [l for l in lineas
                  if "/uploads/" not in l and "stacky-migrated:mantis-file:" not in l]
        removidas = len(lineas) - len(quedan)
        if not removidas:
            continue
        nueva = "\n".join(quedan).rstrip() + "\n"
        res["issues_tocados"] += 1
        res["links_removidos"] += removidas
        res["detalle"].append({"mantis": mantis_id, "iid": issue["iid"],
                               "lineas_removidas": removidas})
        if dry_run:
            continue
        _api(writer, "PUT", f"/projects/{_proj(writer)}/issues/{issue['iid']}",
             json_body={"description": nueva})
    return res


# ── Issue board por estado ──────────────────────────────────────────────

# Orden de FLUJO de Mantis (no alfabetico): es como avanza un ticket.
_ORDEN_ESTADOS = ["new", "feedback", "acknowledged", "confirmed",
                  "assigned", "resolved", "closed"]


def configurar_board(writer, cfg, *, dry_run: bool, nombre_board: "str | None" = None,
                     board_id: "int | None" = None) -> dict:
    """Deja UN issue board con una lista por estado, en orden de flujo.

    LIMITACION DURA DE GITLAB (no es un bug de este script): una lista de
    board por LABEL muestra unicamente issues ABIERTOS. Los issues cerrados
    no aparecen en ninguna lista de label, sino en la lista "Closed"
    incorporada del board (que se controla con `hide_closed_list`). Por eso
    la lista `status::cerradas` se ve VACIA aunque el label este bien puesto
    en 956 issues. Se deja `hide_closed_list=False` para que esos 956 sean
    visibles en la lista Closed, y la verificacion reporta el conteo REAL de
    cada lista para que la diferencia quede a la vista y no escondida.
    """
    from .__main__ import _field_mapping_to_dict

    fm_status = _field_mapping_to_dict(cfg.field_mapping)["status"]
    deseadas = [fm_status[k]["label"] for k in _ORDEN_ESTADOS if k in fm_status]

    body, _ = _api(writer, "GET", f"/projects/{_proj(writer)}/labels",
                   params={"per_page": 100})
    label_id = {l["name"]: l["id"] for l in body} if isinstance(body, list) else {}
    faltan = [l for l in deseadas if l not in label_id]
    if faltan:
        raise RuntimeError(f"faltan labels en el proyecto: {faltan}")

    boards, _ = _api(writer, "GET", f"/projects/{_proj(writer)}/boards")
    if board_id is None:
        if not boards:
            raise RuntimeError("el proyecto no tiene ningun board")
        board_id = boards[0]["id"]
    board = next(b for b in boards if b["id"] == board_id)

    res = {"board_id": board_id, "board_nombre_previo": board["name"],
           "listas_previas": [(l["id"], (l.get("label") or {}).get("name"))
                              for l in board.get("lists", [])],
           "borradas": [], "creadas": [], "renombrado": False}

    if dry_run:
        res["creadas"] = deseadas
        res["borradas"] = [n for _, n in res["listas_previas"]]
        return res

    # `hide_closed_list=False` es lo unico que hace visibles los cerrados.
    payload = {"hide_closed_list": False, "hide_backlog_list": False}
    if nombre_board and nombre_board != board["name"]:
        payload["name"] = nombre_board
        res["renombrado"] = True
    _api(writer, "PUT", f"/projects/{_proj(writer)}/boards/{board_id}",
         json_body=payload)

    # Se borran TODAS las listas y se recrean en orden: la API asigna la
    # position por orden de creacion (append), asi que recrear de cero es la
    # unica forma confiable de fijar el orden sin depender de reordenamientos.
    for lst in board.get("lists", []):
        _api(writer, "DELETE",
             f"/projects/{_proj(writer)}/boards/{board_id}/lists/{lst['id']}")
        res["borradas"].append((lst["id"], (lst.get("label") or {}).get("name")))

    for nombre in deseadas:
        nueva, _ = _api(writer, "POST",
                        f"/projects/{_proj(writer)}/boards/{board_id}/lists",
                        json_body={"label_id": label_id[nombre]})
        res["creadas"].append((nueva.get("id"), nombre, nueva.get("position")))
    return res


def verificar_board(writer, cfg, *, board_id: "int | None" = None) -> dict:
    """Relee el board por API y cuenta, por lista, los issues que REALMENTE
    muestra (label + state=opened, que es el criterio de GitLab) contra el
    total del label. La diferencia es lo que el board esconde."""
    boards, _ = _api(writer, "GET", f"/projects/{_proj(writer)}/boards")
    if board_id is None:
        board_id = boards[0]["id"]
    board = next(b for b in boards if b["id"] == board_id)

    def total(**p):
        q = {"per_page": 1}
        q.update(p)
        _, headers = _api(writer, "GET", f"/projects/{_proj(writer)}/issues", params=q)
        return int(headers.get("X-Total") or headers.get("x-total") or 0)

    filas = []
    for lst in sorted(board.get("lists", []), key=lambda l: l["position"]):
        nombre = (lst.get("label") or {}).get("name")
        filas.append({
            "position": lst["position"], "list_id": lst["id"], "label": nombre,
            "muestra": total(labels=nombre, state="opened"),
            "label_total": total(labels=nombre),
        })
    return {"board_id": board_id, "nombre": board["name"],
            "hide_closed_list": board["hide_closed_list"],
            "hide_backlog_list": board["hide_backlog_list"],
            "listas": filas,
            "cerrados_en_lista_Closed": total(state="closed")}


# ── CLI ─────────────────────────────────────────────────────────────────


def main(argv: "Optional[list[str]]" = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", required=True)
    ap.add_argument("--fase", choices=["labels", "adjuntos", "ambas", "limpiar-vacios",
                                       "board", "verificar-board"], required=True)
    ap.add_argument("--nombre-board", default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--confirmed", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--solo-issues", default=None,
                    help="IDs Mantis separados por coma (para el dry-run acotado)")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--censo", default=None,
                    help="JSON [{id, attachments:[...]}] para no re-scrapear Mantis")
    args = ap.parse_args(argv)

    if not args.dry_run and not args.confirmed:
        print("ABORTADO: hace falta --dry-run o --confirmed explícito.")
        return 2

    cfg = load_config(args.config)
    from . import __main__ as mg

    token = mg._prompt_and_resolve_secret(
        cfg.destination.auth.auth_file, "token", cfg.destination.auth.secret_backend)
    writer = GitLabDestinationWriter(cfg.destination, token)
    assert_target_matches(writer, cfg.destination)
    print(f"destino verificado: {writer.effective_target()}")

    if args.fase == "verificar-board":
        v = verificar_board(writer, cfg)
        print(json.dumps(v, ensure_ascii=False, indent=1))
        return 0

    if args.fase == "board":
        r = configurar_board(writer, cfg, dry_run=args.dry_run,
                             nombre_board=args.nombre_board)
        print("[board] RESULTADO:", json.dumps(r, ensure_ascii=False)[:2000])
        if not args.dry_run:
            print("[board] VERIFICACION:",
                  json.dumps(verificar_board(writer, cfg), ensure_ascii=False, indent=1))
        return 0

    if args.fase == "limpiar-vacios":
        r = limpiar_links_de_adjuntos(writer, cfg, dry_run=args.dry_run)
        print("[limpiar-vacios] RESULTADO:", json.dumps(r, ensure_ascii=False)[:2000])
        return 0

    origin_adapter = mg._build_origin_adapter(cfg)
    solo = set(args.solo_issues.split(",")) if args.solo_issues else None

    if args.fase in ("labels", "ambas"):
        estados = {str(i.get("id")): i.get("status")
                   for i in origin_adapter.fetch_all_issues()}
        print(f"[labels] estados leídos de Mantis: {len(estados)}")
        r = reparar_labels(writer, cfg, estados, dry_run=args.dry_run,
                           limit=args.limit, workers=args.workers)
        print("[labels] RESULTADO:", json.dumps(
            {k: v for k, v in r.items() if k != "detalle"}, ensure_ascii=False)[:2000])
        for d in r["detalle"][:10]:
            print("   ", d)

    if args.fase in ("adjuntos", "ambas"):
        censo = None
        if args.censo:
            with open(args.censo, encoding="utf-8") as fh:
                censo = {str(r["id"]): r.get("attachments") or [] for r in json.load(fh)}
            print(f"[adjuntos] censo precargado: {len(censo)} issues")
        r = reparar_adjuntos(writer, cfg, origin_adapter, dry_run=args.dry_run,
                             limit=args.limit, solo_issues=solo,
                             workers=args.workers, censo=censo)
        print("[adjuntos] RESULTADO:", json.dumps(r, ensure_ascii=False)[:3000])
    return 0


if __name__ == "__main__":
    sys.exit(main())
