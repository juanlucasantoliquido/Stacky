"""scripts/preflight_plan276.py — Plan 276 F0.8: preflight de VISIBILIDAD.

POR QUÉ EXISTE. Los prerequisitos que bloquean *ver tickets de GitLab* viven en 6
lugares distintos (una flag de config, el JSON del proyecto, dos archivos en disco,
un campo de texto de la UI y otra flag). Se descubrían DE A UNO, cada uno
enmascarando al siguiente: en la corrida real de RIPLEY eso costó tres viajes
(ruteo → CERTIFICATE_VERIFY_FAILED → HTTP 404). Esto los mide TODOS JUNTOS y cada
fallo trae su remedio en una línea.

ES UN SCRIPT, NO UN TEST: no se registra en los ratchets (que solo listan
`tests/*.py`) y no entra en la allowlist.

READ-ONLY Y SIN create_app(). Llamar `create_app()` sin `DATABASE_URL` hace
`create_all` contra la BD REAL del operador (181 MB de datos de cliente). Acá solo
se lee config, el JSON del proyecto y `os.path.isfile`.

TRAMPA A EVITAR (medida en RIPLEY, 2026-07-30): el chequeo del archivo de
credenciales SOLO verifica que exista. NUNCA lo abre ni lo escribe. Un escritor de
credenciales ya destruyó un `.pem` de 3907 líneas cuando una ruta de certificado
terminó en el campo equivocado. Preflight = `isfile`, jamás `open(..., "w")`.

REUSA LOS RESOLVEDORES DE PRODUCCIÓN (`resolve_project_context` /
`build_tracker_target`), no una lectura paralela: si el preflight dice verde y
producción falla, el bug está en el resolvedor, no en dos lecturas divergentes.

Uso:
    python scripts/preflight_plan276.py [--project NOMBRE]

Exit code: 0 si los 6 pasan; 1 si alguno falla.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

_OK = "OK   "
_FALLA = "FALLA"
_SKIP = "SKIP "


class _Chequeo:
    def __init__(self, numero: int, titulo: str):
        self.numero = numero
        self.titulo = titulo
        self.estado = _FALLA
        self.detalle = ""
        self.remedio = ""

    def ok(self, detalle: str) -> "_Chequeo":
        self.estado, self.detalle = _OK, detalle
        return self

    def falla(self, detalle: str, remedio: str) -> "_Chequeo":
        self.estado, self.detalle, self.remedio = _FALLA, detalle, remedio
        return self

    def skip(self, detalle: str) -> "_Chequeo":
        self.estado, self.detalle = _SKIP, detalle
        return self

    def imprimir(self) -> None:
        print(f"  [{self.estado}] {self.numero}. {self.titulo}: {self.detalle}")
        if self.remedio:
            print(f"          → {self.remedio}")


def _resolver_proyecto(nombre: str | None) -> str | None:
    if nombre:
        return nombre
    try:
        from project_manager import get_active_project

        return get_active_project()
    except Exception as exc:  # noqa: BLE001
        print(f"  no se pudo resolver el proyecto activo: {exc}")
        return None


def correr(nombre_proyecto: str | None = None) -> int:
    from config import config

    print("PREFLIGHT Plan 276 — prerequisitos para VER los tickets de GitLab")

    proyecto = _resolver_proyecto(nombre_proyecto)
    if not proyecto:
        print("  [FALLA] no hay proyecto activo ni --project.")
        print("          → Activá un proyecto en la UI o pasá --project <NOMBRE>.")
        print("PREFLIGHT: 0/6")
        return 1
    print(f"  proyecto: {proyecto}\n")

    chequeos: list[_Chequeo] = []

    # 1 — el master switch. Su default de fábrica es `false` y con él apagado el
    # tracker GitLab se rechaza ANTES de intentar cualquier conexión.
    c1 = _Chequeo(1, "STACKY_GITLAB_ENABLED")
    if bool(getattr(config, "STACKY_GITLAB_ENABLED", False)):
        c1.ok("True")
    else:
        c1.falla(
            "False (es el default de fábrica)",
            "Encendelo en Configuración global → GitLab (STACKY_GITLAB_ENABLED). "
            "Sin esto el tracker GitLab se rechaza antes de conectar.",
        )
    chequeos.append(c1)

    # 2 — el tipo de tracker del proyecto activo.
    c2 = _Chequeo(2, "issue_tracker.type del proyecto")
    ctx = None
    try:
        from services.project_context import resolve_project_context

        ctx = resolve_project_context(project_name=proyecto)
        tipo = (getattr(ctx, "tracker_type", None) or "").strip().lower()
        if tipo == "gitlab":
            c2.ok("gitlab")
        else:
            c2.falla(
                f"'{tipo or '(sin tipo)'}'",
                f"El proyecto activo tiene tracker '{tipo}'. Cambialo a 'gitlab' en "
                "Editar proyecto → Issue tracker.",
            )
    except Exception as exc:  # noqa: BLE001
        c2.falla(f"no se pudo resolver el contexto: {exc}",
                 "Revisá el config.json del proyecto (issue_tracker).")
    chequeos.append(c2)

    tgt = None
    try:
        from services.project_context import build_tracker_target

        tgt = build_tracker_target(proyecto)
    except Exception as exc:  # noqa: BLE001
        print(f"  (no se pudo construir el destino del tracker: {exc})")

    # 3 — el archivo de bundle declarado existe.
    c3 = _Chequeo(3, "certificado declarado")
    bundle = (getattr(tgt, "ca_bundle", None) or "") if tgt else ""
    if not bundle:
        c3.ok("no se declaró ninguno (verificación estándar)")
    elif os.path.isfile(bundle):
        c3.ok(bundle)
    else:
        c3.falla(
            f"declarado pero NO existe: '{bundle}'",
            f"El certificado declarado no existe: '{bundle}'. Corregí 'Certificado de "
            "la empresa' o dejalo vacío.",
        )
    chequeos.append(c3)

    # 4 — el auth file existe. SOLO `isfile`: nunca se abre ni se escribe.
    c4 = _Chequeo(4, "archivo de credenciales")
    auth = (getattr(tgt, "auth_path", None) or "") if tgt else ""
    if auth and os.path.isfile(auth):
        c4.ok(auth)
    else:
        c4.falla(
            f"no existe: '{auth or '(sin ruta)'}'",
            f"Falta el archivo de credenciales '{auth}'. Cargá el token en Editar "
            "proyecto → Archivo de credenciales.",
        )
    chequeos.append(c4)

    # 5 — base_url sin namespace ni /api/v4 pegado. Usa LA MISMA función que
    # producción (F3), no una copia.
    c5 = _Chequeo(5, "base_url del GitLab")
    base = (getattr(tgt, "base_url", None) or "") if tgt else ""
    try:
        from services.gitlab_client import _validar_base_url
    except (ImportError, AttributeError):
        c5.skip("pendiente F3 (_validar_base_url todavía no existe)")
    else:
        try:
            limpia = _validar_base_url(base)
            c5.ok(limpia or "(vacía: se resuelve por GITLAB_URL)")
        except Exception as exc:  # noqa: BLE001
            c5.falla(f"'{base}'", str(exc))
    chequeos.append(c5)

    # 6 — el destino por proyecto.
    c6 = _Chequeo(6, "STACKY_TRACKER_TARGET_PER_PROJECT_ENABLED")
    if bool(getattr(config, "STACKY_TRACKER_TARGET_PER_PROJECT_ENABLED", True)):
        c6.ok("True")
    else:
        c6.falla(
            "False",
            "Está en OFF: se usa la rama legacy. Encendela (Configuración global) o "
            "verificá F8.1.",
        )
    chequeos.append(c6)

    for c in chequeos:
        c.imprimir()

    # Un SKIP no cuenta contra el total (F0.8: el chequeo 5 nace en F3).
    exigibles = [c for c in chequeos if c.estado != _SKIP]
    pasados = [c for c in exigibles if c.estado == _OK]
    saltados = len(chequeos) - len(exigibles)
    print(f"\nPREFLIGHT: {len(pasados) + saltados}/{len(chequeos)}"
          + (f" ({saltados} en SKIP)" if saltados else ""))
    return 0 if len(pasados) == len(exigibles) else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="Preflight de visibilidad del Plan 276")
    ap.add_argument("--project", default=None, help="nombre del proyecto Stacky")
    args = ap.parse_args()
    return correr(args.project)


if __name__ == "__main__":
    raise SystemExit(main())
