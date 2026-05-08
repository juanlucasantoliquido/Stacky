"""
ado_smoke_test.py — Prueba end-to-end del provider Azure DevOps.

Ejecuta:
  1. Lee config.issue_tracker y arma un AzureDevOpsProvider.
  2. Verifica `is_available()` (auth + red + proyecto accesible).
  3. Lista work items abiertos (WIQL configurable).
  4. Toma el primero y descarga su detalle.
  5. Imprime un resumen por pantalla. NO escribe archivos salvo que se pase --sync.
  6. Con --sync, ejecuta `sync_tickets()` y escribe el layout local.

Uso:
    cd Tools/Stacky
    python scripts/ado_smoke_test.py [--project RSPACIFICO] [--sync] [--limit 3]

Requisitos:
    - STACKY_ADO_PAT (env) o auth/ado_auth.json con el PAT.
    - projects/<NAME>/config.json con issue_tracker.type="azure_devops".
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Permitir ejecutar el script desde cualquier cwd
_HERE = Path(__file__).resolve().parent
_STACKY = _HERE.parent
if str(_STACKY) not in sys.path:
    sys.path.insert(0, str(_STACKY))


def main():
    ap = argparse.ArgumentParser(description="Smoke test del IssueProvider ADO")
    ap.add_argument("--project", default=None,
                    help="Nombre del proyecto Stacky (default: proyecto activo)")
    ap.add_argument("--sync", action="store_true",
                    help="Ejecutar sync_tickets() y escribir archivos locales")
    ap.add_argument("--limit", type=int, default=5,
                    help="Máximo de work items a listar (default: 5)")
    args = ap.parse_args()

    from project_manager import get_active_project
    from issue_provider import get_provider, load_tracker_config, sync_tickets

    project = args.project or get_active_project()
    print(f"[smoke] Proyecto: {project}")

    cfg = load_tracker_config(project)
    if not cfg:
        print("[smoke] ❌ No hay issue_tracker configurado")
        sys.exit(2)
    print(f"[smoke] tracker type: {cfg.get('type')}")
    print(f"[smoke] organization:  {cfg.get('organization','-')}")
    print(f"[smoke] ado project:   {cfg.get('project','-')}")

    if cfg.get("type", "").lower() not in ("azure_devops", "ado"):
        print("[smoke] ⚠ El proyecto no está configurado para ADO — nada que testear.")
        sys.exit(0)

    provider = get_provider(project, override_config=cfg)
    ok, why = provider.is_available()
    if not ok:
        print(f"[smoke] ❌ provider no disponible: {why}")
        sys.exit(3)
    print("[smoke] ✅ provider disponible (auth + ping OK)")

    tickets = provider.fetch_open_tickets()
    print(f"[smoke] work items abiertos: {len(tickets)}")
    for t in tickets[:args.limit]:
        print(f"   - #{t.id:<8} [{t.state_raw:>12}] "
              f"({t.category}) {t.title[:70]}")

    if tickets:
        head = tickets[0]
        print(f"\n[smoke] Descargando detalle de #{head.id} ...")
        detail = provider.fetch_ticket_detail(head.id)
        print(f"   tags:           {detail.extra.get('tags','')}")
        print(f"   area_path:      {detail.extra.get('area_path','')}")
        print(f"   iteration_path: {detail.extra.get('iteration_path','')}")
        print(f"   description:    {len(detail.description)} chars (HTML={detail.description_is_html})")
        print(f"   comments:       {len(detail.comments)}")
        print(f"   attachments:    {len(detail.attachments)}")

    if args.sync:
        print("\n[smoke] Ejecutando sync_tickets() ...")
        summary = sync_tickets(project, limit=args.limit)
        print(f"[smoke] resumen: {summary}")
    else:
        print("\n[smoke] Usá --sync para escribir el layout local de tickets.")


if __name__ == "__main__":
    main()
