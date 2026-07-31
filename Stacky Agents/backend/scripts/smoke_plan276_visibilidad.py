"""scripts/smoke_plan276_visibilidad.py — Plan 276 F12: EL GATE DE CIERRE.

Responde con un EXIT CODE la única pregunta que importa: *después de este plan, ¿hay
tickets visibles en el grafo, y son TODOS los que hay en GitLab?*

POR QUÉ EXISTE. El criterio de cierre era un `curl` leído a ojo. Eso deja tres
agujeros: no distingue "el grafo trae 3 de 53" de "trae los 53"; no lo puede ejecutar
un modelo menor ni un runtime sin una persona delante; y no FALLA — un humano cansado
lee `{"epics":[],"orphans":[]}` y sigue. Un plan cuyo objetivo declarado es *ver los
tickets* tiene que terminar en un gate que se ponga ROJO cuando no se ven.

POR QUÉ DOS CRITERIOS. `len(epics)+len(orphans) > 0` se satisface con UN ticket. El
modo de falla realista de este plan no es "cero tickets" sino "ALGUNOS tickets": el
techo de 4.000 issues truncando (P2-1), el `skipped` del iid no numérico (F5.2), o
una TrackerQuery con el `state` equivocado. Los tres dan un grafo no vacío y
MENTIROSO, que pasa cualquier inspección visual. El único número que los detecta es
el `X-Total` que devuelve GitLab — el mismo que el operador ve en su UI de GitLab.

TOLERANCIA DECLARADA Y ACOTADA: el sync trae ABIERTOS y el grafo puede contener
además issues CERRADOS de corridas anteriores (que el sync marca `closed` pero NO
borra). El criterio 2 compara solo contra los abiertos: se cuentan las filas con
`ado_state != "closed"`. Está así a propósito — comparar el total crudo daría un rojo
FALSO en la segunda corrida, y un gate que da rojos falsos se termina desactivando,
que es peor que no tenerlo.

NO es un test de pytest: es un smoke contra el sistema VIVO. No se registra en los
ratchets, no entra en la allowlist y no corre en CI (necesita el backend arriba y el
GitLab real alcanzable). Se corre a mano y queda como herramienta de diagnóstico.

Dependencias nuevas: CERO (solo stdlib: urllib.request + json).

Exit codes:
    0 — VISIBILIDAD OK: el grafo trae todos los abiertos.
    1 — el operador NO ve (todos o parte de) los tickets ⇒ el plan no cerró.
    2 — falta un prerequisito; el script dice cuál.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

_BASE_API = "http://localhost:5000"
_TIMEOUT = 120


def _http(metodo: str, url: str, cuerpo: dict | None = None) -> tuple[int, dict]:
    datos = json.dumps(cuerpo).encode("utf-8") if cuerpo is not None else None
    req = urllib.request.Request(url, data=datos, method=metodo)
    if datos is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            crudo = resp.read().decode("utf-8", errors="replace")
            return resp.status, (json.loads(crudo) if crudo.strip() else {})
    except urllib.error.HTTPError as exc:
        crudo = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(crudo)
        except Exception:  # noqa: BLE001
            return exc.code, {"raw": crudo}


def _contar_abiertos(body: dict) -> int:
    """Épicas + hijos + huérfanos, contando solo lo que NO está cerrado."""
    total = 0
    for epica in body.get("epics") or []:
        if (epica.get("ado_state") or "").lower() != "closed":
            total += 1
        for hija in epica.get("children") or []:
            if (hija.get("ado_state") or "").lower() != "closed":
                total += 1
    for huerfano in body.get("orphans") or []:
        if (huerfano.get("ado_state") or "").lower() != "closed":
            total += 1
    return total


def correr(proyecto: str | None, base_api: str) -> int:
    # ── Paso 1: el proyecto activo ────────────────────────────────────────────
    if not proyecto:
        try:
            from project_manager import get_active_project

            proyecto = get_active_project()
        except Exception as exc:  # noqa: BLE001
            print(f"FALTA PREREQUISITO: no se pudo resolver el proyecto activo ({exc}).")
            return 2
    if not proyecto:
        print("FALTA PREREQUISITO: no hay proyecto activo. Pasá --project <NOMBRE>.")
        return 2

    # ── Paso 2: el preflight de F0.8. Fallar temprano y nombrar qué falta ─────
    from scripts.preflight_plan276 import correr as preflight

    if preflight(proyecto) != 0:
        print("\nFALTA PREREQUISITO: el preflight no dio 6/6 (ver arriba). No se sigue.")
        return 2
    print()

    # ── Paso 3: disparar el sync ──────────────────────────────────────────────
    status, cuerpo = _http("POST", f"{base_api}/api/tickets/sync-v2", {"project": proyecto})
    if not (200 <= status < 300):
        print(f"sync-v2: HTTP {status} — {cuerpo.get('message') or cuerpo}")
        return 1
    if cuerpo.get("available") is False:
        print(f"sync-v2: CAPACIDAD AUSENTE — {cuerpo.get('message') or cuerpo}")
        return 1
    if not cuerpo.get("ok"):
        print(f"sync-v2: ok=false — {cuerpo.get('message') or cuerpo}")
        return 1
    print(
        f"sync-v2: ok=true created={cuerpo.get('created')} updated={cuerpo.get('updated')} "
        f"removed={cuerpo.get('removed')} skipped={cuerpo.get('skipped', 0)}"
    )

    # ── Paso 4: el X-Total REAL de GitLab ─────────────────────────────────────
    try:
        from services.gitlab_client import GitLabClient
        from services.project_context import build_tracker_target

        tgt = build_tracker_target(proyecto)
        cli = GitLabClient(
            base_url=tgt.base_url or "", project=tgt.project_path,
            auth_path=tgt.auth_path, ca_bundle=tgt.ca_bundle,
        )
        issues, headers = cli._request(
            "GET", f"/projects/{cli._project_path()}/issues",
            params={"state": "opened", "per_page": 1},
        )
        crudo_total = headers.get("X-Total") or headers.get("x-total") if hasattr(headers, "get") else None
        x_total = int(crudo_total) if crudo_total else len(issues or [])
    except Exception as exc:  # noqa: BLE001
        kind = getattr(exc, "kind", None)
        print(f"GitLab X-Total: NO SE PUDO LEER ({type(exc).__name__}"
              + (f", kind={kind}" if kind else "") + f"): {exc}")
        return 1
    print(f"GitLab X-Total (abiertos): {x_total}")

    # ── Paso 5: el grafo ──────────────────────────────────────────────────────
    status, grafo = _http("GET", f"{base_api}/api/tickets/hierarchy?project={proyecto}")
    if not (200 <= status < 300):
        print(f"hierarchy: HTTP {status} — {grafo}")
        return 1
    epics, orphans = grafo.get("epics") or [], grafo.get("orphans") or []
    en_grafo = _contar_abiertos(grafo)
    print(f"grafo: epics={len(epics)} orphans={len(orphans)} total_abiertos={en_grafo}")

    # ── Paso 6: criterio 1 — el grafo no está vacío ───────────────────────────
    if len(epics) + len(orphans) == 0:
        print(f"VISIBILIDAD: FALLA — el grafo está VACÍO (GitLab={x_total}).")
        return 1

    # ── Paso 7: criterio 2 — y trae TODOS ─────────────────────────────────────
    if en_grafo != x_total:
        print(f"VISIBILIDAD: FALLA — grafo={en_grafo}, GitLab={x_total}, "
              f"faltan {x_total - en_grafo}.")
        return 1

    print(f"VISIBILIDAD: OK  ({en_grafo}/{x_total})")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Gate de visibilidad del Plan 276")
    ap.add_argument("--project", default=None, help="nombre del proyecto Stacky")
    ap.add_argument("--base-api", default=_BASE_API, help="URL del backend de Stacky")
    args = ap.parse_args()
    return correr(args.project, args.base_api.rstrip("/"))


if __name__ == "__main__":
    raise SystemExit(main())
